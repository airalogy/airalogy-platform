<script setup lang="ts">
defineProps<{ value: string, options: { value: string, label: string }[], label: string, disabled?: boolean }>()
const emit = defineEmits<{ "update:value": [string] }>()
</script>

<template>
  <select :value="value" :aria-label="label" :disabled="disabled" class="document-select" @change="emit('update:value', ($event.target as HTMLSelectElement).value)">
    <option v-for="option in options" :key="option.value" :value="option.value">
      {{ option.label }}
    </option>
  </select>
</template>

<style scoped>
.document-select { display: block; width: 100%; min-width: 0; min-height: 40px; padding: 8px 32px 8px 12px; border: 1px solid #d1d5db; border-radius: 6px; background-color: #fff; color: #333; font: inherit; text-overflow: ellipsis; }
.document-select:focus-visible { outline: 2px solid #1677ff; outline-offset: 2px; }
.document-select:disabled { opacity: 0.6; cursor: not-allowed; }
</style>
