<script setup lang="ts">
import type {
  ResearchLogScopeParams,
  ResearchLogSource,
  ResearchLogTimelineItem,
} from "@/service/api/research-log"
import { fetchResearchActivitySummary, fetchResearchLogTimeline } from "@/service/api/research-log"
import { documentTimeZone, localDocumentDate } from "@/utils/documentBrowse"
import ResearchLogEntryModal from "@/views/record-diary/modules/research-log-entry-modal.vue"
import ResearchLogList from "@/views/record-diary/modules/research-log-list.vue"
import { useI18n } from "vue-i18n"

const props = withDefaults(defineProps<{ scope: ResearchLogScopeParams, compact?: boolean }>(), {
  compact: false,
})
const { t, locale } = useI18n()
const route = useRoute()
const year = ref(new Date().getFullYear())
const source = ref<ResearchLogSource>("all")
const selected = ref("")
const days = ref<{ date: string, count: number }[]>([])
const items = ref<ResearchLogTimelineItem[]>([])
const total = ref(0)
const page = ref(1)
const busy = ref(false)
const error = ref("")
const canWrite = ref(false)
const logModal = ref<InstanceType<typeof ResearchLogEntryModal>>()
const pageSize = computed(() => (props.compact ? 3 : 20))
let requestId = 0
const bounds = computed(() => {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  if (props.compact) {
    const start = new Date(today)
    start.setDate(start.getDate() - 89)
    return { start, end: today }
  }
  return {
    start: new Date(year.value || today.getFullYear(), 0, 1),
    end:
      year.value === today.getFullYear()
        ? today
        : new Date(year.value || today.getFullYear(), 11, 31),
  }
})
const cells = computed(() => {
  const counts = new Map(days.value.map(d => [d.date, d.count]))
  const start = new Date(bounds.value.start)
  start.setDate(start.getDate() - ((start.getDay() + 6) % 7))
  const result: { date: string, count: number, disabled: boolean }[] = []
  for (const day = new Date(start); day <= bounds.value.end; day.setDate(day.getDate() + 1)) {
    const key = localDocumentDate(day)
    result.push({ date: key, count: counts.get(key) || 0, disabled: day < bounds.value.start })
  }
  return result
})
const options = computed(() =>
  ["all", "meeting", "document", "record", "research", "protocol", "knowledge"].map(value => ({
    value,
    label: t(`page.researchActivity.types.${value}`),
  })),
)
const monthLabels = computed(() => {
  let previous = ""
  return cells.value.flatMap((cell, index) => {
    if (cell.disabled)
      return []
    const month = cell.date.slice(0, 7)
    if (month === previous)
      return []
    previous = month
    return [{ column: Math.floor(index / 7) + 1, label: new Intl.DateTimeFormat(locale.value, { month: "short" }).format(new Date(`${cell.date}T12:00:00`)) }]
  })
})
const weekdays = computed(() => [0, 2, 4].map(day => ({
  row: day + 1,
  label: new Intl.DateTimeFormat(locale.value, { weekday: "short" }).format(new Date(2026, 0, 5 + day)),
})))
const rangeLabel = computed(
  () => `${localDocumentDate(bounds.value.start)} — ${localDocumentDate(bounds.value.end)}`,
)
function color(count: number) {
  return count === 0
    ? "#edf0f3"
    : count < 3
      ? "#9be9a8"
      : count < 6
        ? "#40c463"
        : count < 10
          ? "#30a14e"
          : "#216e39"
}
async function load() {
  const id = ++requestId
  busy.value = true
  error.value = ""
  items.value = []
  total.value = 0
  const params = { ...props.scope, group_meeting_actions: props.scope.scope_type === "project", source: source.value, time_zone: documentTimeZone() }
  try {
    const [summary, timeline] = await Promise.all([
      fetchResearchActivitySummary({
        ...params,
        date_from: localDocumentDate(bounds.value.start),
        date_to: localDocumentDate(bounds.value.end),
      }),
      fetchResearchLogTimeline({
        ...params,
        date_from: selected.value || localDocumentDate(bounds.value.start),
        date_to: selected.value || localDocumentDate(bounds.value.end),
        page: page.value,
        page_size: pageSize.value,
      }),
    ])
    if (id !== requestId)
      return
    days.value = summary.summary
    items.value = timeline.items
    total.value = timeline.total_count
    canWrite.value = timeline.can_write
  }
  catch (e) {
    if (id === requestId)
      error.value = (e as Error).message || t("page.researchActivity.failed")
  }
  finally {
    if (id === requestId)
      busy.value = false
  }
}
function selectDay(day: string) {
  selected.value = selected.value === day ? "" : day
  page.value = 1
}
function reset() {
  selected.value = ""
  page.value = 1
}
watch(
  [() => JSON.stringify(props.scope), () => route.query.day, () => route.query.source],
  () => {
    const day = route.query.day
    const validDay = !props.compact && typeof day === "string" && /^\d{4}-\d{2}-\d{2}$/.test(day) && !Number.isNaN(Date.parse(day))
    selected.value = validDay ? day : ""
    year.value = validDay ? Number(day.slice(0, 4)) : new Date().getFullYear()
    source.value = (options.value.find(option => option.value === route.query.source)?.value ?? "all") as ResearchLogSource
    page.value = 1
  },
  { immediate: true },
)
watch([() => JSON.stringify(props.scope), selected, source, year, page], load, { immediate: true })
onBeforeUnmount(() => requestId++)
</script>

