<script setup lang="ts">
import type { Meeting, MeetingComment, MeetingContent, MeetingMember } from "@/service/api/meetings"
import type { ProjectWork } from "@/service/api/project-work"
import {
  addMeetingComment,
  createMeetingAction,
  getMeeting,
  linkMeetingWork,
  listMeetings,
  meetingComments,
  meetingContent,
  meetingMembers,
  saveMeeting,
} from "@/service/api/meetings"
import { listProjectWork } from "@/service/api/project-work"
import { researchDocumentHistory } from "@/service/api/research-documents"
import { documentTimeZone, localDocumentDate } from "@/utils/documentBrowse"
import { preserveVisualFenceMetadata } from "@/utils/recorderMarkdown"
import { restoreAimdInlineTemplates } from "@airalogy/aimd-core"
import { AimdEditor } from "@airalogy/aimd-editor/vue"
import { useDialog } from "naive-ui"
import { useI18n } from "vue-i18n"
import { onBeforeRouteLeave, onBeforeRouteUpdate } from "vue-router"
import { useProjectInfoStore } from "../project-protocols/hooks/useProjectInfoStore"

const { t, locale } = useI18n()
const dialog = useDialog()
const route = useRoute()
const router = useRouter()
const { projectInfo } = useProjectInfoStore()
const projectId = computed(() => projectInfo.value?.id)
const items = ref<Meeting[]>([])
const total = ref(0)
const page = ref(1)
const q = ref("")
const dateFrom = ref("")
const dateTo = ref("")
const participantFilter = ref<string | null>(null)
const loading = ref(false)
const busy = ref(false)
const error = ref("")
const notice = ref("")
const canCreate = ref(false)
const members = ref<MeetingMember[]>([])
const selected = ref<Meeting>()
const form = ref<MeetingContent>()
const saved = ref("")
const creationId = ref("")
const editorMode = ref<"wysiwyg" | "source">("wysiwyg")
const comment = ref("")
const comments = ref<MeetingComment[]>([])
const commentPage = ref(1)
const commentTotal = ref(0)
const workOptions = ref<ProjectWork[]>([])
const workId = ref<string | null>(null)
const actionTitle = ref("")
const actionAssignee = ref<string | null>(null)
const actionEnd = ref("")
const externalName = ref("")
const externalOrganization = ref("")
const participantToAdd = ref<string | null>(null)
const grantToAdd = ref<string | null>(null)
const history = ref<{ revision: number, change_summary: string, snapshot: { body?: string } }[]>([])
const showHistory = ref(false)
let commentKey = crypto.randomUUID()
let actionKey = crypto.randomUUID()
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
function flushVisual() {
  const editor = visualSurface.value?.getMilkdownEditor?.()
  if (editorMode.value !== "wysiwyg" || !editable.value || !editor)
    return
  const markdown = readVisualMarkdown(editor)
  if (markdown !== visualLastMarkdown)
    updateBody(markdown, true)
  else visualPending.value = false
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
  page.value = 1
  void loadList()
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
      q: q.value,
      participant_id: participantFilter.value || undefined,
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
  form.value = undefined
  comments.value = []
  comment.value = ""
  actionTitle.value = ""
  if (!id)
    return
  if (id === "new") {
    creationId.value = crypto.randomUUID()
    form.value = {
      title: "",
      body: t("page.meetings.template"),
      status: "held",
      occurred_at: new Date(`${localDocumentDate()}T00:00:00`).toISOString(),
      scheduled_at: null,
      time_precision: "date",
      time_zone: documentTimeZone(),
      visibility: "project",
      participants: [],
      access: [],
    }
    saved.value = JSON.stringify(form.value)
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
    const result = await saveMeeting(
      selected.value?.id || creationId.value,
      projectId.value,
      form.value,
      selected.value?.revision,
    )
    accept(result)
    notice.value = t("page.meetings.saved")
    if (route.query.meeting === "new") {
      await router.replace({
        name: "project-meetings",
        params: route.params,
        query: { ...route.query, meeting: result.id },
      })
    }
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
async function createAction() {
  if (!selected.value || !actionTitle.value.trim())
    return
  busy.value = true
  error.value = ""
  try {
    selected.value = await createMeetingAction(selected.value.id, {
      id: actionKey,
      expected_revision: selected.value.revision,
      title: actionTitle.value,
      assignee_user_id: actionAssignee.value,
      planned_end: actionEnd.value || null,
    })
    actionKey = crypto.randomUUID()
    actionTitle.value = ""
    actionAssignee.value = null
    actionEnd.value = ""
    notice.value = t("page.meetings.actionSaved")
  }
  catch (e) {
    error.value = message(e)
  }
  finally {
    busy.value = false
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
  if (!dirty.value)
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
onBeforeRouteUpdate((to, from) => to.query.meeting === from.query.meeting || guard())
function beforeUnload(e: BeforeUnloadEvent) {
  flushVisual()
  if (dirty.value) {
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
      await loadList()
      await loadSelected()
    }
    catch (e) {
      error.value = message(e)
    }
  },
  { immediate: true },
)
watch(() => route.query.meeting, loadSelected)
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
      <form
        class="flex flex-wrap items-end gap-3"
        @submit.prevent="filterList"
      >
        <label>{{ t("page.meetings.search") }}<n-input v-model:value="q" data-testid="meeting-search" /></label>
        <label class="min-w-48">{{ t("page.meetings.participant")
        }}<n-select
          v-model:value="participantFilter"
          :options="memberOptions"
          clearable
          filterable
        /></label>
        <label>{{ t("page.meetings.from") }}<input v-model="dateFrom" type="date" class="meeting-date"></label>
        <label>{{ t("page.meetings.to") }}<input v-model="dateTo" type="date" class="meeting-date"></label>
        <n-button attr-type="submit">
          {{ t("page.meetings.filter") }}
        </n-button>
      </form>
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
            : dirty
              ? t("page.meetings.unsaved")
              : selected
                ? t("page.meetings.saved")
                : t("page.meetings.newDraft")
        }}</span>
        <n-button
          v-if="editable"
          type="primary"
          :loading="busy"
          :disabled="!form.title.trim() || (!dirty && !!selected)"
          data-testid="meeting-save"
          @click="save"
        >
          {{ t("common.save") }}
        </n-button>
      </div>
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
      <details :open="!selected" class="border rounded-lg p-4" data-testid="meeting-people">
        <summary class="cursor-pointer font-medium">
          {{ t("page.meetings.peopleAndAccess") }} · {{ form.participants.length }} ·
          {{ t(`page.meetings.visibility.${form.visibility}`) }}
        </summary>
        <div class="mt-4 space-y-4">
          <p class="text-sm text-gray-500">
            {{ t("page.meetings.participantHint") }}
          </p>
          <div v-if="manageable" class="flex flex-wrap gap-2">
            <n-select
              v-model:value="participantToAdd"
              :options="memberOptions"
              filterable
              clearable
              class="max-w-sm"
              :placeholder="t('page.meetings.choosePerson')"
              data-testid="meeting-participant-select"
            /><n-button @click="addParticipant">
              {{ t("page.meetings.addParticipant") }}
            </n-button>
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
        <h2 class="text-lg">
          {{ t("page.meetings.minutes") }}
        </h2>
        <aimd-editor
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
      <section v-if="selected" class="border rounded-lg p-4" data-testid="meeting-work">
        <h2 class="text-lg">
          {{ t("page.meetings.actions") }}
        </h2>
        <p class="text-sm text-gray-500">
          {{ t("page.meetings.workHint") }}
        </p>
        <ul class="m-0 list-none p-0">
          <li
            v-for="link in selected.work"
            :key="link.item.id"
            class="flex flex-wrap items-center justify-between gap-2 border-b py-3"
          >
            <router-link
              class="text-primary"
              :to="{ name: 'project-work', params: route.params, query: { item: link.item.id } }"
            >
              {{ link.item.title }}
            </router-link><span>{{ t(`page.projectWork.states.${link.item.state}`) }} ·
              {{
                members.find(m => m.id === link.item.assignee_user_id)?.name
                  || t("page.projectWork.unassigned")
              }}</span>
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
          <form class="grid mt-4 gap-3 sm:grid-cols-2" @submit.prevent="createAction">
            <label class="sm:col-span-2">{{ t("page.meetings.actionTitle")
            }}<n-input v-model:value="actionTitle" data-testid="meeting-action-title" /></label>
            <label>{{ t("page.projectWork.assignee")
            }}<n-select
              v-model:value="actionAssignee"
              :options="memberOptions.filter(o => members.find(m => m.id === o.value)?.can_write)"
              clearable
              filterable
            /></label>
            <label>{{ t("page.meetings.due")
            }}<input v-model="actionEnd" type="date" class="meeting-date"></label>
            <p class="m-0 text-sm text-gray-500 sm:col-span-2">
              {{ t("page.meetings.actionAudience") }}
            </p>
            <n-button
              attr-type="submit"
              :disabled="busy || dirty || !actionTitle.trim()"
              data-testid="meeting-create-action"
            >
              {{ t("page.meetings.createAction") }}
            </n-button>
          </form>
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
