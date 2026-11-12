<template>
  <n-card id="aira-memory">
    <memory-panel :endpoint="endpoint" :token="token || ''" />
  </n-card>
</template>

<script setup lang="ts">
import { useOrProvideChatConfigStore } from "@/composables/useChatConfig"
import MemoryPanel from "@airalogy/components/aira-memory/panel.vue"

const { baseUrl, token } = useOrProvideChatConfigStore()
const endpoint = computed(() => baseUrl.value.replace(/\/chats\/?$/, "/aira-memory"))
</script>
