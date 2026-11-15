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
const { t } = useI18n()
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
const pageSize = computed(() => (props.compact ? 10 : 20))
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
  const params = { ...props.scope, source: source.value, time_zone: documentTimeZone() }
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
  [() => JSON.stringify(props.scope), source, year],
  () => {
    reset()
    void load()
  },
  { immediate: true },
)
watch([selected, page], load)
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
        </h2><p class="mb-0 mt-1 text-sm text-gray-500">
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
      <research-log-entry-modal
        v-if="!compact && canWrite"
        ref="logModal"
        :scope="scope"
        :scope-label="t('page.researchActivity.title')"
        @saved="load"
      />
    </header>
    <div class="flex flex-wrap items-center gap-3">
      <n-select
        v-model:value="source"
        :options="options"
        class="!w-44"
        data-testid="activity-type"
      />
      <label v-if="!compact" class="flex items-center gap-2">{{ t("page.researchActivity.year")
      }}<n-input-number
        v-model:value="year"
        :min="1900"
        :max="new Date().getFullYear()"
        :show-button="false"
        class="!w-28"
      /></label>
      <span class="text-xs text-gray-500">{{ rangeLabel }} · {{ documentTimeZone() }}</span>
    </div>
    <n-alert v-if="error" type="error" role="alert">
      {{ error }}
      <n-button size="small" @click="load">
        {{ t("page.researchActivity.retry") }}
      </n-button>
    </n-alert>
    <n-spin :show="busy">
      <div class="activity-calendar-scroll" :aria-label="t('page.researchActivity.calendar')">
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
      <div class="mt-2 flex items-center justify-end gap-1 text-xs text-gray-500">
        <span>{{ t("page.researchActivity.less") }}</span><i
          v-for="count in [0, 1, 3, 6, 10]"
          :key="count"
          class="h-3 w-3 rounded-sm"
          :style="{ background: color(count) }"
        /><span>{{ t("page.researchActivity.more") }}</span>
      </div>
      <div class="mb-3 mt-5 flex flex-wrap items-center justify-between gap-3">
        <h3 class="m-0 text-base font-medium" data-testid="activity-list-title">
          {{
            selected
              ? `${selected} · ${t("page.researchActivity.dayEvents")}`
              : t("page.researchActivity.recent")
          }}
          <span class="text-gray-500">({{ total }})</span>
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
      <research-log-list v-else-if="!error" :items="items" @edit="logModal?.open($event)" />
      <n-pagination
        v-if="total > pageSize"
        v-model:page="page"
        :item-count="total"
        :page-size="pageSize"
        class="mt-4"
      />
    </n-spin>
  </section>
</template>

<style scoped>
.activity-calendar-scroll {
  overflow-x: auto;
  padding: 5px 3px;
}
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
