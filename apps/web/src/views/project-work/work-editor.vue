<script setup lang="ts">
import type { ProjectPerson } from "@/service/api/project-people"
import type { ProjectWork, WorkContent, WorkEvent } from "@/service/api/project-work"
import PeoplePicker from "@/components/project/people-picker.vue"
import { templateError } from "@/service/api/document-templates"
import {
  addWorkActivity,
  blankWork,
  getProjectWork,
  listProjectWork,
  projectWorkHistory,
  projectWorkMembers,
  saveProjectWork,
  workContent,
  workKinds,
  workStates,
} from "@/service/api/project-work"
import { createResearchDocument } from "@/service/api/research-documents"
import { useAuthStore } from "@/store/modules/auth"
import { useDialog } from "naive-ui"
import { useI18n } from "vue-i18n"
import EvidenceLinks from "./evidence-links.vue"
import WorkSnapshot from "./work-snapshot.vue"

const props = defineProps<{
  itemId?: string
  projectId: string
  projectName: string
  labId: string
  people?: ProjectPerson[]
  items: ProjectWork[]
}>()
const emit = defineEmits<{ close: [], saved: [id: string] }>()
const { t } = useI18n()
const auth = useAuthStore()
const dialog = useDialog()
const comparison = ref<ProjectWork>()
const form = ref<WorkContent>(blankWork())
const currentItem = ref<ProjectWork>()
const id = ref(props.itemId || crypto.randomUUID())
const revision = ref(0)
const canWrite = ref(false)
const canApprove = ref(false)
const busy = ref(false)
const loading = ref(true)
const error = ref("")
const notice = ref("")
const panel = ref<"details" | "activity">("details")
const editorElement = ref<HTMLElement>()
const reason = ref("")
const members = ref<{ id: string, name: string, username: string }[]>([])
const events = ref<WorkEvent[]>([])
const eventPage = ref(1)
const eventTotal = ref(0)
const recovered = ref<string>()
const savedContent = ref("")
const dirty = computed(
  () => !loading.value && canWrite.value && JSON.stringify(form.value) !== savedContent.value,
)
const draftKey = computed(
  () => `project-work-draft:${auth.userInfo.id}:${props.projectId}:${props.itemId || "new"}`,
)
const activity = reactive({
  kind: "comment",
  body: "",
  rationale: "",
  scope: "",
  outcome: null as string | null,
  occurred: "",
  supersedes: null as string | null,
  evidence: [] as WorkContent["evidence"],
})
const activityDirty = computed(() => Boolean(
  activity.body.trim() || activity.rationale.trim() || activity.scope.trim()
  || activity.outcome || activity.occurred || activity.supersedes || activity.evidence.length,
))
const pendingActivityKey = computed(() => `${draftKey.value}:activity`)
const unsaved = computed(() => dirty.value || activityDirty.value)
const assignee = computed({
  get: () => form.value.assignee_person_id ? `person:${form.value.assignee_person_id}` : form.value.assignee_user_id ? `user:${form.value.assignee_user_id}` : null,
  set: (value: string | string[] | null) => {
    const selected = typeof value === "string" ? value : ""
    form.value.assignee_person_id = selected.startsWith("person:") ? selected.slice(7) : null
    form.value.assignee_user_id = selected.startsWith("user:") ? selected.slice(5) : null
  },
})
const collaborators = computed({
  get: () => [...form.value.collaborator_ids.map(id => `user:${id}`), ...form.value.collaborator_person_ids.map(id => `person:${id}`)],
  set: (value: string | string[] | null) => {
    const selected = Array.isArray(value) ? value : []
    form.value.collaborator_ids = selected.filter(v => v.startsWith("user:")).map(v => v.slice(5))
    form.value.collaborator_person_ids = selected.filter(v => v.startsWith("person:")).map(v => v.slice(7))
  },
})

