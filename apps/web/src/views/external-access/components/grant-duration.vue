<script setup lang="ts">
import { $t } from "@airalogy/shared/locales"

const props = defineProps<{ max: number }>()
const days = defineModel<number | null>({ required: true })
const custom = ref(false)
const options = computed(() => [...new Set([1, 7, 30, 90, props.max])].filter(n => n <= props.max).sort((a, b) => a - b).map(n => ({ label: $t("accountSettings.dayCount", { count: n }), value: n })).concat({ label: $t("accountSettings.customDays"), value: 0 }))
function choose(value: number) {
  custom.value = value === 0
  if (!custom.value)
    days.value = value
}
</script>

<template>
  <div class="flex flex-wrap gap-2">
    <n-select class="w-40" :value="custom ? 0 : days" :options="options" :aria-label="$t('externalAccess.days')" @update:value="choose" />
    <n-input-number v-if="custom" v-model:value="days" class="w-40" :min="1" :max="max" :precision="0" :aria-label="$t('accountSettings.customDays')" />
  </div>
</template>
