<script setup lang="ts">
import type { Meeting, MeetingMember } from "@/service/api/meetings"
import { getMeeting, listMeetings } from "@/service/api/meetings"
import { documentTimeZone, localDocumentDate } from "@/utils/documentBrowse"
import { useI18n } from "vue-i18n"
import WorkFollowUpDetails from "./work-follow-up-details.vue"

const props = defineProps<{ projectId: string, meetingId: string, members: MeetingMember[], linked?: string[], disabled: boolean }>()
const checked = defineModel<string[]>({ required: true })
const { t } = useI18n()
const opened = ref(false)
const meetings = ref<Meeting[]>([])
const sourceId = ref("")
const source = ref<Meeting>()
const loadedPages = ref(0)
const more = ref(false)
const listing = ref(false)
const reading = ref(false)
const listError = ref(false)
const readError = ref(false)
let readVersion = 0
const unfinished = computed(() => source.value?.work?.map(link => link.item).filter(item => item.state !== "done" && item.state !== "cancelled") || [])

async function loadPage() {
  if (listing.value)
    return
  listing.value = true
  listError.value = false
  try {
    const page = loadedPages.value + 1
    const result = await listMeetings({ project_id: props.projectId, status: "held", time_zone: documentTimeZone(), page })
    meetings.value.push(...result.items.filter(m => m.id !== props.meetingId && !meetings.value.some(existing => existing.id === m.id)))
    loadedPages.value = page
    more.value = page * 20 < result.total
  }
  catch {
    listError.value = true
  }
  finally {
    listing.value = false
  }
}
function toggle(event: Event) {
  opened.value = (event.currentTarget as HTMLDetailsElement).open
  if (opened.value && !loadedPages.value)
    void loadPage()
}
async function readSource() {
  const version = ++readVersion
  source.value = undefined
  checked.value = []
  readError.value = false
  reading.value = Boolean(sourceId.value)
  if (!sourceId.value)
    return
  try {
    const result = await getMeeting(sourceId.value)
    if (version !== readVersion)
      return
    if (result.project_id !== props.projectId || result.status !== "held")
      throw new Error("Unavailable meeting")
    source.value = result
  }
  catch {
    if (version === readVersion)
      readError.value = true
  }
  finally {
    if (version === readVersion)
      reading.value = false
  }
}
</script>

<template>
  <details class="follow-up" data-testid="meeting-follow-up" @toggle="toggle">
    <summary>{{ t('page.meetings.reviewPrevious') }}<span v-if="checked.length"> · {{ t('page.meetings.discussionCount', { count: checked.length }) }}</span></summary>
    <div v-if="opened" class="mt-2">
      <label v-if="meetings.length" class="grid gap-1 text-sm">
        {{ t('page.meetings.previousMeeting') }}
        <select v-model="sourceId" :disabled="disabled" class="source-select" @change="readSource">
          <option value="">{{ t('page.meetings.choosePrevious') }}</option>
          <option v-for="meeting in meetings" :key="meeting.id" :value="meeting.id">
            {{ meeting.occurred_at ? localDocumentDate(new Date(meeting.occurred_at)) : '' }} · {{ meeting.title }}
          </option>
        </select>
      </label>
      <n-button v-if="more || listError" size="small" text :disabled="disabled || listing" @click="loadPage">
        {{ listError ? t('page.meetings.retryPrevious') : t('page.meetings.olderMeetings') }}
      </n-button>
      <p v-if="listing || reading" role="status">{{ t('page.meetings.loadingPrevious') }}</p>
      <p v-else-if="!meetings.length && !listError">{{ t('page.meetings.noPrevious') }}</p>
      <p v-if="readError" role="alert">
        {{ t('page.meetings.unavailable') }} <n-button text size="small" @click="readSource">{{ t('page.meetings.retryPrevious') }}</n-button>
      </p>
      <template v-if="source">
        <p v-if="!unfinished.length" role="status">{{ t('page.meetings.noOpenWork') }}</p>
        <ul v-else class="m-0 list-none p-0 divide-y">
          <li v-for="item in unfinished" :key="item.id">
            <label class="follow-row">
              <input v-model="checked" type="checkbox" :value="item.id" :disabled="disabled || linked?.includes(item.id) || (checked.length >= 50 && !checked.includes(item.id))">
              <span>
                <strong>{{ item.title }}</strong>
                <small v-if="linked?.includes(item.id)"> · {{ t('page.meetings.alreadyLinked') }}</small>
                <work-follow-up-details :item="item" :members="members" show-empty />
              </span>
            </label>
          </li>
        </ul>
        <slot />
      </template>
    </div>
  </details>
</template>

<style scoped>
.follow-up { min-width: 0; padding: 10px 14px; border: 1px solid #dce1e8; border-radius: 8px; }
summary { cursor: pointer; font-weight: 600; }
.source-select { width: 100%; max-width: 36rem; min-width: 0; min-height: 36px; border: 1px solid #b7c1cf; border-radius: 5px; padding: 4px 8px; background: white; }
.follow-row { display: grid; grid-template-columns: 18px minmax(0, 1fr); gap: 10px; align-items: start; padding: 9px 0; overflow-wrap: anywhere; cursor: pointer; }
.follow-row input { margin: 4px 0 0; width: 16px; height: 16px; }
</style>
