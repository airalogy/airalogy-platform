<script setup lang="ts">
import type { MeetingConversation, MeetingProposal } from "@/service/api/meetings"
import { getMeetingConversation, requestMeetingDraft } from "@/service/api/meetings"
import { useI18n } from "vue-i18n"

const props = defineProps<{ projectId: string, projectName: string, meetingName: string, meetingId: string | null, initialChat: string, canSend: boolean }>()
const emit = defineEmits<{ close: [], restart: [], review: [proposal: MeetingProposal] }>()
const { t } = useI18n()
const confirmRestart = ref(false)
const input = ref("")
const turns = ref<{ user: string, reply: string }[]>([])
const proposal = ref<MeetingProposal | null>(null)
const error = ref("")
const busy = ref(false)
const history = ref<HTMLElement>()
const conversationId = ref(crypto.randomUUID() as string)
const linkedMeeting = ref<string | null>(null)
let scopeSelected = false
const restoreFailed = ref(false)
let retry: { text: string, id: string } | undefined
let controller = new AbortController()
onBeforeUnmount(() => controller.abort())

function applyConversation(value: MeetingConversation) {
  if (value.project_id !== props.projectId || value.id !== conversationId.value)
    throw new Error("Conversation unavailable")
  linkedMeeting.value = value.meeting_id
  turns.value = value.turns
  proposal.value = value.proposal
  scopeSelected = true
}

function newConversation() {
  controller.abort()
  controller = new AbortController()
  conversationId.value = crypto.randomUUID()
  scopeSelected = false
  restoreFailed.value = false
  linkedMeeting.value = null
  retry = undefined
  turns.value = []
  input.value = ""
  proposal.value = null
  error.value = ""
  busy.value = false
  confirmRestart.value = false
}

async function restore(id: string) {
  controller.abort()
  controller = new AbortController()
  const { signal } = controller
  conversationId.value = id
  busy.value = true
  restoreFailed.value = false
  error.value = ""
  // Inaccessible or stale content must never remain on screen.
  turns.value = []
  proposal.value = null
  try {
    const saved = await getMeetingConversation(id, signal)
    if (!signal.aborted)
      applyConversation(saved)
  }
  catch {
    if (!signal.aborted) {
      restoreFailed.value = true
      error.value = t("chat.historyUnavailable")
    }
  }
  finally {
    if (!signal.aborted)
      busy.value = false
  }
}

watch(() => props.initialChat, (id) => {
  if (id) {
    newConversation()
    void restore(id)
  }
}, { immediate: true })

async function send() {
  const message = input.value.trim()
  if (!message || !props.canSend || busy.value || restoreFailed.value || turns.value.length >= 8)
    return
  busy.value = true
  error.value = ""
  const { signal } = controller
  if (!retry || retry.text !== message)
    retry = { text: message, id: crypto.randomUUID() }
  if (!scopeSelected) {
    linkedMeeting.value = props.meetingId
    scopeSelected = true
  }
  try {
    const saved = await requestMeetingDraft(props.projectId, message, conversationId.value, linkedMeeting.value, turns.value.length, retry.id, signal)
    if (signal.aborted)
      return
    applyConversation(saved)
    retry = undefined
    input.value = ""
    await nextTick()
    history.value?.scrollTo({ top: history.value.scrollHeight })
  }
  catch (e) {
    if (signal.aborted)
      return
    const status = (e as { response?: { status: number } }).response?.status
    if (status === 409 && (e as { response?: { data?: { detail?: string } } }).response?.data?.detail === "Reload conversation before continuing") {
      await restore(conversationId.value)
      if (!restoreFailed.value)
        error.value = t("chat.changedOnServer")
    }
    else {
      if (status === 403 || status === 404) {
        turns.value = []
        proposal.value = null
        restoreFailed.value = true
      }
      error.value = t(status === 403 || status === 404 ? "page.meetings.unavailable" : status === 503 ? "page.projectAira.unavailable" : "chat.sendUnconfirmed")
    }
  }
  finally {
    if (!signal.aborted)
      busy.value = false
  }
}
</script>

