<script setup lang="ts">
import type {
  DocumentContent,
  DocumentPreview,
  DocumentRevision,
  DocumentValidation,
  Material,
  ResearchDocument,
} from "@/service/api/research-documents"
import type { AimdProtocolRecordData } from "@airalogy/aimd-recorder"
import DocumentMarkdown from "@/components/common/document-markdown.vue"
import { useConfirmDocumentChange } from "@/composables/useConfirmDocumentChange"
import { useOrganizationTranslation } from "@/composables/useOrganizationTranslation"
import { fetchResearchFile } from "@/service/api/knowledge"
import {
  createResearchDocument,
  deriveResearchDocument,
  downloadResearchDocument,
  getResearchDocument,
  previewResearchDocument,
  researchDocumentHistory,
  researchDocumentSubmissions,
  restoreResearchDocument,
  saveResearchDocument,
  submitResearchDocument,
  validateResearchDocument,
} from "@/service/api/research-documents"
import { documentBrowseQuery, documentDateInstant, localDocumentDate } from "@/utils/documentBrowse"
import { downloadBlob } from "@/utils/downloadBlob"
import { preserveVisualFenceMetadata } from "@/utils/recorderMarkdown"
import { createResearchDocumentId } from "@/utils/research-document-id"
import { AimdEditor } from "@airalogy/aimd-editor/vue"
import { AimdRecorderWysiwygSurface } from "@airalogy/aimd-recorder"
import { useDialog } from "naive-ui"
import { useI18n } from "vue-i18n"
import { onBeforeRouteLeave, onBeforeRouteUpdate } from "vue-router"
import DocumentAudience from "./document-audience.vue"
import MaterialLibrary from "./material-library.vue"
import SnapshotPreview from "./snapshot-preview.vue"
import TemplateEditorDialog from "./template-editor-dialog.vue"

const { locale } = useI18n()
const { t } = useOrganizationTranslation()
const route = useRoute()
const router = useRouter()
const dialog = useDialog()
const confirmChange = useConfirmDocumentChange()
const doc = ref<ResearchDocument>()
const form = ref<DocumentContent>()
const mode = ref<"source" | "wysiwyg">("wysiwyg")
const surfaceRevision = ref(0)
const visualSurface = ref<InstanceType<typeof AimdRecorderWysiwygSurface>>()
const visualPending = ref(false)
let visualLastMarkdown: string | undefined
const loading = ref(true)
const saving = ref(false)
const busy = ref(false)
const error = ref("")
const notice = ref("")
const savedHash = ref("")
const changePreview = ref<DocumentPreview>()
const submitPreview = ref<DocumentPreview>()
const restorePreview = ref<{ revision: number, preview: DocumentPreview }>()
const validation = ref<DocumentValidation>()
const revisions = ref<DocumentRevision[]>()
const submissions = ref<Awaited<ReturnType<typeof researchDocumentSubmissions>>["items"]>()
const templateDestination = ref<{ lab_id?: string, project_id?: string }>()
const showDetails = ref(false)
const moreOpen = ref(false)
const resultsOpen = ref(false)
const saveError = ref(false)
const showTemplate = ref(false)
const showMaterials = ref(false)
const showField = ref(false)
const showValues = ref(false)
const valueRows = computed(() =>
  Object.entries(form.value?.record_data || {}).flatMap(([scope, fields]) =>
    Object.entries(fields || {}).map(([field, value]) => ({ scope, field, value })),
  ),
)
const field = reactive({ id: "", title: "", type: "str", unit: "" })
const derive = ref<{
  kind: "protocol" | "knowledge"
  title: string
  body: string
  preview?: DocumentPreview
  result?: { id?: string, knowledge_id?: string }
}>()
let timeout: ReturnType<typeof setTimeout> | undefined
let generation = 0
const denyCollector = () => false
const fingerprint = (value: unknown) => JSON.stringify(value)
const dirty = computed(() => Boolean(visualPending.value || (form.value && fingerprint(form.value) !== savedHash.value)))
const scope = computed(() =>
  doc.value
    ? {
        scope_type: doc.value.scope_type,
        lab_id: doc.value.lab_id || undefined,
        project_id: doc.value.project_id || undefined,
      }
    : undefined,
)
const editable = computed(() => Boolean(doc.value?.can_edit))
const returnTarget = computed(() => ({ name: "research-documents" as const, query: { tab: "documents", ...documentBrowseQuery(route.query), ...(doc.value?.project_id ? { project_id: doc.value.project_id } : doc.value?.lab_id ? { lab_id: doc.value.lab_id } : {}) } }))
function changeDate(day: string) {
  if (!form.value || !editable.value)
    return
  const instant = documentDateInstant(day, form.value.occurred_at)
  if (!instant) {
    error.value = t("page.documentBrowse.invalidDate")
    return
  }
  form.value.occurred_at = instant
}
const fieldTypes = computed(() =>
  ([
    ["str", "string"],
    ["float", "number"],
    ["int", "integer"],
    ["bool", "boolean"],
    ["date", "date"],
  ] as const).map(([value, key]) => ({ value, label: t(`page.researchDocuments.${key}`) })),
)

