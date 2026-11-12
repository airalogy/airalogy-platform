<template>
  <div class="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-gray-500">
    <n-button text size="small" @click="show = true">
      {{ $t('airaMemory.open') }}
    </n-button>
    <n-tooltip trigger="hover">
      <template #trigger>
        <n-checkbox :checked="disabled" :disabled="busy || !!locked" :aria-disabled="busy || !!locked" size="small" @update:checked="$emit('update:disabled', $event)">
          {{ $t('airaMemory.temporary') }}
        </n-checkbox>
      </template>
      {{ $t('airaMemory.temporaryHint') }}
    </n-tooltip>
    <span v-if="status" role="status" class="w-full">
      {{ status.status === 'used' ? $t('airaMemory.used') + labels : status.status === 'unavailable' ? $t('airaMemory.unavailable') : $t('airaMemory.notUsed') }}
    </span>
    <n-modal v-model:show="show" preset="card" :title="$t('airaMemory.open')" class="w-[min(640px,calc(100vw-32px))]" :style="{ maxHeight: '85vh', overflowY: 'auto' }">
      <memory-panel v-if="show" :endpoint="endpoint" :token="token" />
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import type { PreferenceKey } from "../../aira-memory/api"
import { $t } from "@airalogy/shared/locales"
import { computed, ref } from "vue"
import MemoryPanel from "../../aira-memory/panel.vue"

const props = defineProps<{
  endpoint: string
  token: string
  disabled: boolean
  locked?: boolean
  busy?: boolean
  status?: { status: string, keys: string[], revision: number }
}>()
defineEmits<{ "update:disabled": [value: boolean] }>()
const show = ref(false)
const labels = computed(() => props.status?.keys.map(key => $t(`airaMemory.${key as PreferenceKey}`)).join(" · "))
</script>
