<template>
  <span class="field-review" role="group" :aria-label="change.field">
    <template v-if="pending">
      <small class="recorder-suggestion">{{ $t("page.recorderAira.replacement", { before: String(recorderValue(change.before)), after: String(recorderValue(change.after)) }) }}</small>
      <n-button size="tiny" secondary type="primary" :disabled="busy" @click="emit('accept', change.field)">
        {{ $t("page.recorderAira.replaceField") }}
      </n-button>
      <n-button size="tiny" quaternary :disabled="busy" @click="emit('dismiss', change.field)">
        {{ $t("page.recorderAira.keepField") }}
      </n-button>
    </template>
    <n-button v-else class="recorder-field-undo" size="tiny" quaternary :disabled="busy" @click="emit('undo', change.field)">
      {{ $t("page.recorderAira.undoField") }}
    </n-button>
  </span>
</template>

<script setup lang="ts">
import type { RecorderFieldEdit } from "../composables/useRecorderConversation"
import { recorderValue } from "../composables/useRecorderConversation"

defineProps<{ change: RecorderFieldEdit, pending: boolean, busy: boolean }>()
const emit = defineEmits<{ accept: [field: string], dismiss: [field: string], undo: [field: string] }>()
</script>

<style scoped>
.field-review {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: center;
  align-self: stretch;
  gap: 0.25rem;
  max-width: 100%;
}
.aimd-field-wrapper > .field-review {
  padding: 0.25rem 0.375rem;
  border-top: 1px solid var(--aimd-border-color);
}
.recorder-suggestion {
  overflow-wrap: anywhere;
  font-size: 0.8125rem;
  line-height: 1.4;
}
</style>