<template>
  <section
    class="research-activity min-w-0 border rounded-xl bg-white p-4 space-y-4 sm:p-5"
    data-testid="research-activity"
  >
    <header class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h2 class="m-0 text-xl font-semibold">
          {{ t("page.researchActivity.title") }}
        </h2><p v-if="!compact" class="mb-0 mt-1 text-sm text-gray-500">
          {{ t("page.researchActivity.hint") }}
        </p>
      </div>
      <router-link
        v-if="compact && scope.scope_type === 'project'"
        class="text-primary"
        :to="{ name: 'project-records', params: route.params }"
      >
        {{ t("page.researchActivity.viewAll") }} →
      </router-link>
      <div v-if="!compact && (canWrite || $slots.actions)" class="flex flex-wrap items-center gap-2">
        <slot name="actions" :day="selected || undefined" />
        <research-log-entry-modal
          v-if="canWrite"
          ref="logModal"
          :scope="scope"
          :scope-label="t('page.researchActivity.title')"
          @saved="load"
        />
      </div>
    </header>
    <div class="activity-filters flex flex-wrap items-center gap-2 text-sm">
      <n-select
        v-model:value="source"
        :options="options"
        size="small"
        class="!w-32"
        data-testid="activity-type"
        @update:value="reset"
      />
      <label v-if="!compact" class="flex items-center gap-2">{{ t("page.researchActivity.year")
      }}<n-input-number
        v-model:value="year"
        :min="1900"
        :max="new Date().getFullYear()"
        :show-button="false"
        size="small"
        class="!w-20"
        @update:value="reset"
      /></label>
      <div class="flex items-center gap-1 text-xs text-gray-500">
        <span>{{ rangeLabel }}</span>
        <n-popover trigger="click" placement="bottom">
          <template #trigger>
            <n-button quaternary circle size="tiny" :aria-label="t('page.researchActivity.timeZoneDetails')" data-testid="activity-timezone-info">
              <template #icon>
                <n-icon :size="15">
                  <icon-tabler-info-circle />
                </n-icon>
              </template>
            </n-button>
          </template>
          <span data-testid="activity-timezone-details">{{ t('page.researchActivity.timeZoneHint', { timeZone: documentTimeZone() }) }}</span>
        </n-popover>
      </div>
    </div>
    <n-alert v-if="error" type="error" role="alert">
      {{ error }}
      <n-button size="small" @click="load">
        {{ t("page.researchActivity.retry") }}
      </n-button>
    </n-alert>
    <n-spin :show="busy">
      <div :class="{ 'overview-activity-grid': compact }">
        <div class="activity-calendar-frame">
          <div class="activity-calendar-scroll" :aria-label="t('page.researchActivity.calendar')">
            <div class="activity-months" :style="{ gridTemplateColumns: `repeat(${Math.ceil(cells.length / 7)}, 13px)` }" aria-hidden="true">
              <span v-for="month in monthLabels" :key="month.column" :style="{ gridColumn: month.column }">{{ month.label }}</span>
            </div>
            <div class="flex gap-2">
              <div class="activity-weekdays" aria-hidden="true">
                <span v-for="day in weekdays" :key="day.row" :style="{ gridRow: day.row }">{{ day.label }}</span>
              </div>
              <div class="activity-calendar" data-testid="activity-heatmap">
                <button
                  v-for="cell in cells"
                  :key="cell.date"
                  type="button"
                  class="activity-day"
                  :class="{ selected: selected === cell.date }"
                  :style="{
                    background: color(cell.count),
                    visibility: cell.disabled ? 'hidden' : 'visible',
                  }"
                  :disabled="cell.disabled || busy"
                  :title="`${cell.date} · ${cell.count} ${t('page.researchActivity.events')}`"
                  :aria-label="`${cell.date}: ${cell.count} ${t('page.researchActivity.events')}`"
                  :aria-pressed="selected === cell.date"
                  :data-date="cell.date"
                  :data-count="cell.count"
                  @click="selectDay(cell.date)"
                />
              </div>
            </div>
          </div>
          <div class="mt-2 flex items-center justify-end gap-1 text-xs text-gray-500">
            <span>{{ t("page.researchActivity.less") }}</span><i
              v-for="count in [0, 1, 3, 6, 10]"
              :key="count"
              class="h-3 w-3 rounded-sm"
              :style="{ background: color(count) }"
            /><span>{{ t("page.researchActivity.more") }}</span>
          </div>
        </div>
        <div class="min-w-0">
          <div :class="compact ? 'mb-1' : 'mb-3 mt-5'" class="flex flex-wrap items-center justify-between gap-3">
            <h3 class="m-0 text-base font-medium" data-testid="activity-list-title">
              {{
                selected
                  ? `${selected} · ${t("page.researchActivity.dayEvents")}`
                  : t("page.researchActivity.recent")
              }}
              <span v-if="!busy" class="text-gray-500">({{ total }})</span>
            </h3>
            <n-button v-if="selected" size="small" data-testid="activity-clear-date" @click="reset">
              {{ t("page.researchActivity.clearDate") }}
            </n-button>
          </div>
          <p
            v-if="!busy && !error && !items.length"
            class="py-6 text-center text-gray-500"
            data-testid="activity-empty"
          >
            {{ selected ? t("page.researchActivity.emptyDay") : t("page.researchActivity.empty") }}
          </p>
          <research-log-list v-else-if="!error && !busy" :items="items" :compact="compact" @edit="logModal?.open($event)" />
          <n-pagination
            v-if="!compact && total > pageSize"
            v-model:page="page"
            :item-count="total"
            :page-size="pageSize"
            class="mt-4"
          />
          <router-link
            v-if="compact && selected && total > pageSize" class="text-sm text-primary" data-testid="view-day"
            :to="{ name: 'project-records', params: route.params, query: { day: selected, source } }"
          >
            {{ t('page.researchActivity.viewDay', { count: total }) }} →
          </router-link>
        </div>
      </div>
    </n-spin>
  </section>