const dependencyMatches = ref<ProjectWork[]>([])
let dependencySearch = 0
async function searchDependencies(q = "") {
  const ticket = ++dependencySearch
  try {
    const result = await listProjectWork({ project_id: props.projectId, q, page_size: 100 })
    if (ticket === dependencySearch)
      dependencyMatches.value = result.items
  }
  catch {
    error.value = t("page.projectWork.failed")
  }
}
const dependencyOptions = computed(() =>
  [...new Map([...props.items, ...dependencyMatches.value].map(item => [item.id, item])).values()]
    .filter(item => item.id !== id.value)
    .map(item => ({
      value: item.id,
      label: `${item.title} · ${t(`page.projectWork.states.${item.state}`)}`,
    })),
)
function options<T extends readonly string[]>(values: T, key: string) {
  return values.map(value => ({ value, label: t(`${key}.${value}`) }))
}
const outcomes = computed(() =>
  activity.kind === "decision"
    ? ["proposed", ...(canApprove.value ? ["adopted"] : [])]
    : activity.kind === "test"
      ? ["passed", "failed", "inconclusive"]
      : activity.kind === "acceptance"
        ? ["accepted", "rejected"]
        : [],
)
let saveRequest: { signature: string, id: string } | undefined
let activityRequest: { signature: string, id: string } | undefined
let documentId: string | undefined
const showDocument = ref(false)
const documentTitle = ref("")

