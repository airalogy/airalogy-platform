<script setup lang="ts">
import type { ResearchLogScopeParams } from "@/service/api/research-log"
import { useOrganizationTranslation } from "@/composables/useOrganizationTranslation"
import { researchDocumentCalendar } from "@/service/api/research-documents"
import { documentTimeZone, localDocumentDate } from "@/utils/documentBrowse"
import { useI18n } from "vue-i18n"

const props = defineProps<{ scope: ResearchLogScopeParams, q: string, kind: string, selected?: string }>()
const emit = defineEmits<{ select: [string] }>()
const { locale } = useI18n()
const { t } = useOrganizationTranslation()
const month = ref((props.selected || localDocumentDate()).slice(0, 7))
const counts = ref<Record<string, number>>({})
const loading = ref(false)
const error = ref(false)
let sequence = 0
const dates = computed(() => {
  if (!/^\d{4}-(?:0[1-9]|1[0-2])$/.test(month.value))
    return []
  const [year, m] = month.value.split("-").map(Number)
  const first = new Date(year, m - 1, 1, 12)
  const offset = (first.getDay() + 6) % 7
  const last = new Date(year, m, 0, 12).getDate()
  return Array.from({ length: Math.ceil((offset + last) / 7) * 7 }, (_, i) => {
    const day = i - offset + 1
    return day > 0 && day <= last ? `${month.value}-${String(day).padStart(2, "0")}` : ""
  })
})
const weekdays = computed(() => Array.from({ length: 7 }, (_, i) => new Intl.DateTimeFormat(locale.value, { weekday: "short" }).format(new Date(2024, 0, 1 + i))))
function changeMonth(delta: number) {
  if (!dates.value.length)
    month.value = localDocumentDate().slice(0, 7)
  const [year, m] = month.value.split("-").map(Number)
  month.value = localDocumentDate(new Date(year, m - 1 + delta, 1, 12)).slice(0, 7)
}
function moveFocus(event: KeyboardEvent, offset: number) {
  const buttons = Array.from((event.currentTarget as HTMLElement).querySelectorAll<HTMLButtonElement>("button[data-date]"))
  const index = buttons.indexOf(event.target as HTMLButtonElement)
  if (buttons[index + offset]) {
    event.preventDefault()
    buttons[index + offset].focus()
  }
}
async function load() {
  const ticket = ++sequence
  counts.value = {}
  error.value = false
  loading.value = false
  if (!dates.value.length)
    return
  loading.value = true
  try {
    const result = await researchDocumentCalendar(props.scope, { month: `${month.value}-01`, q: props.q, kind: props.kind, time_zone: documentTimeZone() })
    if (ticket === sequence)
      counts.value = Object.fromEntries(result.days.map(day => [day.date, day.count]))
  }
  catch {
    if (ticket === sequence)
      error.value = true
  }
  finally {
    if (ticket === sequence)
      loading.value = false
  }
}
watch(() => [month.value, props.q, props.kind, JSON.stringify(props.scope)], load, { immediate: true })
onBeforeUnmount(() => sequence++)
</script>

<template>
  <section class="max-w-sm border rounded-lg p-3" data-testid="document-calendar" :aria-label="t('page.documentBrowse.calendar')">
    <div class="mb-3 flex items-center gap-2">
      <n-button size="small" :aria-label="t('page.documentBrowse.previousMonth')" @click="changeMonth(-1)">
        ‹
      </n-button>
      <input v-model="month" type="month" class="min-w-0 flex-1 border rounded p-2" :aria-label="t('page.documentBrowse.month')" data-testid="document-calendar-month">
      <n-button size="small" :aria-label="t('page.documentBrowse.nextMonth')" @click="changeMonth(1)">
        ›
      </n-button>
    </div>
    <p class="aira-type-meta">
      {{ t('page.documentBrowse.calendarHint') }}
    </p>
    <n-alert v-if="error" type="error">
      {{ t('page.researchDocuments.failed') }} <n-button @click="load">
        {{ t('common.retry') }}
      </n-button>
    </n-alert>
    <n-spin :show="loading">
      <div class="grid grid-cols-7 gap-1 text-center" @keydown.left="moveFocus($event, -1)" @keydown.right="moveFocus($event, 1)" @keydown.up="moveFocus($event, -7)" @keydown.down="moveFocus($event, 7)">
        <span v-for="day in weekdays" :key="day" class="text-xs text-gray-500">{{ day }}</span>
        <template v-for="(day, index) in dates" :key="index">
          <button v-if="day" type="button" :data-date="day" class="min-h-11 border border-transparent rounded p-1 hover:border-primary focus-visible:outline-primary" :class="selected === day ? 'bg-primary text-white' : 'bg-gray-50'" :aria-pressed="selected === day" :aria-label="t('page.documentBrowse.dayCount', { date: day, count: counts[day] || 0 })" @click="emit('select', day)">
            {{ Number(day.slice(-2)) }}<span v-if="counts[day]" class="block text-xs font-semibold">{{ counts[day] }}</span>
          </button>
          <span v-else />
        </template>
      </div>
    </n-spin>
  </section>
</template>
