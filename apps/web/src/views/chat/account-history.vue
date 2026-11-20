<script setup lang="ts">
import { type AccountChatSummary, getAccountChatHistory, getChatConversation } from "@/service/api/chat"
import { useChatInfoStore } from "@airalogy/components/chat/composables/useChatInfoStore"
import { useChatStore } from "@airalogy/components/chat/store"
import { localizeMemoryTitle } from "@airalogy/components/chat/utils/memory-history"

const emit = defineEmits<{ opened: [] }>()
const store = useChatStore()
const router = useRouter()
const { loading: responding } = useChatInfoStore()!
const items = ref<AccountChatSummary[]>([])
const displayItems = computed(() => items.value.map(item => ({
  ...item,
  title: localizeMemoryTitle(item.title, item.title_is_memory_request),
})))
const page = ref(1)
const more = ref(false)
const busy = ref(false)
const failed = ref(false)
const openError = ref(false)
let sequence = 0

async function load(next: boolean) {
  if (busy.value)
    return
  busy.value = true
  failed.value = false
  try {
    const number = next ? page.value + 1 : 1
    const data = await getAccountChatHistory(number)
    const previous = next ? items.value : []
    const byId = new Map(previous.map(item => [item.id, item]))
    data.items.forEach(item => byId.set(item.id, item))
    items.value = [...byId.values()]
    page.value = number
    more.value = data.has_more
  }
  catch { failed.value = true }
  finally { busy.value = false }
}

async function select(item: AccountChatSummary) {
  const { id } = item
  const current = ++sequence
  openError.value = false
  try {
    if (item.kind === "meeting") {
      await router.push({ name: "project-meetings", params: { labUid: item.lab_uid, projectUid: item.project_uid }, query: { aira: id, meeting: item.meeting_id || undefined } })
      emit("opened")
      return
    }
    const detail = await getChatConversation(id)
    if (sequence !== current || responding.value)
      return
    if (!detail || detail.id !== id)
      throw new Error("Unavailable")
    store.restoreAccountConversation(detail)
    store.reloadRoute(id)
    emit("opened")
  }
  catch {
    if (sequence === current)
      openError.value = true
  }
}

watch(responding, (active) => {
  if (!active)
    void load(false)
})
onMounted(() => load(false))
onBeforeUnmount(() => sequence++)
</script>

<template>
  <section data-testid="account-chat-history" class="min-h-0 flex flex-col gap-1 overflow-auto px-2">
    <n-button v-for="item in displayItems" :key="item.id" :data-chat-id="item.id" :disabled="responding" :class="{ '!h-auto py-1': item.kind === 'meeting' }" quaternary class="!justify-start" :title="item.title" @click="select(item)">
      <span class="min-w-0 text-left">
        <span class="block truncate">{{ item.title || $t('chat.newChatButton') }}</span>
        <small v-if="item.kind === 'meeting'" class="block truncate color-text-secondary">{{ $t('page.meetings.title') }} · {{ item.project_name }}</small>
      </span>
    </n-button>
    <p v-if="openError" role="alert">
      {{ $t("chat.historyUnavailable") }}
    </p>
    <n-spin v-if="busy" size="small" />
    <n-button v-else-if="failed" size="small" @click="load(items.length > 0)">
      {{ $t("common.retry") }}
    </n-button>
    <n-button v-else-if="more" size="small" @click="load(true)">
      {{ $t("page.home.loadMore") }}
    </n-button>
    <p v-else-if="!items.length" class="aira-text-muted p-2">
      {{ $t("chat.noAccountHistory") }}
    </p>
  </section>
</template>