</template>

<style scoped>
.overview-activity-grid { display: grid; gap: 14px 24px; align-items: start; }
@media (min-width: 700px) {
  .overview-activity-grid { grid-template-columns: max-content minmax(0, 1fr); }
}
.activity-calendar-scroll {
  overflow-x: auto;
  padding: 5px 3px;
}
.activity-calendar-frame { width: max-content; max-width: 100%; }
.activity-months { display: grid; gap: 4px; margin: 0 0 6px 38px; font-size: 11px; color: #64748b; }
.activity-months span { white-space: nowrap; }
.activity-weekdays { flex: 0 0 30px; white-space: nowrap; display: grid; grid-template-rows: repeat(7, 13px); gap: 4px; width: 30px; font-size: 10px; line-height: 13px; color: #64748b; }
.activity-calendar {
  display: grid;
  grid-template-rows: repeat(7, 13px);
  grid-auto-flow: column;
  grid-auto-columns: 13px;
  gap: 4px;
  width: max-content;
}
.activity-day {
  width: 13px;
  height: 13px;
  padding: 0;
  border: 1px solid #172b4d0d;
  border-radius: 3px;
  cursor: pointer;
}
.activity-day.selected,
.activity-day:focus-visible {
  outline: 2px solid #1677ff;
  outline-offset: 1px;
}
</style>