<template>
  <section class="aira-panel" data-testid="project-aira-panel" :aria-label="t('page.projectAira.panel')">
    <header>
      <div class="flex items-center gap-2">
        <h2 class="m-0 flex items-center gap-2 text-lg font-semibold">
          <n-icon :size="24" aria-hidden="true"><icon-shared-airalogy-chat /></n-icon>
          Aira
        </h2>
        <div class="ml-auto flex shrink-0 items-center gap-1 whitespace-nowrap">
          <router-link :to="{ name: 'global-chat' }" target="_blank" rel="noopener" class="text-sm text-primary">{{ t("common.allChats") }} ↗</router-link>
          <n-button v-if="turns.length || restoreFailed" size="small" quaternary :disabled="busy" @click="confirmRestart = true">{{ t("page.projectAira.restart") }}</n-button>
          <n-button size="small" quaternary :aria-label="t('common.close')" @click="emit('close')">
            <template #icon><n-icon><icon-tabler-x /></n-icon></template>
          </n-button>
        </div>
      </div>
      <p class="m-0 mt-1 truncate text-sm color-text-secondary" :title="projectName">{{ projectName }}</p>
      <p v-if="meetingName" class="m-0 truncate text-sm" :title="meetingName">{{ meetingName }}</p>
    </header>
    <div v-if="confirmRestart" class="my-2 border rounded-lg p-2 text-sm">
      <p>{{ t("page.projectAira.restartHint") }}</p>
      <n-button size="small" @click="confirmRestart = false">{{ t("common.cancel") }}</n-button>
      <n-button size="small" class="ml-2" @click="newConversation(); emit('restart')">{{ t("page.projectAira.restart") }}</n-button>
    </div>
    <div ref="history" class="min-h-0 flex-1 overflow-y-auto py-3">
      <p v-if="!turns.length" class="text-sm color-text-secondary">{{ t("page.projectAira.hint") }}</p>
      <div v-for="(turn, index) in turns" :key="index" class="mb-4 space-y-2 text-sm">
        <p class="whitespace-pre-wrap break-words rounded-lg bg-gray-100 p-2">{{ turn.user }}</p>
        <p class="whitespace-pre-wrap break-words">{{ turn.reply }}</p>
      </div>
      <section v-if="proposal" class="border rounded-lg p-3 text-sm space-y-3" data-testid="aira-proposal">
        <h3 class="m-0 break-words text-base">{{ proposal.title }}</h3>
        <p class="whitespace-pre-wrap break-words">{{ proposal.body }}</p>
        <ul v-if="proposal.actions.length" class="list-disc pl-5">
          <li v-for="(action, index) in proposal.actions" :key="index">{{ action }}</li>
        </ul>
        <n-button size="small" type="primary" :disabled="busy" @click="emit('review', proposal)">{{ t("page.projectAira.review") }}</n-button>
      </section>
    </div>
    <form class="border-t pt-3 space-y-2" @submit.prevent="send">
      <n-button v-if="restoreFailed" size="small" @click="restore(conversationId)">{{ t("common.retry") }}</n-button>
      <p v-if="error" role="alert" class="text-sm text-red-700">{{ error }}</p>
      <p v-if="turns.length >= 8" class="text-sm">{{ t("page.projectAira.limit") }}</p>
      <n-input v-model:value="input" type="textarea" :maxlength="16000" :disabled="!canSend || busy || restoreFailed || turns.length >= 8" :autosize="{ minRows: 2, maxRows: 6 }" :placeholder="t('page.projectAira.input')" :aria-label="t('page.projectAira.input')" />
      <div class="flex justify-end">
        <n-button attr-type="submit" size="small" :disabled="!canSend || restoreFailed || !input.trim() || confirmRestart || turns.length >= 8" :loading="busy">{{ t("page.projectAira.send") }}</n-button>
      </div>
    </form>
  </section>
</template>

<style scoped>
.aira-panel {
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  min-width: 0;
  padding: 16px;
  padding-bottom: max(16px, env(safe-area-inset-bottom));
}
.aira-panel > header, .aira-panel > form { flex-shrink: 0; }
</style>
