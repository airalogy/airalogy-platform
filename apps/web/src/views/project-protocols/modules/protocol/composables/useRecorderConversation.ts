import type { RecorderProposal, RecorderTurn } from "@airalogy/components/chat/providers/recorderTurn"
import { recorderTurnKey } from "@airalogy/components/chat/providers/recorderTurn"
import { cloneDeep, isEqual } from "lodash-es"
import { nanoid } from "nanoid"
import { computed, onActivated, onDeactivated, onScopeDispose, provide, ref, shallowReactive, shallowRef, watch } from "vue"
import { useI18n } from "vue-i18n"

interface RecorderOptions {
  scope: () => string
  version: () => string | undefined
  recordId: () => string | undefined
  editable: () => boolean
  fields: () => Record<string, { value?: unknown, assigner?: unknown }>
  isSimulated: (field: string) => boolean
  setSimulated: (field: string, simulated: boolean) => void
  write: (field: string, value: unknown) => Promise<void>
}

export interface RecorderFieldEdit {
  field: string
  before: unknown
  after: unknown
  wasSimulated: boolean
  revision?: number
}

export function recorderValue(value: unknown): unknown {
  return value && typeof value === "object" && "value" in value ? value.value : value
}
function empty(value: unknown) {
  const raw = recorderValue(value)
  return raw == null || raw === ""
}