function storeDraft() {
  if (loading.value || !canWrite.value)
    return
  try {
    if (dirty.value) {
      localStorage.setItem(
        draftKey.value,
        JSON.stringify({
          id: id.value,
          revision: revision.value,
          form: form.value,
          reason: reason.value,
        }),
      )
    }
    else {
      localStorage.removeItem(draftKey.value)
    }
    if (activityDirty.value)
      localStorage.setItem(pendingActivityKey.value, JSON.stringify(activity))
    else localStorage.removeItem(pendingActivityKey.value)
  }
  catch {
    /* Storage can be unavailable; keep the in-memory form and navigation guard. */
  }
}
function restoreDraft() {
  try {
    const draft = JSON.parse(recovered.value!)
    form.value = { ...blankWork(), ...draft.form }
    revision.value = draft.revision
    id.value = draft.id
    reason.value = draft.reason || ""
    recovered.value = undefined
    notice.value = t("page.projectWork.restored")
  }
  catch {
    error.value = t("page.projectWork.failed")
  }
}
async function history(reset = false) {
  if (!revision.value)
    return
  if (reset)
    eventPage.value = 1
  const result = await projectWorkHistory(id.value, eventPage.value)
  events.value = reset ? result.events : [...events.value, ...result.events]
  eventTotal.value = result.total
}
async function moreHistory() {
  eventPage.value++
  try {
    await history()
  }
  catch {
    eventPage.value--
    error.value = t("page.projectWork.failed")
  }
}
async function load() {
  loading.value = true
  error.value = ""
  try {
    members.value = (await projectWorkMembers(props.projectId)).members
    if (props.itemId) {
      const item = await getProjectWork(props.itemId)
      if (item.project_id !== props.projectId)
        throw new Error(t("page.projectWork.wrongProject"))
      currentItem.value = item
      form.value = workContent(item)
      revision.value = item.revision
      canWrite.value = Boolean(item.can_write)
      canApprove.value = Boolean(item.can_approve)
      await history(true)
    }
    else {
      canWrite.value = true
    }
    savedContent.value = JSON.stringify(form.value)
    if (canWrite.value) {
      try {
        recovered.value = localStorage.getItem(draftKey.value) || undefined
        const cached = localStorage.getItem(pendingActivityKey.value)
        if (cached)
          Object.assign(activity, JSON.parse(cached))
      }
      catch {
        /* Optional local recovery. */
      }
    }
  }
  catch (err) {
    error.value = templateError(err, t("page.projectWork.failed"))
  }
  finally {
    loading.value = false
  }
}
async function save() {
  if (busy.value || !canWrite.value)
    return
  error.value = ""
  notice.value = ""
  const missing = !form.value.title.trim()
    ? ["titleRequired", "work-title"]
    : form.value.state === "blocked" && !form.value.blocker.trim()
      ? ["blockerRequired", "work-blocker"]
      : form.value.state === "done" && !form.value.acceptance.trim()
        ? ["acceptanceRequired", "work-acceptance"]
        : revision.value && !reason.value.trim()
          ? ["reasonRequired", "work-change-reason"]
          : null
  if (missing) {
    error.value = t(`page.projectWork.${missing[0]}`)
    panel.value = "details"
    await nextTick()
    const field = editorElement.value?.querySelector<HTMLInputElement | HTMLTextAreaElement>(`[data-testid="${missing[1]}"] input, [data-testid="${missing[1]}"] textarea`)
    field?.focus()
    field?.scrollIntoView({ block: "center", behavior: "smooth" })
    return
  }
  if (form.value.evidence.some(item => item.available === false)) {
    error.value = t("page.projectWork.unavailableSave")
    return
  }
  const signature = JSON.stringify([form.value, revision.value, reason.value])
  if (saveRequest?.signature !== signature)
    saveRequest = { signature, id: crypto.randomUUID() }
  busy.value = true
  try {
    const result = await saveProjectWork(
      form.value,
      id.value,
      props.projectId,
      revision.value,
      saveRequest.id,
      reason.value,
    )
    form.value = workContent(result)
    revision.value = result.revision
    savedContent.value = JSON.stringify(form.value)
    reason.value = ""
    storeDraft()
    notice.value = t("page.projectWork.saved", { name: props.projectName })
    const current = await getProjectWork(id.value)
    canWrite.value = Boolean(current.can_write)
    canApprove.value = Boolean(current.can_approve)
    await history(true)
    emit("saved", id.value)
  }
  catch (err) {
    error.value = templateError(err, t("page.projectWork.failed"))
  }
  finally {
    busy.value = false
  }
}
async function postActivity() {
  if (busy.value || dirty.value || !canWrite.value || !revision.value || !activity.body.trim())
    return
  if (activity.evidence.some(item => item.available === false)) {
    error.value = t("page.projectWork.unavailableSave")
    return
  }
  const signature = JSON.stringify([activity, revision.value])
  if (activityRequest?.signature !== signature)
    activityRequest = { signature, id: crypto.randomUUID() }
  busy.value = true
  error.value = ""
  try {
    const result = await addWorkActivity(id.value, {
      request_id: activityRequest.id,
      expected_revision: revision.value,
      kind: activity.kind,
      body: activity.body,
      rationale: activity.rationale,
      scope: activity.scope,
      outcome: activity.outcome,
      occurred_at: activity.occurred ? new Date(activity.occurred).toISOString() : null,
      supersedes: activity.supersedes,
      evidence: activity.evidence,
    })
    revision.value = result.revision
    Object.assign(activity, {
      body: "",
      rationale: "",
      scope: "",
      outcome: null,
      occurred: "",
      supersedes: null,
      evidence: [],
    })
    storeDraft()
    await history(true)
    notice.value = t("page.projectWork.activitySaved")
    emit("saved", id.value)
  }
  catch (err) {
    error.value = templateError(err, t("page.projectWork.failed"))
  }
  finally {
    busy.value = false
  }
}
async function reloadRevision() {
  try {
    const latest = await getProjectWork(id.value)
    // Keep local content and show server content for an explicit comparison.
    comparison.value = latest
  }
  catch (err) {
    error.value = templateError(err, t("page.projectWork.failed"))
  }
}
function acceptComparison() {
  revision.value = comparison.value!.revision
  comparison.value = undefined
  notice.value = t("page.projectWork.compareAccepted")
}
function confirmLeave(): Promise<boolean> {
  return new Promise((resolve) => {
    dialog.warning({
      title: t("page.projectWork.unsaved"),
      content: t("page.projectWork.leave"),
      positiveText: t("common.confirm"),
      negativeText: t("common.cancel"),
      onPositiveClick: () => resolve(true),
      onNegativeClick: () => resolve(false),
      onClose: () => resolve(false),
      onMaskClick: () => resolve(false),
    })
  })
}
async function requestClose() {
  if (busy.value)
    return
  storeDraft()
  if (!unsaved.value || (await confirmLeave()))
    emit("close")
}
function beforeUnload(event: BeforeUnloadEvent) {
  if (unsaved.value) {
    storeDraft()
    event.preventDefault()
    event.returnValue = ""
  }
}
onBeforeRouteLeave(async () => {
  storeDraft()
  return !unsaved.value || (await confirmLeave())
})
watch([form, reason, activity], storeDraft, { deep: true })
watch(
  () => activity.kind,
  () => {
    activity.outcome = null
    activity.supersedes = null
  },
  { flush: "sync" },
)
onMounted(() => {
  void load()
  window.addEventListener("beforeunload", beforeUnload)
})
onBeforeUnmount(() => window.removeEventListener("beforeunload", beforeUnload))
async function createPlan() {
  if (busy.value)
    return
  busy.value = true
  error.value = ""
  documentId ||= crypto.randomUUID()
  try {
    const doc = await createResearchDocument({
      id: documentId,
      scope_type: "project",
      project_id: props.projectId,
      lab_id: props.labId,
      title: documentTitle.value.trim() || form.value.title,
      kind: "document",
      body: `# ${form.value.title}\n\n${form.value.goal}\n`,
    })
    if (!form.value.evidence.some(link => link.id === doc.id)) {
      form.value.evidence.push({
        kind: "document",
        id: doc.id,
        version: String(doc.revision),
        label: doc.title,
        available: true,
      })
    }
    showDocument.value = false
    documentId = undefined
    notice.value = t("page.projectWork.documentCreated")
  }
  catch (err) {
    error.value = templateError(err, t("page.projectWork.failed"))
  }
  finally {
    busy.value = false
  }
}
</script>

