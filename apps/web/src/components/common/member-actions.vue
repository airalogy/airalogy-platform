<script setup lang="ts">
import type { DropdownOption } from "naive-ui"
import { useBasicLayout } from "@/composables"

defineProps<{ options: DropdownOption[] }>()
const emit = defineEmits<{ select: [key: string | number] }>()
const { isMobile } = useBasicLayout()
</script>

<template>
  <n-dropdown placement="bottom-end" trigger="click" :options="options" @select="emit('select', $event)">
    <n-button :quaternary="isMobile" :circle="isMobile" aria-haspopup="menu" size="small" :aria-label="$t('common.actions')" :title="$t('common.actions')">
      <template #icon>
        <icon-tabler-dots-vertical v-if="isMobile" />
        <icon-tabler-chevron-down v-else />
      </template>
      <template v-if="!isMobile">
        {{ $t("common.actions") }}
      </template>
    </n-button>
  </n-dropdown>
</template>
