<script setup lang="ts">
import { getChatConversation } from "@/service/api/chat"
import { useChatStore } from "@airalogy/components/chat/store"
import ChatView from "./index.vue"

const store = useChatStore()
const route = useRoute()
const router = useRouter()
const initialChat = route.query.chat
const loading = ref(false)
const unavailable = ref(false)
let mounted = true
// The chat view can restore device-only drafts itself. Server IDs are verified
// before the view and its URL synchronization mount, including on a new device.
if (typeof initialChat === "string" && /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(initialChat)) {
  loading.value = true
  getChatConversation(initialChat).then((data) => {
    if (!mounted)
      return
    if (!data || data.id !== initialChat)
      throw new Error("Unavailable")
    store.restoreAccountConversation(data)
  }).catch(() => {
    unavailable.value = true
  }).finally(() => {
    loading.value = false
  })
}
onBeforeUnmount(() => {
  mounted = false
})
async function showHistory() {
  await router.replace({ name: "global-chat" })
  unavailable.value = false
}
</script>

<template>
  <n-spin v-if="loading" class="m-auto" />
  <div v-else-if="unavailable" class="m-auto p-4">
    <p role="alert">{{ $t('chat.historyUnavailable') }}</p>
    <n-button @click="showHistory">{{ $t('common.allChats') }}</n-button>
  </div>
  <chat-view v-else />
</template>
