<script setup lang="ts">
import type { Meeting, MeetingActionDraft, MeetingComment, MeetingContent, MeetingMember } from "@/service/api/meetings"
import type { ProjectPerson } from "@/service/api/project-people"
import type { ProjectWork } from "@/service/api/project-work"
import AiraActionButton from "@/components/common/aira-action-button.vue"
import DocumentMarkdown from "@/components/common/document-markdown.vue"
import PeoplePicker from "@/components/project/people-picker.vue"
import { useConfirmDocumentChange } from "@/composables/useConfirmDocumentChange"
import {
  addMeetingComment,
  getMeeting,
  linkMeetingWork,
  listMeetings,
  meetingComments,
  meetingContent,
  meetingMembers,
  saveMeeting,
  saveMeetingActions,
  saveMeetingWithActions,
} from "@/service/api/meetings"
import { listProjectPeople } from "@/service/api/project-people"
import { listProjectWork } from "@/service/api/project-work"
import { researchDocumentHistory } from "@/service/api/research-documents"
import { documentTimeZone, localDocumentDate } from "@/utils/documentBrowse"
import { downloadBlob } from "@/utils/downloadBlob"
import { preserveVisualFenceMetadata } from "@/utils/recorderMarkdown"
import { restoreAimdInlineTemplates } from "@airalogy/aimd-core"
import { AimdEditor } from "@airalogy/aimd-editor/vue"
import FilterIcon from "~icons/tabler/filter"
import SearchIcon from "~icons/tabler/search"
import { useDialog } from "naive-ui"
import { useTemplateRef } from "vue"
import { useI18n } from "vue-i18n"
import { onBeforeRouteLeave, onBeforeRouteUpdate } from "vue-router"
import { useProjectInfoStore } from "../project-protocols/hooks/useProjectInfoStore"
import ActionBatch from "./action-batch.vue"
import { meetingHandoffKey, meetingNameKey, organizeMinutesKey } from "./aira-handoff"
import FollowUps from "./follow-ups.vue"
import PreviousMeetingWork from "./previous-meeting-work.vue"
import SourcePanel from "./source-panel.vue"
import WorkFollowUpDetails from "./work-follow-up-details.vue"

const { t, locale } = useI18n()
const dialog = useDialog()
const confirmChange = useConfirmDocumentChange()
const route = useRoute()
const router = useRouter()
const { projectInfo } = useProjectInfoStore()
const projectId = computed(() => projectInfo.value?.id)
const showSources = ref(false)
const suggestedTasks = ref<string[]>([])
const items = ref<Meeting[]>([])
const total = ref(0)
const page = ref(1)
const q = ref("")
const appliedQuery = ref("")
const filtersOpen = ref(false)
const dateFrom = ref("")
const dateTo = ref("")
const participantFilter = ref<string | null>(null)
const projectPeople = ref<ProjectPerson[]>([])