export function useRecorderConversation(options: RecorderOptions) {
  const { locale, t } = useI18n()
  const receipt = ref("")
  const showPreviewLink = ref(false)
  const busy = ref(false)
  const offers = shallowRef<RecorderFieldEdit[]>([])
  const journal = shallowRef<RecorderFieldEdit[]>([])
  const revisions = shallowReactive(new Map<string, number>())
  let formId = nanoid()
  let activeRequest = ""
  let lastChatId: string | undefined
  let alive = true

  function matches(edit: RecorderFieldEdit, side: "before" | "after", fields = options.fields()) {
    const node = fields[edit.field]
    return node && !node.assigner && revisions.get(edit.field) === edit.revision && isEqual(node.value, edit[side])
  }
  function eligible(source: typeof offers, side: "before" | "after") {
    const available = computed(() => {
      const items = new Map<string, RecorderFieldEdit>()
      if (source.value.length) {
        const fields = options.fields()
        for (const edit of source.value) {
          if (matches(edit, side, fields))
            items.set(edit.field, edit)
        }
      }
      return items
    })
    // A picker or a dependent calculation may change a field without a DOM input event.
    // Once its snapshot is stale, returning to the old value must not revive the action.
    watch(available, (items) => {
      if (items.size < source.value.length)
        source.value = [...items.values()]
    }, { flush: "sync" })
    return available
  }
  const pending = eligible(offers, "before")
  const edits = eligible(journal, "after")
  const canBegin = () => alive && options.editable() && Boolean(options.version()) && !busy.value

  function reset() {
    formId = nanoid()
    activeRequest = ""
    lastChatId = undefined
    revisions.clear()
    offers.value = []
    journal.value = []
    receipt.value = ""
    showPreviewLink.value = false
  }
  watch([options.scope, options.editable], reset, { flush: "sync" })
  onActivated(() => {
    alive = true
  })
  onDeactivated(() => {
    alive = false
    reset()
  })
  onScopeDispose(() => {
    alive = false
  })

  function current(request: string) {
    return alive && options.editable() && request === activeRequest
  }

  async function writeChanges(changes: RecorderFieldEdit[], undoing = false) {
    if (busy.value || !changes.length || !current(activeRequest))
      return []
    const request = activeRequest
    const written: string[] = []
    busy.value = true
    try {
      for (const edit of changes) {
        if (!current(request))
          break
        if (!matches(edit, undoing ? "after" : "before"))
          continue
        await options.write(edit.field, undoing ? edit.before : edit.after)
        if (!current(request) || revisions.get(edit.field) !== edit.revision)
          continue
        options.setSimulated(edit.field, undoing && edit.wasSimulated)
        if (undoing) {
          journal.value = journal.value.filter(item => item !== edit)
        }
        else {
          offers.value = offers.value.filter(item => item !== edit)
          journal.value = [...journal.value, { ...edit, after: cloneDeep(options.fields()[edit.field].value) }]
        }
        written.push(edit.field)
      }
    }
    finally {
      busy.value = false
    }
    return written
  }

  async function accept(field?: string) {
    const choices = [...pending.value.values()].filter(edit => field === undefined || edit.field === field)
    const request = activeRequest
    const applied = await writeChanges(choices)
    if (current(request) && applied.length)
      receipt.value = `${t("page.recorderAira.replaced")}: ${applied.join(", ")}`
  }
  function dismiss(field?: string) {
    if (busy.value || !current(activeRequest))
      return
    offers.value = field === undefined ? [] : offers.value.filter(edit => edit.field !== field)
    receipt.value = ""
  }
  async function undo(field?: string) {
    const changes = [...edits.value.values()].filter(edit => field === undefined || edit.field === field)
    const request = activeRequest
    const reverted = await writeChanges(changes, true)
    if (current(request) && reverted.length)
      receipt.value = `${t("page.recorderAira.undone")}: ${reverted.join(", ")}`
  }

  function begin(chatId?: string): RecorderTurn | undefined {
    if (!canBegin())
      return undefined
    const awaitingReview = pending.value.size > 0
    const originalRevisions = new Map(revisions)
    const before = new Map(Object.entries(options.fields()).map(([key, field]) => [key, cloneDeep(field.value)]))
    const target = {
      form_id: formId,
      request_id: nanoid(),
      version: options.version()!,
      record_id: options.recordId(),
      locale: locale.value === "zh-CN" ? "zh-CN" as const : "en-US" as const,
      filled: [...before].filter(([, value]) => !empty(value)).map(([key]) => key),
      last_applied: chatId && chatId === lastChatId ? [...edits.value.keys()] : [],
    }
    activeRequest = target.request_id
    let consumed = false
    async function apply(proposal: RecorderProposal, serverChatId?: string) {
      if (consumed || !current(target.request_id) || proposal.request_id !== target.request_id || proposal.form_id !== target.form_id)
        return ""
      consumed = true
      showPreviewLink.value = proposal.intent === "simulate"
      if (showPreviewLink.value)
        return ""
      if (proposal.intent !== "fill")
        return ""
      const chatLocale = proposal.reply_locale || target.locale
      if (awaitingReview) {
        receipt.value = t("page.recorderAira.finishReview")
        return t("page.recorderAira.finishReview", {}, { locale: chatLocale })
      }
      const suggestions: RecorderFieldEdit[] = []
      const direct: RecorderFieldEdit[] = []
      const preserved: string[] = []
      const fields = options.fields()
      for (const [field, after] of Object.entries(proposal.values)) {
        const edit = { field, before: before.get(field), after, revision: originalRevisions.get(field), wasSimulated: options.isSimulated(field) }
        if (!before.has(field) || !matches(edit, "before", fields)) {
          preserved.push(field)
          continue
        }
        if (isEqual(recorderValue(edit.before), after)) {
          preserved.push(field)
          continue
        }
        if (!empty(edit.before))
          suggestions.push(edit)
        else
          direct.push(edit)
      }
      if (suggestions.length || direct.length) {
        lastChatId = serverChatId
        journal.value = []
        offers.value = suggestions
      }
      const written = await writeChanges(direct)
      if (!current(target.request_id))
        return ""
      function describe(lang: string) {
        const groups = [
          ["page.recorderAira.filled", written],
          ["page.recorderAira.replace", [...pending.value.keys()]],
          ["page.recorderAira.skipped", proposal.skipped],
          ["page.recorderAira.preserved", preserved],
        ] as const
        return groups.filter(([, names]) => names.length)
          .map(([key, names]) => `${t(key, {}, { locale: lang })} (${names.length}): ${names.join(", ")}`)
          .join("\n") || t("page.recorderAira.noChanges", {}, { locale: lang })
      }
      receipt.value = describe(locale.value)
      return describe(chatLocale)
    }
    return { target, apply }
  }
  provide(recorderTurnKey, { begin, enabled: canBegin })
  function markInput(event: Event) {
    if (!(event.target instanceof Element))
      return
    const owner = event.target.closest<HTMLElement>("[data-recorder-field], [data-rec-focus-key]")
    const field = owner?.dataset.recorderField || owner?.dataset.recFocusKey?.replace(/^var:/, "")
    if (field)
      revisions.set(field, (revisions.get(field) || 0) + 1)
  }
  return { receipt, showPreviewLink, pending, edits, busy, accept, dismiss, undo, markInput, reset }
}