function contentOf(value: ResearchDocument): DocumentContent {
  return {
    title: value.title,
    kind: value.kind,
    body: value.body,
    body_format: value.body_format || "aimd",
    record_data: {
      var: value.record_data.var || {},
      step: value.record_data.step || {},
      check: value.record_data.check || {},
      quiz: value.record_data.quiz || {},
    },
    file_ids: [...value.file_ids],
    tags: [...value.tags],
    collection: value.collection,
    occurred_at: value.occurred_at,
  }
}
function apply(value: ResearchDocument) {
  visualPending.value = false
  visualLastMarkdown = undefined
  doc.value = value
  form.value = contentOf(value)
  savedHash.value = fingerprint(form.value)
  surfaceRevision.value++
  validation.value = undefined
  error.value = ""
  saveError.value = false
}
function fail(err: unknown) {
  const response = (err as { response?: { status?: number, data?: { detail?: unknown } } })
    ?.response
  const detail = response?.data?.detail
  if (detail && typeof detail === "object" && "errors" in detail)
    validation.value = detail as DocumentValidation
  error.value
    = typeof detail === "string"
      ? detail
      : response?.status === 409
        ? t("page.researchDocuments.changedElsewhere")
        : t("page.researchDocuments.failed")
}
async function load() {
  const ticket = ++generation
  clearTimeout(timeout)
  loading.value = true
  doc.value = undefined
  form.value = undefined
  error.value = ""
  changePreview.value = undefined
  submitPreview.value = undefined
  restorePreview.value = undefined
  revisions.value = undefined
  derive.value = undefined
  try {
    const value = await getResearchDocument(String(route.params.documentId))
    if (ticket === generation)
      apply(value)
  }
  catch (err) {
    if (ticket === generation)
      fail(err)
  }
  finally {
    if (ticket === generation)
      loading.value = false
  }
}
function scheduleSave() {
  clearTimeout(timeout)
  if (dirty.value && editable.value && !changePreview.value && !submitPreview.value)
    timeout = setTimeout(() => void save(), 1400)
}
// Milkdown emits serialized content after a short debounce. Read its current
// state before a save/navigation, so a final keystroke cannot be discarded.
interface VisualEditor { action: (read: (ctx: { get: (name: string) => any }) => string) => string }
function readVisualMarkdown(editor: VisualEditor) {
  return editor.action((ctx) => {
    const view = ctx.get("editorView")
    return ctx.get("serializer")(view.state.doc) as string
  })
}
function onVisualReady({ milkdown }: { milkdown: VisualEditor }) {
  // The initial serializer output may normalize whitespace. Viewing a document
  // alone must not create a revision or rewrite its original Markdown.
  visualLastMarkdown = readVisualMarkdown(milkdown)
}
function flushVisualContent() {
  if (mode.value !== "wysiwyg" || !editable.value)
    return
  const editor = visualSurface.value?.getEditor?.()
  if (!editor)
    return
  const markdown = readVisualMarkdown(editor)
  if (markdown !== visualLastMarkdown)
    updateBody(markdown, true)
  else
    visualPending.value = false
}
function markVisualInput(event: Event) {
  const target = event.target as HTMLElement
  if (editable.value && target.matches(".ProseMirror[contenteditable=true]"))
    visualPending.value = true
}
async function save(confirmImpact = false): Promise<boolean> {
  flushVisualContent()
  if (!doc.value || !form.value || !editable.value || saving.value)
    return false
  if (!dirty.value)
    return true
  clearTimeout(timeout)
  saving.value = true
  saveError.value = false
  error.value = ""
  const id = doc.value.id
  const content = structuredClone(toRaw(form.value))
  const hash = fingerprint(content)
  const revision = doc.value.revision
  try {
    const preview = await previewResearchDocument(id, { ...content, expected_revision: revision })
    if (
      preview.impact?.requires_confirmation
      && (!confirmImpact || preview.preview_digest !== changePreview.value?.preview_digest)
    ) {
      changePreview.value = preview
      return false
    }
    const result = await saveResearchDocument(id, {
      ...content,
      expected_revision: revision,
      preview_digest: preview.preview_digest,
    })
    if (doc.value?.id !== id)
      return false
    // A late save response updates the revision, never newer in-flight typing.
    doc.value = result
    savedHash.value = hash
    changePreview.value = undefined
    notice.value = ""
    return true
  }
  catch (err) {
    saveError.value = true
    fail(err)
    return false
  }
  finally {
    saving.value = false
    if (dirty.value && !error.value && !changePreview.value)
      scheduleSave()
  }
}
function updateBody(content: string, visual = false) {
  if (!form.value || !editable.value)
    return
  try {
    form.value.body = visual ? preserveVisualFenceMetadata(form.value.body, content) : content
    visualPending.value = false
    if (visual)
      visualLastMarkdown = content
    validation.value = undefined
  }
  catch (err) {
    mode.value = "source"
    fail(err)
  }
}
function updateValues(value: AimdProtocolRecordData) {
  if (!form.value || !editable.value)
    return
  // Keep removed fields' values until an explicit reviewed edit, rather than
  // letting a renderer refresh silently discard scientific data.
  const previous = form.value.record_data
  form.value.record_data = {
    var: { ...previous.var, ...value.var },
    step: { ...previous.step, ...value.step },
    check: { ...previous.check, ...value.check },
    quiz: { ...previous.quiz, ...value.quiz },
  }
  validation.value = undefined
}
function switchMode(value: "source" | "wysiwyg") {
  flushVisualContent()
  mode.value = value
  if (value === "wysiwyg")
    surfaceRevision.value++
}
async function check() {
  if (!doc.value || !(await save()))
    return
  busy.value = true
  try {
    validation.value = await validateResearchDocument(doc.value.id)
  }
  catch (err) {
    fail(err)
  }
  finally {
    busy.value = false
  }
}
async function submit(confirm = false) {
  if (!doc.value || !(await save()))
    return
  busy.value = true
  try {
    const result = await submitResearchDocument(
      doc.value.id,
      doc.value.revision,
      confirm ? submitPreview.value?.preview_digest : undefined,
    )
    if (result.requires_confirmation) {
      submitPreview.value = result
    }
    else {
      submitPreview.value = undefined
      doc.value.state = "submitted"
      notice.value = t("page.researchDocuments.submissionSuccess")
    }
  }
  catch (err) {
    submitPreview.value = undefined
    fail(err)
  }
  finally {
    busy.value = false
  }
}
async function showSubmissions() {
  if (!doc.value)
    return
  try {
    submissions.value = (await researchDocumentSubmissions(doc.value.id)).items
  }
  catch (err) { fail(err) }
}
async function history() {
  if (!doc.value)
    return
  try {
    revisions.value = (await researchDocumentHistory(doc.value.id)).items
  }
  catch (err) {
    fail(err)
  }
}
async function restore(revision: number, confirm = false) {
  if (!doc.value || !(await save()))
    return
  busy.value = true
  try {
    const result = await restoreResearchDocument(
      doc.value.id,
      revision,
      doc.value.revision,
      confirm ? restorePreview.value?.preview.preview_digest : undefined,
    )
    if ("requires_confirmation" in result) {
      restorePreview.value = { revision, preview: result }
    }
    else if ("record_data" in result) {
      apply(result)
      restorePreview.value = undefined
      revisions.value = undefined
    }
  }
  catch (err) {
    fail(err)
  }
  finally {
    busy.value = false
  }
}
async function saveAsTemplate() {
  if (!doc.value || (editable.value && !(await save())))
    return
  showTemplate.value = true
}
async function copy() {
  if (!doc.value || !scope.value || !(await save()))
    return
  busy.value = true
  try {
    const result = await createResearchDocument({
      ...scope.value,
      id: createResearchDocumentId(),
      title: doc.value.title,
      kind: doc.value.kind,
      source_document_id: doc.value.id,
    })
    await router.push({ name: "research-document-detail", params: { documentId: result.id } })
  }
  catch (err) {
    fail(err)
  }
  finally {
    busy.value = false
  }
}
function addField() {
  if (!form.value)
    return
  if (!/^[a-z]\w*$/i.test(field.id)) {
    error.value = t("page.researchDocuments.newFieldInvalid")
    return
  }
  const extras = `${field.title ? `, title=${JSON.stringify(field.title)}` : ""}${field.unit ? `, unit=${JSON.stringify(field.unit)}` : ""}`
  form.value.body += `\n\n${field.title || field.id}: {{var|${field.id}: ${field.type}${extras}}}\n`
  surfaceRevision.value++
  showField.value = false
  field.id = ""
  field.title = ""
  field.unit = ""
}
function attach(item: Material) {
  if (form.value && !form.value.file_ids.includes(item.id)) {
    form.value.file_ids.push(item.id)
    doc.value?.files.push(item)
  }
}
function removeAttachment(id: string) {
  if (form.value)
    form.value.file_ids = form.value.file_ids.filter(value => value !== id)
}
function removeValue(scope: string, field: string) {
  if (!form.value || !editable.value)
    return
  const values = form.value.record_data[scope as keyof AimdProtocolRecordData]
  delete values[field]
  surfaceRevision.value++
}
async function importSource(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ""
  const content = form.value
  if (!file || !content || !editable.value)
    return
  if (!/\.(?:md|aimd)$/i.test(file.name) || file.size > 800000) {
    error.value = t("page.meetingSpace.invalidFile")
    return
  }
  if (content.body && !(await confirmChange(t("page.meetingSpace.replace"))))
    return
  const format = file.name.toLowerCase().endsWith(".aimd") ? "aimd" : "md"
  if (format === "md" && Object.values(content.record_data).some(group => Object.keys(group || {}).length)) {
    error.value = t("page.meetingSpace.structuredValues")
    return
  }
  const text = await file.text()
  if (content !== form.value || text.length > 200000) {
    error.value = t("page.meetingSpace.invalidFile")
    return
  }
  await switchMode("source")
  content.body_format = format
  updateBody(text)
}
function downloadSource() {
  const content = form.value
  if (content)
    downloadBlob(new Blob([content.body], { type: "text/plain;charset=utf-8" }), `${content.title}.${content.body_format || "aimd"}`)
}
async function downloadAttachment(id: string) {
  try {
    const blob = await fetchResearchFile(id, "download")
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement("a")
    anchor.href = url
    anchor.download = doc.value?.files.find(file => file.id === id)?.filename || "material"
    anchor.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
  catch (err) {
    fail(err)
  }
}
async function download(derivationId?: string) {
  if (!doc.value)
    return
  if (editable.value && !(await save()))
    return
  try {
    const blob = await downloadResearchDocument(doc.value.id, derivationId)
    if (!blob)
      return
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement("a")
    anchor.href = url
    anchor.download = derivationId ? "protocol-draft.zip" : "research-document.zip"
    anchor.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
  catch (err) {
    fail(err)
  }
}
async function deriveAsset(confirm = false) {
  if (!doc.value || !derive.value || !(await save()))
    return
  busy.value = true
  try {
    const result = await deriveResearchDocument(doc.value.id, {
      expected_revision: doc.value.revision,
      kind: derive.value.kind,
      title: derive.value.title,
      body: derive.value.body,
      preview_digest: confirm ? derive.value.preview?.preview_digest : undefined,
    })
    if (result.requires_confirmation)
      derive.value.preview = result
    else derive.value.result = result
  }
  catch (err) {
    fail(err)
  }
  finally {
    busy.value = false
  }
}
function beforeUnload(event: BeforeUnloadEvent) {
  flushVisualContent()
  if (dirty.value) {
    event.preventDefault()
    event.returnValue = ""
  }
}
async function guard() {
  flushVisualContent()
  if (!dirty.value || (await save()))
    return true
  return new Promise<boolean>((resolve) => {
    dialog.warning({
      title: t("page.researchDocuments.unsaved"),
      content: t("page.researchDocuments.leaveUnsaved"),
      positiveText: t("page.researchDocuments.confirm"),
      negativeText: t("common.cancel"),
      onPositiveClick: () => resolve(true),
      onNegativeClick: () => resolve(false),
      onClose: () => resolve(false),
      onMaskClick: () => resolve(false),
    })
  })
}
onBeforeRouteLeave(guard)
onBeforeRouteUpdate(guard)
watch(
  form,
  () => {
    submitPreview.value = undefined
    scheduleSave()
  },
  { deep: true },
)
watch(() => route.params.documentId, load, { immediate: true })
onMounted(() => window.addEventListener("beforeunload", beforeUnload))
onBeforeUnmount(() => {
  generation++
  clearTimeout(timeout)
  window.removeEventListener("beforeunload", beforeUnload)
})
</script>

<template>
  <main
    class="research-document-editor mx-auto max-w-7xl w-full !px-0 !py-4 sm:!p-6"
    data-testid="research-document-editor"
  >
    <n-spin :show="loading">
      <n-alert v-if="error" type="error" class="mb-4" role="alert" data-testid="document-error">
        {{ error }}
      </n-alert>
      <n-button v-if="!doc && !loading" @click="load">
        {{ t("page.researchDocuments.reload") }}
      </n-button>
      <template v-if="doc && form">
        <n-alert v-if="doc.meeting_url" type="info" class="mb-4">
          <router-link :to="doc.meeting_url" class="text-primary">
            {{ t('page.meetings.openMeeting') }}
          </router-link>
        </n-alert>
        <header class="mb-5 space-y-3" data-testid="document-editor-header">
          <div class="flex flex-wrap items-center justify-between gap-3">
            <n-button quaternary data-testid="document-back" @click="router.push(returnTarget)">
              {{ t('page.documentBrowse.backList') }}
            </n-button>
            <div class="flex flex-wrap items-center gap-2">
              <span class="aira-type-meta" :class="{ 'text-red-600': saveError }" role="status" aria-live="polite" data-testid="document-save-state">{{ t(saveError ? 'page.documentUx.saveFailed' : saving ? 'page.researchDocuments.saving' : dirty ? 'page.researchDocuments.unsaved' : 'page.researchDocuments.saved') }}</span>
              <n-button v-if="saveError && editable" size="small" :loading="saving" data-testid="document-save-retry" @click="save()">
                {{ t('common.retry') }}
              </n-button>
              <n-button quaternary :aria-expanded="showDetails" aria-controls="document-details" data-testid="document-details-toggle" @click="showDetails = !showDetails">
                {{ t('page.documentUx.details') }}
              </n-button>
              <n-popover v-model:show="moreOpen" trigger="click" placement="bottom-end">
                <template #trigger>
                  <n-button quaternary data-testid="document-more" :aria-expanded="moreOpen">
                    {{ t('common.more') }}
                  </n-button>
                </template>
                <div class="document-more-actions" @keydown.esc="moreOpen = false">
                  <h3>{{ t('page.documentUx.historyGroup') }}</h3>
                  <n-button quaternary :disabled="saving || busy" @click="moreOpen = false; history()">
                    {{ t('page.researchDocuments.history') }}
                  </n-button>
                  <n-button quaternary :disabled="saving || busy" @click="moreOpen = false; showSubmissions()">
                    {{ t('page.researchDocuments.submittedHistory') }}
                  </n-button>
                  <h3>{{ t('page.documentUx.reuseGroup') }}</h3>
                  <n-button quaternary :disabled="saving || busy" data-testid="save-as-document-template" @click="moreOpen = false; saveAsTemplate()">
                    {{ t('page.documentTemplates.saveAs') }}
                  </n-button>
                  <n-button v-if="editable" quaternary :disabled="saving || busy" @click="moreOpen = false; copy()">
                    {{ t('page.researchDocuments.copy') }}
                  </n-button>
                  <n-button v-if="editable" quaternary :disabled="saving || busy" @click="moreOpen = false; derive = { kind: 'protocol', title: form.title, body: form.body }">
                    {{ t('page.researchDocuments.derive') }}
                  </n-button>
                  <h3>{{ t('page.documentUx.fileGroup') }}</h3>
                  <n-button quaternary :disabled="saving || busy" @click="moreOpen = false; download()">
                    {{ t('page.researchDocuments.export') }}
                  </n-button>
                  <n-button v-if="editable" quaternary :disabled="saving || busy || !dirty" @click="moreOpen = false; save()">
                    {{ t('page.researchDocuments.save') }}
                  </n-button>
                </div>
              </n-popover>
            </div>
          </div>
          <n-input v-model:value="form.title" type="textarea" :autosize="{ minRows: 1, maxRows: 6 }" :maxlength="512" :readonly="!editable" size="large" :bordered="false" class="document-title" :input-props="{ 'aria-label': t('page.researchDocuments.titleLabel') }" data-testid="document-title" />
          <document-audience v-if="scope" compact :scope="scope" :name="doc.scope_name" />
          <div class="flex flex-wrap items-center gap-3 text-sm text-gray-600">
            <label class="flex items-center gap-2">{{ t('page.documentBrowse.recordedDate') }}
              <input type="date" :value="localDocumentDate(form.occurred_at || doc.created_at)" :disabled="!editable || saving" class="max-w-full min-h-9 border rounded px-2" data-testid="document-recorded-date" @change="changeDate(($event.target as HTMLInputElement).value)">
            </label>
            <n-tag v-if="doc.state === 'submitted'" size="small" type="success">
              {{ t('page.researchDocuments.submitted') }}
            </n-tag>
          </div>
        </header>
        <n-alert v-if="!editable" type="info" class="mb-4">
          {{ t("page.researchDocuments.readOnly") }}
        </n-alert>
        <n-alert v-if="notice" type="success" class="mb-4" role="status">
          {{ notice }}
          <router-link v-if="templateDestination" :to="{ name: 'research-documents', query: { tab: 'templates', ...(templateDestination.project_id ? { project_id: templateDestination.project_id } : templateDestination.lab_id ? { lab_id: templateDestination.lab_id } : {}) } }" class="ml-2 text-primary">
            {{ t('page.documentTemplates.library') }}
          </router-link>
        </n-alert>
        <n-alert
          v-if="validation"
          :type="validation.valid ? 'success' : 'warning'"
          class="mb-4"
          role="status"
        >
          {{
            t(
              validation.valid
                ? "page.researchDocuments.valid"
                : "page.researchDocuments.checkErrors",
            )
          }}
          <ul v-if="validation.errors.length">
            <li v-for="(issue, index) in validation.errors" :key="index">
              <code>{{ issue.field }}</code>: {{ issue.message }}
            </li>
          </ul>
        </n-alert>
        <div class="document-columns" :class="{ 'document-columns--details': showDetails }">
          <section
            class="min-w-0 border border-gray-200 rounded-xl bg-white p-3 sm:p-5"
            :aria-label="t('page.researchDocuments.bodyLabel')"
          >
            <div class="mb-3 flex flex-wrap items-center gap-2">
              <label v-if="editable">{{ t("page.meetingSpace.format") }}
                <select v-model="form.body_format" :disabled="Object.values(form.record_data).some(group => Object.keys(group || {}).length)"><option value="aimd">AIMD</option><option value="md">Markdown</option></select>
              </label>
              <label v-if="editable">{{ t("page.meetingSpace.importDoc") }} <input type="file" accept=".md,.aimd" @change="importSource"></label>
              <n-button size="small" @click="downloadSource">{{ t("page.meetingSpace.export") }} .{{ form.body_format }}</n-button>
              <n-button v-if="editable && mode === 'source' && form.body_format !== 'md'" size="small" :disabled="saving || busy" @click="showField = true">
                {{ t('page.researchDocuments.addField') }}
              </n-button>
              <n-button
                size="small"
                :type="mode === 'wysiwyg' ? 'primary' : 'default'"
                @click="switchMode('wysiwyg')"
              >
                {{ t("page.researchDocuments.visual") }}
              </n-button>
              <n-button
                size="small"
                :type="mode === 'source' ? 'primary' : 'default'"
                data-testid="document-source-mode"
                @click="switchMode('source')"
              >
                {{ t("page.researchDocuments.source") }}
              </n-button>
            </div>
            <template v-if="form.body_format === 'md'">
              <n-input v-if="mode === 'source'" type="textarea" :readonly="!editable" :value="form.body" :autosize="{ minRows: 10 }" @update:value="updateBody($event)" />
              <document-markdown v-else :body="form.body" format="md" />
            </template>
            <aimd-editor
              v-else-if="mode === 'source'"
              :model-value="form.body"
              mode="source"
              :readonly="!editable"
              :locale="locale"
              :min-height="400"
              :keep-inactive-editors-mounted="false"
              @update:model-value="updateBody($event)"
              @update:mode="switchMode"
            />
            <aimd-recorder-wysiwyg-surface
              v-else
              :key="`${doc.id}:${surfaceRevision}`"
              ref="visualSurface"
              :content="form.body"
              :model-value="form.record_data"
              :readonly="!editable"
              :locale="locale"
              :min-height="400"
              :request-collector-permission="denyCollector"
              @ready="onVisualReady"
              @input="markVisualInput"
              @update:content="updateBody($event, true)"
              @update:model-value="updateValues"
            />
          </section>
          <aside v-if="showDetails" id="document-details" class="min-w-0 space-y-4" data-testid="document-details">
            <p class="aira-type-meta">
              {{ t('page.documentBrowse.dateHint') }}
            </p>
            <p v-if="scope?.scope_type !== 'personal'" class="aira-type-meta">
              {{ t('page.documentBrowse.draftAudience') }}
            </p>
            <n-card size="small" :title="t('page.researchDocuments.tags')">
              <n-dynamic-tags v-model:value="form.tags" :disabled="!editable" />
            </n-card>
            <n-card size="small" :title="t('page.researchDocuments.collection')">
              <n-input
                v-model:value="form.collection"
                :readonly="!editable"
                :input-props="{ 'aria-label': t('page.researchDocuments.collection') }"
              />
            </n-card>
            <n-card size="small" :title="t('page.researchDocuments.attachments')">
              <ul v-if="form.file_ids.length" class="m-0 pl-4 space-y-3">
                <li v-for="id in form.file_ids" :key="id" class="break-words">
                  <n-button
                    v-if="doc.files.find(file => file.id === id)?.filename"
                    text
                    @click="downloadAttachment(id)"
                  >
                    {{ doc.files.find(file => file.id === id)?.filename }}
                  </n-button>
                  <span v-else>{{ t("page.researchDocuments.unavailable") }}</span>
                  <n-button v-if="editable" text size="small" @click="removeAttachment(id)">
                    {{ t("page.researchDocuments.removeAttachment") }}
                  </n-button>
                </li>
              </ul>
              <n-button v-if="editable" class="mt-3" @click="showMaterials = true">
                {{ t("page.researchDocuments.attach") }}
              </n-button>
            </n-card>
            <n-card
              v-if="Object.keys(doc.origin).length"
              size="small"
              :title="t('page.researchDocuments.sourceInfo')"
            >
              <p class="break-all">
                {{ doc.origin.kind }} · {{ doc.origin.version || doc.origin.revision }}
              </p>
            </n-card>
          </aside>
        </div>
        <section class="mt-4 border rounded-xl p-4" data-testid="document-results">
          <button type="button" class="w-full flex items-center justify-between gap-3 text-left" :aria-expanded="resultsOpen" aria-controls="document-results-actions" data-testid="document-results-toggle" @click="resultsOpen = !resultsOpen">
            <span class="font-medium">{{ t('page.documentUx.results') }}</span><span aria-hidden="true">{{ resultsOpen ? '−' : '+' }}</span>
          </button>
          <div v-if="resultsOpen" id="document-results-actions" class="mt-3 space-y-3">
            <p class="aira-type-meta">
              {{ t('page.documentUx.resultsHint') }}
            </p>
            <div class="flex flex-wrap gap-2">
              <n-button v-if="editable" :disabled="saving || busy" @click="check">
                {{ t('page.researchDocuments.validate') }}
              </n-button>
              <n-button v-if="editable && valueRows.length" @click="showValues = true">
                {{ t('page.researchDocuments.reviewValues') }}
              </n-button>
              <n-button v-if="editable" type="primary" :disabled="saving || busy" data-testid="document-submit" @click="submit()">
                {{ t('page.researchDocuments.submit') }}
              </n-button>
              <n-button v-else @click="showSubmissions">
                {{ t('page.researchDocuments.submittedHistory') }}
              </n-button>
            </div>
          </div>
        </section>
      </template>
    </n-spin>
    <template-editor-dialog v-if="showTemplate && scope && doc" :scope="scope" :source-document="doc" @close="showTemplate = false" @saved="showTemplate = false; notice = t('page.documentTemplates.saved'); templateDestination = $event" />
    <n-modal
      v-model:show="showValues"
      preset="card"
      class="aira-dialog"
      :title="t('page.researchDocuments.reviewValues')"
    >
      <p>{{ t("page.researchDocuments.reviewValuesHint") }}</p>
      <div class="max-h-55vh overflow-y-auto space-y-3">
        <div
          v-for="item in valueRows"
          :key="`${item.scope}.${item.field}`"
          class="flex flex-wrap items-center gap-3 border-b pb-3"
        >
          <span class="min-w-0 flex-1 break-all">{{ item.scope }}.{{ item.field }}: {{ item.value }}</span>
          <n-button size="small" @click="removeValue(item.scope, item.field)">
            {{ t("page.researchDocuments.removeValue") }}
          </n-button>
        </div>
      </div>
      <n-button class="mt-4" @click="showValues = false">
        {{ t("page.researchDocuments.close") }}
      </n-button>
    </n-modal>
    <n-modal :show="Boolean(submissions)" preset="card" class="aira-dialog" :title="t('page.researchDocuments.submittedHistory')" @update:show="submissions = undefined">
      <p>{{ t('page.researchDocuments.submitHint') }}</p>
      <n-empty v-if="!submissions?.length" :description="t('page.researchDocuments.noSubmissions')" />
      <div class="max-h-65vh overflow-y-auto space-y-4">
        <article v-for="item in submissions" :key="item.id">
          <h3>{{ t('page.researchDocuments.revision', { revision: item.source_revision }) }} · {{ new Date(item.created_at).toLocaleString() }}</h3>
          <snapshot-preview :snapshot="item.snapshot" />
        </article>
      </div>
    </n-modal>
    <n-modal
      v-model:show="showField"
      preset="card"
      class="aira-dialog"
      :title="t('page.researchDocuments.addField')"
      style="--aira-dialog-width: 32rem"
    >
      <n-form label-placement="top">
        <n-form-item :label="t('page.researchDocuments.fieldId')">
          <n-input v-model:value="field.id" data-testid="document-field-id" />
        </n-form-item>
        <n-form-item :label="t('page.researchDocuments.fieldTitle')">
          <n-input v-model:value="field.title" />
        </n-form-item>
        <n-form-item :label="t('page.researchDocuments.fieldType')">
          <n-select v-model:value="field.type" :options="fieldTypes" />
        </n-form-item>
        <n-form-item :label="t('page.researchDocuments.fieldUnit')">
          <n-input v-model:value="field.unit" />
        </n-form-item>
      </n-form><p>{{ t("page.researchDocuments.fieldHint") }}</p>
      <n-button type="primary" data-testid="document-field-insert" @click="addField">
        {{ t("page.researchDocuments.insert") }}
      </n-button>
    </n-modal>
    <n-modal
      :show="Boolean(changePreview)"
      preset="card"
      class="aira-dialog"
      :mask-closable="false"
      :title="t('page.researchDocuments.definitionImpact')"
      @update:show="changePreview = undefined"
    >
      <p>{{ t("page.researchDocuments.definitionImpactHint") }}</p>
      <div v-for="item in changePreview?.impact?.field_changes" :key="item.field" class="mb-3 border-b pb-2">
        <strong>{{ item.field }}</strong>
        <p class="break-words">
          {{ item.before?.type || '—' }} {{ item.before?.unit || '' }} → {{ item.after?.type || '—' }} {{ item.after?.unit || '' }}
        </p>
      </div>
      <p v-if="changePreview?.impact?.removed_values.length">
        {{ t("page.researchDocuments.removedValues") }}:
        {{ changePreview.impact.removed_values.join(", ") }}
      </p>
      <n-button type="primary" :loading="saving" @click="save(true)">
        {{ t("page.researchDocuments.confirm") }}
      </n-button>
    </n-modal>
    <n-modal
      :show="Boolean(submitPreview)"
      preset="card"
      class="aira-dialog"
      :mask-closable="false"
      :title="t('page.researchDocuments.submit')"
      @update:show="submitPreview = undefined"
    >
      <p>{{ t("page.researchDocuments.submitHint") }}</p>
      <snapshot-preview :snapshot="submitPreview?.snapshot" />
      <n-button
        type="primary"
        :loading="busy"
        data-testid="document-submit-confirm"
        @click="submit(true)"
      >
        {{ t("page.researchDocuments.confirm") }}
      </n-button>
    </n-modal>
    <n-modal
      :show="Boolean(revisions)"
      preset="card"
      class="aira-dialog"
      :title="t('page.researchDocuments.history')"
      @update:show="revisions = undefined"
    >
      <div class="max-h-65vh overflow-y-auto">
        <article
          v-for="item in revisions"
          :key="item.revision"
          class="mb-4 border-b border-gray-100 pb-4"
        >
          <p>
            {{ t("page.researchDocuments.revision", { revision: item.revision }) }} ·
            {{ item.change_summary }}
          </p>
          <details>
            <summary>{{ t("page.researchDocuments.preview") }}</summary><snapshot-preview :snapshot="item.snapshot" />
          </details>
          <n-button v-if="editable" :disabled="busy || saving" @click="restore(item.revision)">
            {{ t("page.researchDocuments.restore") }}
          </n-button>
        </article>
      </div>
    </n-modal>
    <n-modal
      :show="Boolean(restorePreview)"
      preset="card"
      class="aira-dialog"
      :mask-closable="false"
      :title="t('page.researchDocuments.restore')"
      @update:show="restorePreview = undefined"
    >
      <p>{{ t("page.researchDocuments.restoreHint") }}</p>
      <snapshot-preview :snapshot="restorePreview?.preview.snapshot" />
      <n-button
        v-if="restorePreview"
        type="primary"
        :loading="busy"
        @click="restore(restorePreview.revision, true)"
      >
        {{ t("page.researchDocuments.confirm") }}
      </n-button>
    </n-modal>
    <n-modal
      v-model:show="showMaterials"
      preset="card"
      class="aira-dialog"
      style="--aira-dialog-width: 60rem"
      :title="t('page.researchDocuments.materials')"
    >
      <material-library v-if="scope && showMaterials" :scope="scope" attach @attach="attach" />
    </n-modal>
    <n-modal
      :show="Boolean(derive)"
      preset="card"
      class="aira-dialog"
      style="--aira-dialog-width: 56rem"
      :mask-closable="false"
      :title="t('page.researchDocuments.derive')"
      @update:show="derive = undefined"
    >
      <template v-if="derive">
        <n-alert type="info" class="mb-4">
          {{ t("page.researchDocuments.deriveHint") }}
        </n-alert>
        <template v-if="!derive.result">
          <n-select
            v-model:value="derive.kind"
            :options="[
              { value: 'protocol', label: t('page.researchDocuments.deriveProtocol') },
              { value: 'knowledge', label: t('page.researchDocuments.deriveKnowledge') },
            ]"
            @update:value="derive.preview = undefined"
          />
          <n-input
            v-model:value="derive.title"
            class="my-3"
            :input-props="{ 'aria-label': t('page.researchDocuments.titleLabel') }"
            @update:value="derive.preview = undefined"
          />
          <n-input
            v-model:value="derive.body"
            type="textarea"
            :autosize="{ minRows: 10, maxRows: 22 }"
            @update:value="derive.preview = undefined"
          />
          <n-button
            class="mt-4"
            type="primary"
            :loading="busy"
            @click="deriveAsset(Boolean(derive.preview))"
          >
            {{
              t(
                derive.preview
                  ? "page.researchDocuments.confirm"
                  : "page.researchDocuments.preview",
              )
            }}
          </n-button>
          <snapshot-preview v-if="derive.preview" :snapshot="derive.preview.snapshot" />
        </template>
        <template v-else>
          <p>{{ t("page.researchDocuments.derived") }}</p>
          <router-link
            v-if="derive.result.knowledge_id"
            :to="{ name: 'knowledge-home', query: { item: derive.result.knowledge_id } }"
          >
            <n-button>{{ t("page.researchDocuments.openKnowledge") }}</n-button>
          </router-link>
          <n-button v-else @click="download(derive.result.id)">
            {{ t("page.researchDocuments.downloadMethod") }}
          </n-button>
        </template>
      </template>
    </n-modal>
  </main>
</template>

<style scoped>
.document-columns {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 1.5rem;
}
.document-columns--details { grid-template-columns: minmax(0, 1fr) 260px; }
.document-title { --n-font-size: 26px !important; font-weight: 600; }
.document-more-actions { display: flex; flex-direction: column; align-items: stretch; max-height: 65vh; overflow-y: auto; min-width: 220px; }
.document-more-actions h3 { margin: 8px 12px 4px; font-size: 12px; color: #6b7280; }
.document-more-actions :deep(.n-button__content) { justify-content: flex-start; width: 100%; }
.preview-json {
  max-height: 45vh;
  overflow: auto;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font-size: 0.8rem;
}
@media (max-width: 1000px) {
  .document-columns {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
