<template>
  <n-loading-bar-provider>
    <n-dialog-provider>
      <n-notification-provider>
        <n-message-provider>
          <context-holder />
          <record-export-notifier />
          <slot />
        </n-message-provider>
      </n-notification-provider>
    </n-dialog-provider>
  </n-loading-bar-provider>
</template>

<script setup lang="ts">
import { useProvideChatConfigStore } from "@/composables"
import { verifyOwnedChatIds } from "@/service/api/chat"
import { useAuthStore } from "@/store/modules/auth"
import { useProvideChatProvider } from "@airalogy/components/chat/providers/useChatProvider"
import { useChatStore } from "@airalogy/components/chat/store"
import { useDialog, useLoadingBar, useMessage, useNotification } from "naive-ui"
import { createTextVNode, defineComponent } from "vue"
import RecordExportNotifier from "./record-export-notifier.vue"

defineOptions({
  name: "AppProvider",
})

function register() {
  window.$dialog = useDialog()
  window.$loadingBar = useLoadingBar()
  window.$message = useMessage()
  window.$notification = useNotification()
}

const auth = useAuthStore()
watch(() => auth.isLogin && auth.userInfo.id, (id) => {
  if (id) {
    // If offline, leave the original cache intact and retry at the next login.
    void useChatStore().importOwnedLegacyHistory(verifyOwnedChatIds).catch(() => {})
  }
}, { immediate: true })
const configs = useProvideChatConfigStore()
useProvideChatProvider(configs)
const ContextHolder = defineComponent({
  name: "ContextHolder",
  setup() {
    register()

    return () => createTextVNode()
  },
})
</script>

<style scoped>
</style>
