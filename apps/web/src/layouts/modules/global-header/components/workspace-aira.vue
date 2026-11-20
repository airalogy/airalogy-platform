<script setup lang="ts">
import AiraSidePanel from "@/components/common/aira-side-panel.vue"
import { useProvideChatConfigStore } from "@/composables"
import { useWorkspaceAira } from "@/composables/useWorkspaceAira"
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

const { visible, restoreFocus } = useWorkspaceAira()!
function close() {
  visible.value = false
  nextTick(restoreFocus)
}
</script>

<template>
  <aira-side-panel :open="visible" label="Aira" @close="close">
    <section class="h-full min-h-0 flex flex-col" data-testid="home-aira-panel">
      <header class="flex shrink-0 items-center justify-between gap-2 border-b border-gray-200 px-4 py-3">
        <h2 id="home-aira-title" class="aira-type-card-title m-0 flex items-center gap-2">
          <n-icon :size="24" aria-hidden="true">
            <icon-shared-airalogy-chat />
          </n-icon>
          Aira
        </h2>
        <router-link :to="fullPage" target="_blank" rel="noopener" class="ml-auto text-sm text-primary" data-testid="open-aira-history">
          {{ $t("common.allChats") }} ↗
        </router-link>
        <div id="home-aira-memory-actions" class="shrink-0" />
        <n-button size="small" quaternary circle :aria-label="$t('common.close')" @click="close">
          <template #icon>
            <n-icon><icon-tabler-x /></n-icon>
          </template>
        </n-button>
      </header>
      <div class="min-h-0 min-w-0 flex-1 px-3">
        <chat-view embedded />
      </div>
    </section>
  </aira-side-panel>
</template>