const loading = ref(false)
const busy = ref(false)
const error = ref("")
const notice = ref("")
const canCreate = ref(false)
const members = ref<MeetingMember[]>([])
const participantOptions = computed(() => [...members.value.filter(m => !projectPeople.value.some(p => p.user_id === m.id)).map(m => ({ value: `user:${m.id}`, label: m.name || m.username })), ...projectPeople.value.map(p => ({ value: p.user_id ? `user:${p.user_id}` : `person:${p.id}`, label: `${p.display_name || p.name}${p.organization ? ` · ${p.organization}` : ""}` }))])
const filterSummary = computed(() => [
  participantOptions.value.find(option => option.value === participantFilter.value)?.label,
  dateFrom.value && `${t("page.meetings.from")} ${dateFrom.value}`,
  dateTo.value && `${t("page.meetings.to")} ${dateTo.value}`,
].filter(Boolean).join(" · "))
const selected = ref<Meeting>()
const sourcePlayback = ref<InstanceType<typeof SourcePanel>>()
async function recordingLink(event: MouseEvent) {
  const href = (event.target as HTMLElement).closest("a")?.getAttribute("href")
  if (!href || !/^#recording-\d+$/.test(href))
    return
  event.preventDefault()
  if (!selected.value?.can_read_sources)
    return
  showSources.value = true
  await nextTick()
  await sourcePlayback.value?.seek(Number(href.slice(11)))
}
const form = ref<MeetingContent>()
const saved = ref("")
const creationId = ref("")
const grantAttendees = ref(true)
const handoff = inject(meetingHandoffKey, null)
const meetingName = inject(meetingNameKey, null)
watchEffect((cleanup) => {
  if (!meetingName)
    return
  meetingName.value = form.value ? form.value.title.trim() || t("page.meetings.new") : ""
  cleanup(() => {
    meetingName.value = ""
  })
})
const initialActionTitles = ref<string[]>([])
const editorMode = ref<"wysiwyg" | "source">("wysiwyg")
const comment = ref("")
const comments = ref<MeetingComment[]>([])
const commentPage = ref(1)
const commentTotal = ref(0)
const workOptions = ref<ProjectWork[]>([])
const workId = ref<string | null>(null)
const editing = ref(false)
const actionDirty = ref(false)
const draftActions = ref<MeetingActionDraft[]>([])
const discussionIds = ref<string[]>([])
let batchRequestId = crypto.randomUUID()
const draftMeeting = computed<Meeting | undefined>(() => form.value && projectId.value && !selected.value
  ? {
      ...form.value,
      id: creationId.value,
      project_id: projectId.value,
      revision: 1,
      created_at: "",
      updated_at: "",
      lab_id: "",
      can_read_sources: false,
      can_manage: true,
      can_edit: true,
      can_comment: true,
      can_create_work: true,
    }
  : undefined)
const projectPersonToAdd = ref<string | string[] | null>(null)
const externalName = ref("")
const externalOrganization = ref("")
const participantToAdd = ref<string | null>(null)
const grantToAdd = ref<string | null>(null)
const history = ref<{ revision: number, change_summary: string, snapshot: { body?: string } }[]>([])
const showHistory = ref(false)
let commentKey = crypto.randomUUID()
let sequence = 0
const editable = computed(() => !selected.value || selected.value.can_edit)
const visualSurface = ref<InstanceType<typeof AimdEditor>>()
const visualPending = ref(false)
const surfaceRevision = ref(0)
let visualLastMarkdown: string | undefined
interface VisualEditor {
  action: (read: (ctx: { get: (name: string) => any }) => string) => string
}
function readVisualMarkdown(editor: VisualEditor) {
  return restoreAimdInlineTemplates(
    editor.action(ctx => ctx.get("serializer")(ctx.get("editorView").state.doc) as string),
  )
}
function onVisualReady({ milkdown }: { milkdown?: VisualEditor }) {
  if (milkdown)
    visualLastMarkdown = readVisualMarkdown(milkdown)
}
function updateBody(body: string, visual = false) {
  if (!form.value || !editable.value)
    return
  form.value.body = visual ? preserveVisualFenceMetadata(form.value.body, body) : body
  visualPending.value = false
  if (visual)
    visualLastMarkdown = body
}
async function importMinutes(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ""
  const content = form.value
  if (!file || !content || !editable.value)
    return
  if (file.size > 800000 || !/\.(?:md|aimd)$/i.test(file.name)) {
    error.value = t("page.meetingSpace.invalidFile")
    return
  }
  flushVisual()
  if (content.body && !(await confirmChange(t("page.meetingSpace.replace"))))
    return
  const body = await file.text()
  if (content !== form.value || body.length > 200000) {
    error.value = t("page.meetingSpace.invalidFile")
    return
  }
  content.body_format = file.name.toLowerCase().endsWith(".md") ? "md" : "aimd"
  updateBody(body)
  surfaceRevision.value++
}
function exportMinutes(meeting: Meeting) {
  downloadBlob(new Blob([meeting.body], { type: "text/plain;charset=utf-8" }), `${meeting.title}.${meeting.body_format || "aimd"}`)
}
function flushVisual() {
  const editor = visualSurface.value?.getMilkdownEditor?.()
  if (editorMode.value !== "wysiwyg" || !editable.value || !editor)
    return
  const markdown = readVisualMarkdown(editor)
  if (markdown !== visualLastMarkdown)
    updateBody(markdown, true)
  else visualPending.value = false
}
const organize = inject(organizeMinutesKey, null)
const actionBatch = useTemplateRef("actionBatch")
function organizeMinutes(trigger: HTMLElement) {
  flushVisual()
  const source = form.value
  if (!source || !editing.value || !editable.value || !organize)
    return
  const { title, body } = source
  const id = selected.value?.id || creationId.value
  const notes = [t("page.airaActions.minutesPrompt"), title, body].filter(Boolean).join("\n\n")
  organize.open({
    prompt: notes,
    apply(proposal) {
      flushVisual()
      if (!editing.value || !editable.value || busy.value || form.value !== source || (selected.value?.id || creationId.value) !== id || source.title !== title || source.body !== body)
        return false
      const actions = proposal.actions.filter(Boolean)
      const staged = actionBatch.value?.appendSuggestions(actions)
      const actionText = !staged && actions.length ? `\n\n${t("page.meetings.actions")}\n${actions.map(action => `- ${action}`).join("\n")}` : ""
      updateBody(proposal.body + actionText)
      if (!source.title.trim())
        source.title = proposal.title
      surfaceRevision.value++
      return true
    },
  }, trigger)
}
function switchMode(mode: "source" | "wysiwyg") {
  flushVisual()
  editorMode.value = mode
  surfaceRevision.value++
}
function markInput(e: Event) {
  if (editable.value && (e.target as HTMLElement).matches(".ProseMirror[contenteditable=true]"))
    visualPending.value = true
}
const dirty = computed(
  () => visualPending.value || (!!form.value && JSON.stringify(form.value) !== saved.value),
)
const manageable = computed(() => !selected.value || selected.value.can_manage)
const memberOptions = computed(() =>
  members.value.map(m => ({ value: m.id, label: `${m.name || m.username} (${m.username})` })),
)
const statusOptions = computed(() =>
  ["held", "planned", "cancelled"].map(value => ({ value, label: t(`page.meetings.${value}`) })),
)
const accessOptions = computed(() =>
  ["project", "selected"].map(value => ({ value, label: t(`page.meetings.visibility.${value}`) })),
)
const roleOptions = computed(() =>
  ["viewer", "commenter", "editor"].map(value => ({
    value,
    label: t(`page.meetings.roles.${value}`),
  })),
)
const attendanceOptions = computed(() =>
  ["attended", "invited", "absent", "unknown"].map(value => ({
    value,
    label: t(`page.meetings.attendance.${value}`),
  })),
)
function message(e: unknown) {
  const status = (e as { response?: { status?: number } })?.response?.status
  if (status === 409)
    return t("page.meetings.conflict")
  if (status === 403 || status === 404)
    return t("page.meetings.unavailable")
  if (status === 422)
    return t("page.meetings.invalid")
  return t("page.meetings.failed")
}
function accept(m: Meeting) {
  visualPending.value = false
  visualLastMarkdown = undefined
  surfaceRevision.value++
  selected.value = m
  form.value = meetingContent(m)
  saved.value = JSON.stringify(form.value)
}
function dateValue(value: string | null, precision: "date" | "datetime") {
  if (!value)
    return ""
  const d = new Date(value)
  if (precision === "date")
    return localDocumentDate(d)
  return `${localDocumentDate(d)}T${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`
}
function setTime(key: "occurred_at" | "scheduled_at", value: string) {
  if (!form.value)
    return
  const d = new Date(value.length === 10 ? `${value}T00:00:00` : value)
  form.value[key] = value && Number.isFinite(d.getTime()) ? d.toISOString() : null
  form.value.time_zone = documentTimeZone()
}
function filterList() {
  if (page.value === 1)
    void loadList()
  else
    page.value = 1
}
function searchMeetings(value = q.value) {
  appliedQuery.value = value.trim()
  filterList()
}
function clearMeetingFilters() {
  participantFilter.value = null
  dateFrom.value = ""
  dateTo.value = ""
  filterList()
}
async function loadList() {
  if (!projectId.value)
    return
  const ticket = ++sequence
  loading.value = true
  error.value = ""
  try {
    const data = await listMeetings({
      project_id: projectId.value,
      q: appliedQuery.value,
      participant_id: participantFilter.value?.startsWith("user:") ? participantFilter.value.slice(5) : undefined,
      person_id: participantFilter.value?.startsWith("person:") ? participantFilter.value.slice(7) : undefined,
      date_from: dateFrom.value || undefined,
      date_to: dateTo.value || undefined,
      time_zone: documentTimeZone(),
      page: page.value,
    })
    if (ticket !== sequence)
      return
    items.value = data.items
    total.value = data.total
    canCreate.value = data.can_write
  }
  catch (e) {
    if (ticket === sequence)
      error.value = message(e)
  }
  finally {
    if (ticket === sequence)
      loading.value = false
  }
}
async function loadSelected() {
  if (!projectId.value)
    return
  const id = typeof route.query.meeting === "string" ? route.query.meeting : ""
  error.value = ""
  notice.value = ""
  history.value = []
  showHistory.value = false
  selected.value = undefined
  showSources.value = false
  suggestedTasks.value = []
  form.value = undefined
  comments.value = []
  comment.value = ""
  editing.value = false
  actionDirty.value = false
  draftActions.value = []
  discussionIds.value = []
  batchRequestId = crypto.randomUUID()
  initialActionTitles.value = []
  if (!id)
    return
  if (id === "new") {
    editing.value = true
    grantAttendees.value = true
    creationId.value = crypto.randomUUID()
    form.value = {
      title: "",
      body: t("page.meetings.template"),
      body_format: "aimd",
      status: "held",
      occurred_at: new Date(`${localDocumentDate()}T00:00:00`).toISOString(),
      scheduled_at: null,
      time_precision: "date",
      time_zone: documentTimeZone(),
      visibility: "selected",
      participants: [],
      access: [],
    }
    saved.value = JSON.stringify(form.value)
    if (route.query.draft) {
      const seed = handoff?.value
      if (seed?.projectId === projectId.value && seed.key === route.query.draft) {
        const proposal = seed.proposal
        form.value.title = proposal.title
        form.value.body = proposal.body
        setTime("occurred_at", proposal.occurred_on || "")
        initialActionTitles.value = [...proposal.actions]
      }
      else {
        form.value = undefined
        error.value = t("page.projectAira.expired")
      }
    }
    return
  }
  busy.value = true
  try {
    const m = await getMeeting(id)
    if (m.project_id !== projectId.value)
      throw new Error(t("page.meetings.failed"))
    accept(m)
    commentPage.value = 1
    await loadComments()
    if (m.can_create_work) {
      workOptions.value = (
        await listProjectWork({ project_id: projectId.value, page_size: 100 })
      ).items
    }
  }
  catch (e) {
    error.value = message(e)
  }
  finally {
    busy.value = false
  }
}
async function loadComments() {
  if (!selected.value)
    return
  const result = await meetingComments(selected.value.id, commentPage.value)
  comments.value = result.items
  commentTotal.value = result.total
}
async function save() {
  flushVisual()
  if (!form.value || !projectId.value || busy.value)
    return
  busy.value = true
  error.value = ""
  notice.value = ""
  try {
    let content = form.value
    if (!selected.value && grantAttendees.value && content.visibility === "selected") {
      const access = [...content.access]
      for (const person of content.participants) {
        const uid = person.user_id || projectPeople.value.find(p => p.id === person.person_id)?.user_id
        if (uid && person.attendance !== "absent" && members.value.some(m => m.id === uid) && !access.some(grant => grant.user_id === uid))
          access.push({ user_id: uid, role: "viewer" })
      }
      content = { ...content, access }
    }
    const result = !selected.value && (draftActions.value.length || discussionIds.value.length)
      ? await saveMeetingWithActions(creationId.value, projectId.value, content, batchRequestId, draftActions.value, discussionIds.value)
      : await saveMeeting(
        selected.value?.id || creationId.value,
        projectId.value,
        content,
        selected.value?.revision,
      )
    const creating = !selected.value
    accept(result)
    discussionIds.value = []
    if (creating) {
      draftActions.value = []
      actionDirty.value = false
    }
    editing.value = false
    notice.value = t("page.meetings.saved")
    if (route.query.meeting === "new") {
      await router.replace({
        name: "project-meetings",
        params: route.params,
        query: { meeting: result.id },
      })
    }
    if (handoff)
      handoff.value = null
    await loadList()
  }
  catch (e) {
    error.value = message(e)
  }
  finally {
    busy.value = false
  }
}
function addParticipant() {
  const member = members.value.find(m => m.id === participantToAdd.value)
  if (member && form.value && !form.value.participants.some(p => p.user_id === member.id)) {
    form.value.participants.push({
      user_id: member.id,
      name: member.name || member.username,
      organization: "",
      attendance: form.value.status === "held" ? "attended" : "invited",
    })
  }
  participantToAdd.value = null
}
function addExternal() {
  if (form.value && externalName.value.trim()) {
    form.value.participants.push({
      user_id: null,
      name: externalName.value.trim(),
      organization: externalOrganization.value.trim(),
      attendance: form.value.status === "held" ? "attended" : "invited",
    })
  }
  externalName.value = ""
  externalOrganization.value = ""
}
function addGrant() {
  if (
    form.value
    && grantToAdd.value
    && !form.value.access.some(g => g.user_id === grantToAdd.value)
  ) {
    form.value.access.push({ user_id: grantToAdd.value, role: "viewer" })
  }
  grantToAdd.value = null
}
async function postComment() {
  if (!selected.value || !comment.value.trim())
    return
  busy.value = true
  error.value = ""
  try {
    await addMeetingComment(selected.value.id, commentKey, comment.value)
    comment.value = ""
    commentKey = crypto.randomUUID()
    await loadComments()
  }
  catch (e) {
    error.value = message(e)
  }
  finally {
    busy.value = false
  }
}
async function saveDiscussion() {
  if (!selected.value || !discussionIds.value.length || busy.value)
    return
  busy.value = true
  error.value = ""
  try {
    selected.value = await saveMeetingActions(selected.value.id, batchRequestId, selected.value.revision, [], discussionIds.value)
    discussionIds.value = []
    batchRequestId = crypto.randomUUID()
    notice.value = t("page.meetings.discussionSaved")
  }
  catch (e) {
    error.value = message(e)
  }
  finally {
    busy.value = false
  }
}
async function linkWork() {
  if (!selected.value || !workId.value)
    return
  busy.value = true
  error.value = ""
  try {
    selected.value = await linkMeetingWork(selected.value.id, workId.value, selected.value.revision)
    workId.value = null
  }
  catch (e) {
    error.value = message(e)
  }
  finally {
    busy.value = false
  }
}
async function addProjectParticipant() {
  if (!form.value || typeof projectPersonToAdd.value !== "string" || !projectId.value)
    return
  const value = projectPersonToAdd.value
  if (value.startsWith("user:")) {
    participantToAdd.value = value.slice(5)
    addParticipant()
  }
  else {
    const person = (await listProjectPeople(projectId.value)).people.find(p => p.id === value.slice(7))
    if (person && !form.value.participants.some(p => p.person_id === person.id)) {
      form.value.participants.push({ user_id: null, person_id: person.id, name: person.display_name || person.name, organization: person.organization, attendance: form.value.status === "held" ? "attended" : "invited" })
    }
  }
  projectPersonToAdd.value = null
}
async function cancelEditing() {
  if (await guard()) {
    if (selected.value)
      accept(selected.value)
    editing.value = false
  }
}
async function loadHistory() {
  if (!selected.value)
    return
  try {
    history.value = (await researchDocumentHistory(selected.value.id)).items as typeof history.value
    showHistory.value = true
  }
  catch (e) {
    error.value = message(e)
  }
}
async function guard() {
  flushVisual()
  if (!dirty.value && !actionDirty.value && !discussionIds.value.length && !comment.value.trim())
    return true
  return new Promise<boolean>((resolve) => {
    dialog.warning({
      title: t("page.meetings.unsaved"),
      content: t("page.meetings.unsavedLeave"),
      positiveText: t("page.researchDocuments.confirm"),
      negativeText: t("common.cancel"),
      onPositiveClick: () => resolve(true),
      onNegativeClick: () => resolve(false),
      onClose: () => resolve(false),
      onMaskClick: () => resolve(false),
    })
  })
}
async function reload() {
  if (await guard())
    await loadSelected()
}

onBeforeRouteLeave(guard)
onBeforeRouteUpdate((to, from) => (to.query.meeting === from.query.meeting && to.query.draft === from.query.draft) || guard())
function beforeUnload(e: BeforeUnloadEvent) {
  flushVisual()
  if (dirty.value || actionDirty.value || discussionIds.value.length || comment.value.trim()) {
    e.preventDefault()
    e.returnValue = ""
  }
}
onMounted(() => window.addEventListener("beforeunload", beforeUnload))
onBeforeUnmount(() => {
  sequence++
  window.removeEventListener("beforeunload", beforeUnload)
})
watch(
  projectId,
  async () => {
    if (!projectId.value)
      return
    try {
      members.value = (await meetingMembers(projectId.value)).members
      projectPeople.value = (await listProjectPeople(projectId.value)).people
      await loadList()
      await loadSelected()
    }
    catch (e) {
      error.value = message(e)
    }
  },
  { immediate: true },
)
watch([() => route.query.meeting, () => route.query.draft], loadSelected)
watch(page, loadList)
</script>

<template>
  <section class="min-w-0 space-y-5" data-testid="meetings-page">
    <header class="flex flex-wrap items-center justify-between gap-3">
      <h1 class="aira-type-page-title">
        {{ t("page.meetings.title") }}
      </h1>
      <n-button
        v-if="!form && canCreate"
        type="primary"
        data-testid="meeting-new"
        @click="
          router.push({
            name: 'project-meetings',
            params: route.params,
            query: { ...route.query, meeting: 'new' },
          })
        "
      >
        {{ t("page.meetings.new") }}
      </n-button>
      <n-button
        v-if="form"
        @click="
          router.push({
            name: 'project-meetings',
            params: route.params,
            query: { ...route.query, meeting: undefined },
          })
        "
      >
        {{ t("page.meetings.back") }}
      </n-button>
    </header>
    <n-alert v-if="error" type="error" role="alert" data-testid="meeting-error">
      {{ error }}
      <n-button v-if="selected" size="small" @click="reload()">
        {{ t("page.meetings.reload") }}
      </n-button>
    </n-alert>
    <n-alert v-if="notice" type="success" role="status">
      {{ notice }}
    </n-alert>
    <template v-if="!form">
      <router-link v-if="projectId" :to="{ name: 'my-work', query: { view: 'meetings', scope: 'visible', project: projectId, period: 'past' } }">{{ t("page.meetingSpace.linkedTimeline") }}</router-link>
      <div class="meeting-filters">
        <form class="meeting-search-row" role="search" @submit.prevent="searchMeetings()">
          <n-input
            v-model:value="q" clearable size="small" data-testid="meeting-search"
            :placeholder="t('page.meetings.search')" :input-props="{ 'aria-label': t('page.meetings.search') }"
            @clear="searchMeetings('')"
          >
            <template #suffix>
              <button type="submit" class="meeting-search-submit" :aria-label="t('common.search')">
                <n-icon :component="SearchIcon" :size="16" />
              </button>
            </template>
          </n-input>
          <n-button
            size="small" :type="filterSummary ? 'primary' : 'default'" :ghost="Boolean(filterSummary)"
            :aria-expanded="filtersOpen" aria-controls="meeting-filter-fields"
            data-testid="meeting-filters-toggle" @click="filtersOpen = !filtersOpen"
          >
            <template #icon><n-icon :component="FilterIcon" /></template>
            {{ t("page.documentUx.filters") }}
          </n-button>
        </form>
        <div v-show="filtersOpen" id="meeting-filter-fields" class="meeting-filter-fields">
          <label>{{ t("page.meetings.participant") }}
            <n-select v-model:value="participantFilter" size="small" :options="participantOptions" clearable filterable @update:value="filterList" />
          </label>
          <label>{{ t("page.meetings.from") }}<input v-model="dateFrom" type="date" :max="dateTo || undefined" class="meeting-date" @change="filterList"></label>
          <label>{{ t("page.meetings.to") }}<input v-model="dateTo" type="date" :min="dateFrom || undefined" class="meeting-date" @change="filterList"></label>
        </div>
        <div v-if="filterSummary" class="flex flex-wrap items-center gap-2 text-sm" data-testid="meeting-filter-summary">
          <span>{{ filterSummary }}</span>
          <n-button text size="small" @click="clearMeetingFilters">
            {{ t("page.documentUx.clearFilters") }}
          </n-button>
        </div>
      </div>
      <n-spin :show="loading">
        <p v-if="!loading && !items.length" class="py-8 text-gray-500">
          {{ t("page.meetings.empty") }}
        </p>
        <ul class="m-0 list-none p-0 divide-y">
          <li v-for="item in items" :key="item.id" class="py-4" data-testid="meeting-list-item">
            <router-link
              class="text-lg text-primary"
              :to="{
                name: 'project-meetings',
                params: route.params,
                query: { ...route.query, meeting: item.id },
              }"
            >
              {{ item.title }}
            </router-link>
            <p class="mb-1 text-sm text-gray-500">
              {{
                item.occurred_at
                  ? dateValue(item.occurred_at, item.time_precision).replace("T", " ")
                  : item.scheduled_at
                    ? dateValue(item.scheduled_at, "datetime").replace("T", " ")
                    : t("page.meetings.timeUnknown")
              }}
              · {{ t(`page.meetings.${item.status}`) }} ·
              {{ t(`page.meetings.visibility.${item.visibility}`) }}
            </p>
            <p class="text-sm">
              {{
                item.participants.map(p => p.name).join("、") || t("page.meetings.noParticipants")
              }}
            </p>
          </li>
        </ul>
      </n-spin>
      <n-pagination v-if="total > 20" v-model:page="page" :item-count="total" :page-size="20" />
    </template>
    <template v-else>
      <div
        class="meeting-save-bar flex flex-wrap items-center justify-between gap-3 border rounded-lg bg-white p-3"
      >
        <span data-testid="meeting-save-state">{{
          busy
            ? t("page.meetings.saving")
            : dirty || discussionIds.length
              ? t("page.meetings.unsaved")
              : selected
                ? t("page.meetings.saved")
                : t("page.meetings.newDraft")
        }}</span>
        <n-button
          v-if="editable && editing"
          type="primary"
          :loading="busy"
          :disabled="!form.title.trim() || (form.status === 'held' && !form.occurred_at) || (!dirty && !!selected)"
          data-testid="meeting-save"
          @click="save"
        >
          {{ t("common.save") }}
        </n-button>
      </div>
      <div v-if="selected && !editing" class="flex flex-wrap items-center gap-2">
        <n-button v-if="editable" type="primary" :disabled="busy || !!discussionIds.length" @click="editing = true" data-testid="meeting-edit">{{ t("common.edit") }}</n-button>
        <a href="#meeting-actions" class="text-primary">{{ t("page.meetings.actions") }} ({{ selected.work?.length || 0 }})</a>
      </div>
      <n-button v-if="selected && editing" text @click="cancelEditing">{{ t("common.cancel") }}</n-button>
      <article v-if="selected && !editing" class="space-y-4" data-testid="meeting-reading">
        <h1 class="m-0 text-2xl font-semibold">{{ selected.title }}</h1>
        <p class="text-sm text-gray-500">{{ t(`page.meetings.${selected.status}`) }} · {{ dateValue(selected.occurred_at || selected.scheduled_at, selected.time_precision) || t("page.meetings.noDate") }} · {{ t(`page.meetings.visibility.${selected.visibility}`) }}</p>
        <p v-if="selected.participants.length" class="text-sm">{{ selected.participants.map(p => `${p.name}${p.organization ? `（${p.organization}）` : ''} · ${t(`page.meetings.attendance.${p.attendance}`)}`).join('；') }}</p>
        <div @click="recordingLink"><document-markdown :body="selected.body" :format="selected.body_format || 'aimd'" /></div>
        <n-button size="small" @click="exportMinutes(selected)">{{ t("page.meetingSpace.export") }} .{{ selected.body_format || "aimd" }}</n-button>
        <template v-if="selected.can_read_sources">
          <n-button @click="showSources = !showSources">{{ t("page.meetingSpace.sources") }}</n-button>
          <component :is="SourcePanel" ref="sourcePlayback" v-if="showSources" :key="selected.id" :id="selected.id" :manage="selected.can_manage" @draft="(body, tasks) => { if (form) { form.body = body; suggestedTasks = tasks; editing = true } }" @cite="ms => { if (form) { form.body += ` [${Math.floor(ms / 1000)}s](#recording-${ms})`; editing = true } }" />
          <follow-ups :suggestions="suggestedTasks" :id="selected.id" :lab="selected.lab_id" :projects="[selected.project_id]" :revision="selected.revision" :manage="selected.can_manage" />
        </template>
      </article>
      <template v-if="editing">
        <label class="block">{{ t("page.meetings.subject")
        }}<n-input v-model:value="form.title" :readonly="!editable" data-testid="meeting-title" /></label>
        <div class="grid gap-4 sm:grid-cols-3">
          <label>{{ t("page.meetings.status")
          }}<n-select
            v-model:value="form.status"
            :options="statusOptions"
            :disabled="!editable"
            data-testid="meeting-status"
          /></label>
          <label v-if="form.status === 'held'">{{ t("page.meetings.actualTime")
          }}<input
            :value="dateValue(form.occurred_at, form.time_precision)"
            :type="form.time_precision === 'date' ? 'date' : 'datetime-local'"
            :disabled="!editable"
            class="meeting-date"
            data-testid="meeting-date"
            @change="setTime('occurred_at', ($event.target as HTMLInputElement).value)"
          ></label>
          <label v-else>{{ t("page.meetings.scheduledTime")
          }}<input
            :value="dateValue(form.scheduled_at, 'datetime')"
            type="datetime-local"
            :disabled="!editable"
            class="meeting-date"
            @change="setTime('scheduled_at', ($event.target as HTMLInputElement).value)"
          ></label>
          <n-checkbox
            v-if="form.status === 'held'"
            :checked="form.time_precision === 'datetime'"
            :disabled="!editable"
            @update:checked="form.time_precision = $event ? 'datetime' : 'date'"
          >
            {{ t("page.meetings.exactTime") }}
          </n-checkbox>
        </div>
        <previous-meeting-work
          v-if="draftMeeting && projectId" :key="creationId" v-model="discussionIds"
          :project-id="projectId" :meeting-id="creationId" :people="projectPeople" :members="members" :disabled="busy"
        />
        <details :open="!selected" class="border rounded-lg p-4" data-testid="meeting-people">
          <summary class="cursor-pointer font-medium">
            {{ t("page.meetings.peopleAndAccess") }} · {{ form.participants.length }} ·
            {{ t(`page.meetings.visibility.${form.visibility}`) }}
          </summary>
          <div class="mt-4 space-y-4">
            <p class="text-sm text-gray-500">
              {{ t("page.meetings.participantHint") }}
            </p>
            <div v-if="manageable && projectId" class="flex flex-wrap gap-2">
              <people-picker v-model="projectPersonToAdd" :project-id="projectId" :members="members" class="min-w-60 flex-1" />
              <n-button :disabled="!projectPersonToAdd" @click="addProjectParticipant">{{ t("page.meetings.addParticipant") }}</n-button>
            </div>
            <div v-if="manageable" class="flex flex-wrap gap-2">
              <n-input
                v-model:value="externalName"
                class="max-w-xs"
                :placeholder="t('page.meetings.externalName')"
              /><n-input
                v-model:value="externalOrganization"
                class="max-w-xs"
                :placeholder="t('page.meetings.organization')"
              /><n-button @click="addExternal">
                {{ t("page.meetings.addExternal") }}
              </n-button>
            </div>
            <div
              v-for="(person, index) in form.participants"
              :key="index"
              class="flex flex-wrap items-center gap-3"
            >
              <span>{{ person.name }} {{ person.organization }}</span><n-select
                v-model:value="person.attendance"
                :options="attendanceOptions"
                :disabled="!manageable"
                class="!w-32"
              /><n-button v-if="manageable" quaternary @click="form.participants.splice(index, 1)">
                {{ t("common.delete") }}
              </n-button>
            </div>
            <label class="block max-w-sm">{{ t("page.meetings.audience")
            }}<n-select
              v-model:value="form.visibility"
              :options="accessOptions"
              :disabled="!manageable"
              data-testid="meeting-visibility"
            /></label>
            <p class="text-sm text-gray-500">
              {{ t("page.meetings.audienceHint") }}
            </p>
            <n-checkbox v-if="!selected && form.visibility === 'selected'" v-model:checked="grantAttendees">{{ t("page.meetingSpace.inviteAttendees") }}</n-checkbox>
            <template v-if="manageable">
              <div class="flex flex-wrap gap-2">
                <n-select
                  v-model:value="grantToAdd"
                  :options="memberOptions"
                  filterable
                  clearable
                  class="max-w-sm"
                  :placeholder="t('page.meetings.choosePerson')"
                  data-testid="meeting-access-select"
                /><n-button @click="addGrant">
                  {{ t("page.meetings.grant") }}
                </n-button>
              </div>
              <div
                v-for="(grant, index) in form.access"
                :key="grant.user_id"
                class="flex flex-wrap items-center gap-3"
              >
                <span>{{
                  members.find(m => m.id === grant.user_id)?.name || t("page.meetings.formerMember")
                }}</span><n-select v-model:value="grant.role" :options="members.find(m => m.id === grant.user_id)?.can_write ? roleOptions : roleOptions.filter(r => r.value === 'viewer')" class="!w-36" /><n-button
                  quaternary
                  @click="form.access.splice(index, 1)"
                >
                  {{ t("common.delete") }}
                </n-button>
              </div>
            </template>
          </div>
        </details>
        <section class="min-w-0 border rounded-lg p-3" data-testid="meeting-minutes">
          <div class="mb-2 flex flex-wrap items-center justify-between gap-2">
            <h2 class="m-0 text-lg">{{ t("page.meetings.minutes") }}</h2>
            <aira-action-button v-if="editable && organize?.available.value" :disabled="busy" :aria-expanded="organize.visible.value" data-testid="meeting-organize" @click="organizeMinutes($event.currentTarget)">
              {{ t("page.airaActions.organize") }}
            </aira-action-button>
          </div>
          <div v-if="editable" class="mb-3 flex flex-wrap items-center gap-3">
            <label>{{ t("page.meetingSpace.format") }} <select v-model="form.body_format" @focus="flushVisual"><option value="aimd">AIMD</option><option value="md">Markdown</option></select></label>
            <label>{{ t("page.meetingSpace.importDoc") }} <input type="file" accept=".md,.aimd" @change="importMinutes"></label>
          </div>
          <n-input v-if="form.body_format === 'md'" v-model:value="form.body" type="textarea" :readonly="!editable" :autosize="{ minRows: 8 }" />
          <aimd-editor v-else
                       :key="surfaceRevision"
                       ref="visualSurface"
                       :model-value="form.body"
                       :mode="editorMode"
                       :readonly="!editable"
                       :locale="locale"
                       :show-aimd-toolbar="false"
                       :min-height="320"
                       :keep-inactive-editors-mounted="false"
                       @ready="onVisualReady"
                       @input.capture="markInput"
                       @update:model-value="updateBody($event, editorMode === 'wysiwyg')"
                       @update:mode="switchMode"
          />
        </section>
      </template>
      <action-batch ref="actionBatch" v-if="draftMeeting" :key="creationId" :meeting="draftMeeting" :members="members" :disabled="busy" draft :initial-titles="initialActionTitles" @rows="draftActions = $event" @dirty="actionDirty = $event" />
      <div v-if="selected" class="flex flex-wrap items-center gap-3 text-sm text-gray-500">
        <span>{{ t("page.meetings.created") }}
          {{ new Date(selected.created_at).toLocaleString() }}</span><span>{{ t("page.meetings.updated") }}
            {{ new Date(selected.updated_at).toLocaleString() }}</span>
        <n-button size="small" @click="loadHistory">
          {{ t("page.meetings.history") }}
        </n-button>
        <router-link
          :to="{ name: 'research-document-detail', params: { documentId: selected.id } }"
        >
          {{ t("page.meetings.document") }}
        </router-link>
      </div>
      <section v-if="selected" id="meeting-actions" class="border rounded-lg p-4" data-testid="meeting-work">
        <h2 class="text-lg">
          {{ t("page.meetings.actions") }}
        </h2>
        <p class="text-sm text-gray-500">
          {{ t("page.meetings.workHint") }}
        </p>
        <previous-meeting-work
          v-if="selected.can_comment && selected.can_create_work && !editing && projectId"
          :key="selected.id" v-model="discussionIds" :project-id="projectId" :meeting-id="selected.id"
          :people="projectPeople" :members="members" :disabled="busy" :linked="selected.work?.map(link => link.item.id)"
        >
          <n-button v-if="discussionIds.length" size="small" type="primary" :loading="busy" @click="saveDiscussion">
            {{ t('page.meetings.addDiscussion', { count: discussionIds.length }) }}
          </n-button>
        </previous-meeting-work>
        <ul class="m-0 list-none p-0">
          <li
            v-for="link in selected.work"
            :key="link.item.id"
            class="border-b py-2 [overflow-wrap:anywhere]"
          >
            <router-link
              class="text-primary"
              :to="{ name: 'project-work', params: route.params, query: { item: link.item.id } }"
            >
              {{ link.item.title }}
            </router-link>
            <work-follow-up-details :item="link.item" :members="members" :people="projectPeople" />
          </li>
        </ul>
        <template v-if="selected.can_comment">
          <p v-if="dirty" class="text-amber-700">
            {{ t("page.meetings.saveFirst") }}
          </p>
          <div class="mt-4 flex flex-wrap gap-2">
            <n-select
              v-model:value="workId"
              filterable
              clearable
              :options="workOptions.map(w => ({ label: w.title, value: w.id }))"
              class="max-w-xl"
              :placeholder="t('page.meetings.existingWork')"
            /><n-button :disabled="busy || dirty || !workId" @click="linkWork">
              {{ t("page.meetings.linkWork") }}
            </n-button>
          </div>
          <action-batch ref="actionBatch" v-if="selected.can_create_work" :key="selected.id" :meeting="selected" :members="members" :disabled="busy || dirty" @dirty="actionDirty = $event" @saved="selected = $event; notice = t('page.meetings.actionSaved')" />
        </template>
      </section>
      <section v-if="selected" class="border rounded-lg p-4" data-testid="meeting-comments">
        <h2 class="text-lg">
          {{ t("page.meetings.comments") }}
        </h2>
        <article v-for="item in comments" :key="item.id" class="border-b py-3">
          <p class="text-sm text-gray-500">
            {{ item.author.name || item.author.username }} ·
            {{ new Date(item.created_at).toLocaleString() }}
          </p><p class="whitespace-pre-wrap break-words">
            {{ item.body }}
          </p>
        </article>
        <n-pagination
          v-if="commentTotal > 50"
          v-model:page="commentPage"
          :item-count="commentTotal"
          :page-size="50"
          @update:page="loadComments"
        />
        <form v-if="selected.can_comment" class="mt-4 space-y-3" @submit.prevent="postComment">
          <n-input
            v-model:value="comment"
            type="textarea"
            :placeholder="t('page.meetings.commentHint')"
            data-testid="meeting-comment"
          /><n-button
            attr-type="submit"
            :disabled="busy || !comment.trim()"
            data-testid="meeting-comment-send"
          >
            {{ t("page.meetings.postComment") }}
          </n-button>
        </form>
      </section>
    </template>
    <n-modal
      v-model:show="showHistory"
      preset="card"
      :title="t('page.meetings.history')"
      class="max-w-3xl"
    >
      <article v-for="revision in history" :key="revision.revision" class="border-b py-4">
        <h3>v{{ revision.revision }} · {{ revision.change_summary }}</h3><pre class="whitespace-pre-wrap break-words">{{ revision.snapshot.body }}</pre>
      </article>
    </n-modal>
  </section>
