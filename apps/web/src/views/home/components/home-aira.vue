<script setup lang="ts">
import { useProvideChatConfigStore } from "@/composables"
import { useProvideChatProvider } from "@airalogy/components/chat/providers/useChatProvider"
import { useChatStore } from "@airalogy/components/chat/store"

const chatStore = useChatStore()
const fullPage = computed(() => {
  const id = chatStore.findSessionByUUID()?.serverId
  return { name: "global-chat" as const, query: id ? { chat: id } : {} }
})

const ChatView = defineAsyncComponent(() => import("@/views/chat/index.vue"))
const chatConfig = useProvideChatConfigStore()
chatConfig.mode.value = "embedded"
useProvideChatProvider(chatConfig)

const opened = ref(false)
const visible = ref(false)
const trigger = ref<{ $el: HTMLButtonElement }>()

function open() {
  opened.value = true
  visible.value = true
}
function restoreFocus() {
  if (!visible.value)
    trigger.value?.$el.focus({ preventScroll: true })
}
</script>

<template>
  <n-button
    ref="trigger" secondary type="primary" data-testid="home-aira" aria-haspopup="dialog"
    :aria-expanded="visible" @click="open"
  >
    {{ $t('page.home.workspace.askAira') }}
  </n-button>
  <n-drawer
    v-if="opened" v-model:show="visible" placement="right" width="min(100%, 460px)"
    display-directive="show" aria-labelledby="home-aira-title" @after-leave="restoreFocus"
  >
    <section class="h-full min-h-0 flex flex-col" data-testid="home-aira-panel">
      <header class="flex shrink-0 items-center justify-between gap-2 border-b border-gray-200 px-4 py-3">
        <h2 id="home-aira-title" class="aira-type-card-title m-0 flex items-center gap-2">
          <n-icon :size="24" aria-hidden="true"><icon-shared-airalogy-chat /></n-icon>
          Aira
        </h2>
        <router-link :to="fullPage" target="_blank" rel="noopener" class="ml-auto text-sm text-primary" data-testid="open-aira-history">
          {{ $t("common.allChats") }} ↗
        </router-link>
        <n-button size="small" quaternary circle :aria-label="$t('common.close')" @click="visible = false">
          <template #icon><n-icon><icon-tabler-x /></n-icon></template>
        </n-button>
      </header>
      <div class="min-h-0 min-w-0 flex-1 px-3">
        <chat-view embedded />
      </div>
    </section>
  </n-drawer>
</template>