<template>
  <n-drawer
    :show="true"
    :width="760"
    class="max-w-full"
    :mask-closable="false"
    @update:show="requestClose"
  >
    <n-drawer-content
      data-testid="work-editor"
      :title="itemId ? t('page.projectWork.detail') : t('page.projectWork.new')"
      closable
    >
      <n-spin :show="loading">
        <div ref="editorElement" class="space-y-4">
          <p class="m-0 text-sm text-gray-500">{{
            t("page.projectWork.destination", { name: projectName })
          }}</p>
          <p v-if="!revision && !loading" class="m-0 rounded-lg bg-blue-50 p-3 text-sm text-blue-800">{{ t("page.projectWork.quickStartHint") }}</p>
          <div v-if="revision" class="flex gap-2 border-b border-gray-200 pb-3" role="group" :aria-label="t('page.projectWork.detail')">
            <n-button :type="panel === 'details' ? 'primary' : 'default'" :aria-pressed="panel === 'details'" data-testid="work-details-tab" @click="panel = 'details'">{{ t("page.projectWork.detailsTab") }}</n-button>
            <n-button :type="panel === 'activity' ? 'primary' : 'default'" :aria-pressed="panel === 'activity'" data-testid="work-activity-tab" @click="panel = 'activity'">{{ t("page.projectWork.activityTab") }}</n-button>
          </div>
          <n-alert v-if="recovered" type="warning">
            {{ t("page.projectWork.localDraft") }}
            <n-button size="small" @click="restoreDraft">{{
              t("page.projectWork.restore")
            }}</n-button>
          </n-alert>
          <n-alert v-if="error" type="error" data-testid="work-error"
          >{{ error }}
            <n-button v-if="revision" size="small" @click="reloadRevision">{{
              t("page.projectWork.compare")
            }}</n-button></n-alert
          >
          <p v-if="notice" role="status" class="text-green-700">{{ notice }}</p>
          <work-snapshot v-if="!loading && !canWrite && currentItem" v-show="panel === 'details'" :item="currentItem" :members="members" :people="people" :items="items" :project-id="projectId" />
          <form v-if="canWrite" v-show="panel === 'details'" class="space-y-4" @submit.prevent="save">
            <fieldset :disabled="!canWrite || busy" class="m-0 min-w-0 border-0 p-0 space-y-4">
              <label class="block"
              >{{ t("page.projectWork.titleLabel") }} *<n-input
                :disabled="!canWrite || busy"
                v-model:value="form.title"
                data-testid="work-title"
                :maxlength="255"
              /></label>
              <div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <label
                >{{ t("page.projectWork.kind")
                }}<n-select
                  :disabled="!canWrite || busy"
                  v-model:value="form.kind"
                  :options="options(workKinds, 'page.projectWork.kinds')"
                /></label>
                <label
                >{{ t("page.projectWork.state")
                }}<n-select
                  :disabled="!canWrite || busy"
                  v-model:value="form.state"
                  data-testid="work-state"
                  :options="options(workStates, 'page.projectWork.states')"
                /></label>
                <label
                >{{ t("page.projectWork.priority")
                }}<n-select
                  :disabled="!canWrite || busy"
                  v-model:value="form.priority"
                  :options="
                    options(['low', 'normal', 'high', 'urgent'], 'page.projectWork.priorities')
                  "
                /></label>
              </div>
              <label class="block"
              >{{ t("page.projectWork.goal")
              }}<n-input
                :disabled="!canWrite || busy"
                v-model:value="form.goal"
                type="textarea"
                :autosize="{ minRows: 3, maxRows: 12 }"
              /></label>
              <label class="block"
              >{{ t("page.projectWork.acceptance")
              }}<n-input
                :disabled="!canWrite || busy"
                v-model:value="form.acceptance"
                data-testid="work-acceptance"
                type="textarea"
                :autosize="{ minRows: 2, maxRows: 6 }"
              /></label>
              <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <label
                >{{ t("page.projectWork.assignee")
                }}<people-picker v-model="assignee" :project-id="projectId" :members="members" :disabled="!canWrite || busy" data-testid="work-assignee" /></label>
                <label
                >{{ t("page.projectWork.collaborators")
                }}<people-picker v-model="collaborators" :project-id="projectId" :members="members" multiple :disabled="!canWrite || busy" /></label>
                <label
                >{{ t("page.projectWork.start")
                }}<input v-model="form.planned_start" type="date" class="work-date"
                /></label>
                <label
                >{{ t("page.projectWork.end")
                }}<input v-model="form.planned_end" type="date" class="work-date"
                /></label>
              </div>
              <label class="block">{{ t("page.projectWork.deadlineNote") }}<n-input v-model:value="form.deadline_note" :maxlength="1000" /></label>
              <label v-if="form.state === 'blocked' || form.blocker" class="block"
              >{{ t("page.projectWork.blocker") }} *<n-input
                :disabled="!canWrite || busy"
                v-model:value="form.blocker"
                data-testid="work-blocker"
                type="textarea"
              /></label>
              <label class="block"
              >{{ t("page.projectWork.nextStep")
              }}<n-input
                :disabled="!canWrite || busy"
                v-model:value="form.next_step"
                type="textarea"
                :autosize="{ minRows: 2, maxRows: 4 }"
              /></label>
              <label class="block"
              >{{ t("page.projectWork.dependencies")
              }}<n-select
                :disabled="!canWrite || busy"
                v-model:value="form.dependency_ids"
                multiple
                filterable
                clearable
                :options="dependencyOptions"
                remote
                @search="searchDependencies"
                @focus="searchDependencies()"
              /></label>
              <section class="rounded border border-gray-200 p-3">
                <div class="mb-3 flex flex-wrap items-center justify-between gap-2"
                ><strong>{{ t("page.projectWork.evidence") }}</strong
                ><n-button size="small" @click="showDocument = true">{{
                  t("page.projectWork.createDocument")
                }}</n-button></div
                >
                <evidence-links
                  v-model="form.evidence"
                  :project-id="projectId"
                  :editable="canWrite && !busy"
                />
              </section>
              <label v-if="revision" class="block"
              >{{ t("page.projectWork.changeReason") }} *<n-input
                :disabled="!canWrite || busy"
                v-model:value="reason"
                data-testid="work-change-reason"
              /></label>
            </fieldset>
            <p v-if="form.state === 'done'" class="text-sm text-gray-500">{{
              t("page.projectWork.completionHint")
            }}</p>
          </form>
          <section v-if="revision" v-show="panel === 'activity'" class="space-y-3" data-testid="work-activity-panel">
            <form v-if="canWrite" class="space-y-3" @submit.prevent="postActivity">
              <n-select
                :disabled="!canWrite || busy"
                v-model:value="activity.kind"
                data-testid="work-activity-kind"
                :options="
                  options(
                    [
                      'comment',
                      'progress',
                      'decision',
                      'test',
                      ...(canApprove ? ['acceptance'] : []),
                    ],
                    'page.projectWork.events',
                  )
                "
              />
              <n-input
                :disabled="!canWrite || busy"
                v-model:value="activity.body"
                type="textarea"
                :placeholder="t('page.projectWork.activityBody')"
                data-testid="work-activity-body"
              />
              <label class="block"
              >{{ t("page.projectWork.occurredAt")
              }}<input v-model="activity.occurred" type="datetime-local" class="work-date"
              /></label>
              <template v-if="outcomes.length">
                <n-select
                  :disabled="!canWrite || busy"
                  v-model:value="activity.outcome"
                  data-testid="work-activity-outcome"
                  :options="options(outcomes, 'page.projectWork.outcomes')"
                  :placeholder="t('page.projectWork.result')"
                />
                <n-input
                  :disabled="!canWrite || busy"
                  v-model:value="activity.rationale"
                  type="textarea"
                  :placeholder="t('page.projectWork.rationale')"
                />
                <n-input
                  :disabled="!canWrite || busy"
                  v-if="activity.kind === 'decision'"
                  v-model:value="activity.scope"
                  :placeholder="t('page.projectWork.decisionScope')"
                />
                <n-select
                  :disabled="!canWrite || busy"
                  v-if="activity.kind === 'decision'"
                  v-model:value="activity.supersedes"
                  clearable
                  :placeholder="t('page.projectWork.supersedes')"
                  :options="
                    events
                      .filter(e => e.kind === 'decision')
                      .map(e => ({ value: e.id, label: e.payload.body || e.id }))
                  "
                />
              </template>
              <evidence-links v-model="activity.evidence" :project-id="projectId" editable />
              <n-alert v-if="dirty" type="warning">
                {{ t("page.projectWork.saveFirst") }}
                <n-button size="small" @click="panel = 'details'">{{ t("page.projectWork.backToDetails") }}</n-button>
              </n-alert>
            </form>
            <p v-if="!events.some(event => !['created', 'updated'].includes(event.kind))" class="text-sm text-gray-500">{{ t("page.projectWork.activityEmpty") }}</p>
            <ol class="m-0 mt-5 list-none p-0 space-y-4">
              <li
                v-for="event in events"
                :key="event.id"
                class="border-l-2 border-gray-200 pl-3"
                data-testid="work-event"
              >
                <div class="flex flex-wrap gap-x-2 text-sm"
                ><strong>{{ t(`page.projectWork.events.${event.kind}`) }}</strong
                ><span>{{ event.actor }}</span
                ><time>{{ new Date(event.created_at).toLocaleString() }}</time></div
                >
                <p v-if="event.payload.outcome" class="font-semibold">{{
                  t(`page.projectWork.outcomes.${event.payload.outcome}`)
                }}</p>
                <p v-if="event.payload.body" class="whitespace-pre-wrap break-words">{{
                  event.payload.body
                }}</p>
                <p v-if="event.payload.occurred_at" class="text-sm text-gray-500"
                >{{ t("page.projectWork.occurredAt") }}:
                  {{ new Date(event.payload.occurred_at).toLocaleString() }}</p
                >
                <p v-if="event.payload.rationale" class="whitespace-pre-wrap">{{
                  event.payload.rationale
                }}</p>
                <p v-if="event.payload.scope"
                >{{ t("page.projectWork.decisionScope") }}: {{ event.payload.scope }}</p
                >
                <p v-if="event.payload.supersedes" class="text-sm"
                >{{ t("page.projectWork.replacesDecision") }} {{ events.find(previous => previous.id === event.payload.supersedes)?.payload.body || t('page.projectWork.earlierDecision') }}</p
                >
                <evidence-links
                  v-if="event.payload.evidence"
                  :model-value="event.payload.evidence"
                  :project-id="projectId"
                />
                <details v-if="event.payload.snapshot"
                ><summary
                >{{
                  t("page.projectWork.version", { revision: event.payload.snapshot.revision })
                }}
                  · {{ event.payload.reason }}</summary
                ><work-snapshot :item="event.payload.snapshot" :members="members" :items="items" :project-id="projectId" />
                </details>
              </li>
            </ol>
            <n-button
              v-if="events.length < eventTotal"
              class="mt-3"
              @click="moreHistory"
            >{{ t("page.projectWork.more") }}</n-button
            >
          </section>
        </div>
      </n-spin>
      <template v-if="canWrite && !loading" #footer>
        <div class="w-full flex flex-wrap items-center justify-between gap-3" data-testid="work-editor-footer">
          <span class="text-sm text-gray-500">{{
            !revision ? t("page.projectWork.notCreated") : unsaved ? t("page.projectWork.unsaved") : t("page.projectWork.version", { revision })
          }}</span>
          <n-button v-if="panel === 'details'" type="primary" :loading="busy" data-testid="work-save" @click="save">{{ t(revision ? "common.save" : "page.projectWork.newSave") }}</n-button>
          <n-button v-else type="primary" :disabled="dirty || !activity.body.trim()" :loading="busy" data-testid="work-activity-save" @click="postActivity">{{ t("page.projectWork.post") }}</n-button>
        </div>
      </template>
    </n-drawer-content>
  </n-drawer>
  <n-modal
    :show="Boolean(comparison)"
    preset="card"
    class="aira-dialog max-w-3xl"
    :title="t('page.projectWork.compare')"
    :aria-label="t('page.projectWork.compare')"
    @update:show="comparison = undefined"
  >
    <p>{{ t("page.projectWork.compareHint") }}</p>
    <work-snapshot v-if="comparison" :item="comparison" :members="members" :items="items" :project-id="projectId" class="max-h-50vh overflow-auto" />
    <n-button type="primary" @click="acceptComparison">{{
      t("page.projectWork.keepMine")
    }}</n-button>
  </n-modal>
  <n-modal
    v-model:show="showDocument"
    preset="card"
    class="aira-dialog max-w-xl"
    :title="t('page.projectWork.createDocument')"
    :aria-label="t('page.projectWork.createDocument')"
  >
    <p>{{ t("page.projectWork.documentHint") }}</p>
    <n-input v-model:value="documentTitle" :placeholder="form.title" />
    <n-button type="primary" class="mt-3" :loading="busy" @click="createPlan">{{
      t("page.projectWork.createDocument")
    }}</n-button>
  </n-modal>
</template>

<style scoped>
.work-date {
  display: block;
  width: 100%;
  min-width: 0;
  border: 1px solid #d1d5db;
  border-radius: 4px;
  padding: 7px 10px;
  background: white;
  color: inherit;
  box-sizing: border-box;
}
</style>
