<script setup lang="ts">
import type { Meeting, MeetingActionDraft, MeetingMember } from "@/service/api/meetings"
import PeoplePicker from "@/components/project/people-picker.vue"
import { saveMeetingActions } from "@/service/api/meetings"
import { blankWork } from "@/service/api/project-work"
import { useI18n } from "vue-i18n"

const props = defineProps<{ meeting: Meeting, members: MeetingMember[], disabled: boolean, draft?: boolean, initialTitles?: string[] }>()
const emit = defineEmits<{ saved: [meeting: Meeting], dirty: [value: boolean], rows: [value: MeetingActionDraft[]] }>()
const { t } = useI18n()
const rows = ref<MeetingActionDraft[]>((props.initialTitles ?? []).map(title => ({ ...blankWork(), id: crypto.randomUUID(), title })))
const titles = ref("")
const busy = ref(false)
const error = ref("")
let requestId = crypto.randomUUID()
const dirty = computed(() => rows.value.length > 0 || Boolean(titles.value.trim()))
watch(dirty, value => emit("dirty", value), { immediate: true })
watch(rows, value => emit("rows", value), { deep: true, immediate: true })
function add(title = "") {
  if (rows.value.length < 50)
    rows.value.push({ ...blankWork(), id: crypto.randomUUID(), title })
}
function importTitles() {
  const values = titles.value.split(/\r?\n/).map(v => v.replace(/^\s*(?:[-*]|\d+[.)、])\s*/, "").trim()).filter(Boolean)
  if (values.length + rows.value.length > 50) {
    error.value = t("page.meetings.batchLimit")
    return
  }
  values.forEach(add)
  titles.value = ""
}
function choose(row: MeetingActionDraft, value: string | string[] | null, multiple = false) {
  const values = Array.isArray(value) ? value : typeof value === "string" ? [value] : []
  if (multiple) {
    row.collaborator_ids = values.filter(v => v.startsWith("user:")).map(v => v.slice(5))
    row.collaborator_person_ids = values.filter(v => v.startsWith("person:")).map(v => v.slice(7))
  }
  else {
    row.assignee_person_id = values[0]?.startsWith("person:") ? values[0].slice(7) : null
    row.assignee_user_id = values[0]?.startsWith("user:") ? values[0].slice(5) : null
  }
}
async function save() {
  if (!rows.value.length || rows.value.some(row => !row.title.trim()) || busy.value || props.disabled)
    return
  busy.value = true
  error.value = ""
  try {
    const result = await saveMeetingActions(props.meeting.id, requestId, props.meeting.revision, rows.value)
    rows.value = []
    requestId = crypto.randomUUID()
    emit("dirty", false)
    emit("saved", result)
  }
  catch (e) {
    const status = (e as { response?: { status?: number } }).response?.status
    error.value = t(status === 409 ? "page.meetings.conflict" : "page.meetings.batchFailed")
  }
  finally { busy.value = false }
}
</script>

<template>
  <section class="mt-4 space-y-3" data-testid="meeting-action-batch">
    <h3 class="text-base font-medium">{{ t("page.meetings.batchTitle") }}</h3>
    <p class="text-sm text-gray-500">{{ t("page.meetings.actionAudience") }}</p>
    <details>
      <summary class="cursor-pointer text-sm">{{ t("page.meetings.pasteTitles") }}</summary>
      <n-input v-model:value="titles" class="my-2" type="textarea" :disabled="busy || disabled" :placeholder="t('page.meetings.onePerLine')" />
      <n-button size="small" :disabled="!titles.trim() || busy || disabled" @click="importTitles">{{ t("page.meetings.addRows") }}</n-button>
    </details>
    <article v-for="(row, index) in rows" :key="row.id" class="border rounded-lg p-3 space-y-3" :data-testid="`meeting-action-row-${index}`">
      <div class="flex items-start gap-2">
        <span class="pt-1 text-gray-500">{{ index + 1 }}</span>
        <n-input v-model:value="row.title" :maxlength="255" :disabled="busy || disabled" :placeholder="t('page.meetings.actionTitle')" data-testid="meeting-action-title" />
        <n-button quaternary :disabled="busy || disabled" @click="rows.splice(index, 1)">{{ t("common.delete") }}</n-button>
      </div>
      <div class="grid gap-3 sm:grid-cols-2">
        <label>{{ t("page.projectWork.assignee") }}<people-picker :model-value="row.assignee_person_id ? `person:${row.assignee_person_id}` : row.assignee_user_id ? `user:${row.assignee_user_id}` : null" :project-id="meeting.project_id" :members="members.filter(m => m.can_write)" :disabled="busy || disabled" @update:model-value="choose(row, $event)" /></label>
        <label>{{ t("page.projectWork.end") }}<input v-model="row.planned_end" type="date" class="w-full border rounded p-2" :disabled="busy || disabled"></label>
        <label class="sm:col-span-2">{{ t("page.projectWork.deadlineNote") }}<n-input v-model:value="row.deadline_note" :maxlength="1000" :disabled="busy || disabled" /></label>
      </div>
      <details>
        <summary class="cursor-pointer text-sm">{{ t("page.meetings.actionDetails") }}</summary>
        <div class="mt-3 space-y-3">
          <label class="block">{{ t("page.projectWork.collaborators") }}<people-picker :model-value="[...row.collaborator_ids.map(id => `user:${id}`), ...row.collaborator_person_ids.map(id => `person:${id}`)]" multiple :project-id="meeting.project_id" :members="members.filter(m => m.can_write)" :disabled="busy || disabled" @update:model-value="choose(row, $event, true)" /></label>
          <label class="block">{{ t("page.projectWork.goal") }}<n-input v-model:value="row.goal" type="textarea" :maxlength="20000" :disabled="busy || disabled" /></label>
          <label class="block">{{ t("page.projectWork.acceptance") }}<n-input v-model:value="row.acceptance" type="textarea" :maxlength="10000" :disabled="busy || disabled" /></label>
        </div>
      </details>
    </article>
    <p v-if="error" class="text-sm text-red-600" role="alert">{{ error }}</p>
    <div class="flex flex-wrap gap-2">
      <n-button :disabled="busy || disabled || rows.length >= 50" @click="add()" data-testid="meeting-add-action-row">{{ t("page.meetings.addActionRow") }}</n-button>
      <n-button v-if="rows.length && !draft" type="primary" :loading="busy" :disabled="disabled || rows.some(row => !row.title.trim())" @click="save" data-testid="meeting-create-action">{{ t("page.meetings.saveActions", { count: rows.length }) }}</n-button>
    </div>
  </section>
</template>