</template>

<style scoped>
.meeting-filters { display: grid; gap: 8px; }
.meeting-search-row { display: flex; align-items: center; gap: 8px; }
.meeting-search-row .n-input { min-width: 0; max-width: 20rem; }
.meeting-search-row :is(.n-input, .n-button) { --n-height: 34px !important; }
.meeting-search-submit { display: grid; place-items: center; width: 28px; height: 30px; }
.meeting-filter-fields { display: flex; align-items: end; flex-wrap: wrap; gap: 8px 12px; }
.meeting-filter-fields label { display: grid; gap: 3px; min-width: 0; font-size: 13px; }
.meeting-filter-fields label:first-child { width: 14rem; }
.meeting-filter-fields .meeting-date { width: 10rem; }
@media (max-width: 600px) {
  .meeting-search-row .n-input { max-width: none; }
  .meeting-search-row :is(.n-input, .n-button), .meeting-filter-fields .n-select { --n-height: 40px !important; }
  .meeting-search-submit { width: 36px; height: 36px; }
  .meeting-filter-fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .meeting-filter-fields label:first-child { grid-column: 1 / -1; width: auto; }
  .meeting-filter-fields .meeting-date { width: 100%; min-width: 0; min-height: 40px; }
}
.meeting-date {
  display: block;
  width: 100%;
  min-height: 34px;
  border: 1px solid #d1d5db;
  border-radius: 4px;
  padding: 4px 8px;
}
.meeting-save-bar {
  position: sticky;
  top: 0;
  z-index: 5;
}
label {
  font-size: 14px;
}
</style>
