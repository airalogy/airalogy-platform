<script setup lang="ts">
import type { MeetingProposal } from "@/service/api/meetings"
import { requestMeetingDraft } from "@/service/api/meetings"
import { useI18n } from "vue-i18n"

const props = defineProps<{ projectId: string, projectName: string }>()
const emit = defineEmits<{ close: [], review: [proposal: MeetingProposal] }>()
const { t } = useI18n()
const confirmRestart = ref(false)
const input = ref("")
const turns = ref<{ user: string, reply: string }[]>([])
const proposal = ref<MeetingProposal | null>(null)
const error = ref("")
const busy = ref(false)
const history = ref<HTMLElement>()
let active = true
onBeforeUnmount(() => {
  active = false
})

function newConversation() {
  turns.value = []
  input.value = ""
  proposal.value = null
  error.value = ""
  confirmRestart.value = false
}

async function send() {
  const message = input.value.trim()
  if (!message || busy.value || turns.value.length >= 8)
    return
  busy.value = true
  error.value = ""
  try {
    const reply = await requestMeetingDraft(props.projectId, message, turns.value, proposal.value)
    if (!active)
      return
    turns.value.push({ user: message, reply: reply.message })
    if (reply.draft)
      proposal.value = reply.draft
    input.value = ""
    await nextTick()
    history.value?.scrollTo({ top: history.value.scrollHeight })
  }
  catch (e) {
    const status = (e as { response?: { status: number } }).response?.status
    error.value = t(status === 403 || status === 404 ? "page.meetings.unavailable" : status === 503 ? "page.projectAira.unavailable" : "page.projectAira.failed")
  }
  finally { busy.value = false }
}
</script>

<template>
  <aside class="aira-panel" data-testid="project-aira-panel" :aria-label="t('page.projectAira.panel')">
    <header class="flex items-start justify-between gap-2">
      <div>
        <h2 class="m-0 text-lg font-semibold">Aira</h2>
        <p class="m-0 text-sm color-text-secondary">{{ projectName }}</p>
      </div>
      <div class="flex items-center gap-1">
        <n-button v-if="turns.length" size="small" quaternary :disabled="busy" @click="confirmRestart = true">{{ t("page.projectAira.restart") }}</n-button>
        <n-button size="small" quaternary :aria-label="t('common.close')" @click="emit('close')">
          <template #icon><n-icon><icon-tabler-x /></n-icon></template>
        </n-button>
      </div>
    </header>
    <div v-if="confirmRestart" class="my-2 border rounded-lg p-2 text-sm">
      <p>{{ t("page.projectAira.restartHint") }}</p>
      <n-button size="small" @click="confirmRestart = false">{{ t("common.cancel") }}</n-button>
      <n-button size="small" class="ml-2" @click="newConversation">{{ t("page.projectAira.restart") }}</n-button>
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
      <p v-if="error" role="alert" class="text-sm text-red-700">{{ error }}</p>
      <p v-if="turns.length >= 8" class="text-sm">{{ t("page.projectAira.limit") }}</p>
      <n-input v-model:value="input" type="textarea" :maxlength="16000" :disabled="busy || turns.length >= 8" :autosize="{ minRows: 2, maxRows: 6 }" :placeholder="t('page.projectAira.input')" :aria-label="t('page.projectAira.input')" />
      <div class="flex justify-end">
        <n-button attr-type="submit" size="small" :disabled="!input.trim() || confirmRestart || turns.length >= 8" :loading="busy">{{ t("page.projectAira.send") }}</n-button>
      </div>
    </form>
  </aside>
</template>

<style scoped>
.aira-panel { position: sticky; top: 16px; display: flex; flex-direction: column; height: calc(100dvh - 100px); min-width: 0; padding: 16px; background: var(--n-color, white); border: 1px solid #dce2ea; border-radius: 12px; }
@media (max-width: 899px) {
  .aira-panel { position: static; height: 100dvh; border: 0; border-radius: 0; padding-bottom: max(16px, env(safe-area-inset-bottom)); }
}
</style>
