<script setup lang="ts">
import type {
  DocumentPreview,
  DocumentSummary,
} from "@/service/api/research-documents"
import type { ResearchLogScopeParams } from "@/service/api/research-log"
import {
  importResearchDocument,
  listResearchDocuments,
} from "@/service/api/research-documents"
import { documentTimeZone, localDocumentDate, queryText } from "@/utils/documentBrowse"
import { createResearchDocumentId } from "@/utils/research-document-id"
import FileTextIcon from "~icons/tabler/file-text"
import FilterIcon from "~icons/tabler/filter"
import PlusIcon from "~icons/tabler/plus"
import { useI18n } from "vue-i18n"
import DocumentAudience from "./document-audience.vue"
import DocumentCalendar from "./document-calendar.vue"
import DocumentReader from "./document-reader.vue"
import DocumentSelect from "./document-select.vue"
import NewDocumentDialog from "./new-document-dialog.vue"
import SnapshotPreview from "./snapshot-preview.vue"

const props = defineProps<{ scope: ResearchLogScopeParams, compact?: boolean, scopeName?: string }>()
const { t } = useI18n()
const router = useRouter()
const route = useRoute()
const items = ref<DocumentSummary[]>([])
const total = ref(0)
const page = computed(() => Math.min(100000, Math.max(1, Number.parseInt(queryText(route.query.page), 10) || 1)))
const q = ref("")
const kind = ref("")
const from = ref("")
const to = ref("")
const order = ref<"updated" | "recorded">("updated")
const calendarOpen = ref(false)
const filtersOpen = ref(false)
const archiveInput = ref<HTMLInputElement>()
const hasFilters = computed(() => Boolean(kind.value || from.value || to.value))
const loading = ref(false)
const moving = ref(false)
const reading = computed(() => props.compact ? "" : queryText(route.query.read))
const selectedIndex = computed(() => items.value.findIndex(item => item.id === reading.value))
const previous = computed(() => selectedIndex.value > 0 || page.value > 1)
const next = computed(() => selectedIndex.value >= 0 && (selectedIndex.value < items.value.length - 1 || page.value * 20 < total.value))
const error = ref("")
const busy = ref(false)
const showCreate = ref(false)
const listElement = ref<HTMLElement>()

const canWrite = ref(false)
const hasQuery = computed(() => ["q", "kind", "from", "to"].some(key => queryText(route.query[key])) || page.value > 1)
const showBrowseTools = computed(() => !props.compact && (total.value > 0 || hasQuery.value))
const moreOptions = computed(() => [
  { key: "templates", label: t("page.documentTemplates.library") },
  ...(canWrite.value ? [{ key: "import", label: t("page.documentUx.importArchive"), disabled: busy.value }] : []),
])
function moreAction(key: string) {
  if (key === "import")
    archiveInput.value?.click()
  else if (key === "templates")
    void router.push({ name: "research-documents", query: { tab: "templates", ...(props.scope.project_id ? { project_id: props.scope.project_id } : props.scope.lab_id ? { lab_id: props.scope.lab_id } : {}) } })
}
function clearSearch() {
  q.value = ""
  kind.value = ""
  from.value = ""
  to.value = ""
  void search()
}
const archive = ref<{ file: File, id: string, preview?: DocumentPreview }>()
async function selectArchive(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file)
    return
  input.value = ""
  archive.value = { file, id: createResearchDocumentId() }
  await importArchive()
}
async function importArchive(confirm = false) {
  if (!archive.value)
    return
  busy.value = true
  try {
    const result = await importResearchDocument(
      props.scope,
      archive.value.file,
      archive.value.id,
      confirm ? archive.value.preview?.preview_digest : undefined,
    )
    if ("requires_confirmation" in result) {
      archive.value.preview = result
    }
    else if ("id" in result) {
      archive.value = undefined
      await router.push({ name: "research-document-detail", params: { documentId: result.id } })
    }
  }
  catch {
    error.value = t("page.researchDocuments.failed")
  }
  finally {
    busy.value = false
  }
}
let sequence = 0
const options = computed(() => [
  { value: "", label: t("page.researchDocuments.allKinds") },
  ...["document", "experiment", "progress", "meeting", "reflection", "blocker", "milestone"].map(
    value => ({ value, label: t(`page.researchDocuments.${value}`) }),
  ),
])
function params(targetPage = page.value) {
  return { q: queryText(route.query.q), kind: queryText(route.query.kind), page: targetPage, page_size: props.compact ? 5 : 20, order: queryText(route.query.order) === "recorded" ? "recorded" as const : "updated" as const, date_from: queryText(route.query.from) || undefined, date_to: queryText(route.query.to) || undefined, time_zone: documentTimeZone() }
}
function browseTo(id: string, targetPage = page.value) {
  return { name: route.name === "project-documents" ? "project-documents" as const : "research-documents" as const, params: route.params, query: { ...route.query, page: String(targetPage), read: id || undefined } }
}
async function search() {
  if (from.value && to.value && from.value > to.value) {
    error.value = t("page.documentBrowse.invalidRange")
    return
  }
  await router.replace({ name: route.name === "project-documents" ? "project-documents" as const : "research-documents" as const, params: route.params, query: { ...route.query, q: q.value || undefined, kind: kind.value || undefined, order: order.value, from: from.value || undefined, to: to.value || undefined, page: undefined, read: undefined } })
}
function chooseDay(day: string) {
  from.value = day
  to.value = day
  order.value = "recorded"
  void search()
}
async function move(delta: number) {
  if (moving.value)
    return
  const item = items.value[selectedIndex.value + delta]
  if (item) {
    await router.replace(browseTo(item.id))
    return
  }
  const targetPage = page.value + delta
  if (targetPage < 1 || targetPage > Math.ceil(total.value / 20))
    return
  const context = route.fullPath
  moving.value = true
  try {
    const result = await listResearchDocuments(props.scope, params(targetPage))
    if (route.fullPath === context && result.items.length)
      await router.replace(browseTo(delta > 0 ? result.items[0].id : result.items[result.items.length - 1].id, targetPage))
  }
  catch { error.value = t("page.researchDocuments.failed") }
  finally { moving.value = false }
}
async function load() {
  const ticket = ++sequence
  error.value = ""
  loading.value = true
  items.value = []
  canWrite.value = false
  try {
    const result = await listResearchDocuments(props.scope, params())
    if (ticket !== sequence)
      return
    items.value = result.items
    total.value = result.total_count
    canWrite.value = result.can_write
  }
  catch {
    if (ticket === sequence)
      error.value = t("page.researchDocuments.failed")
  }
  finally {
    if (ticket === sequence)
      loading.value = false
  }
}
watch(
  () => JSON.stringify([props.scope, ...["q", "kind", "page", "order", "from", "to"].map(key => route.query[key])]),
  () => {
    q.value = queryText(route.query.q)
    kind.value = queryText(route.query.kind)
    from.value = queryText(route.query.from)
    to.value = queryText(route.query.to)
    order.value = queryText(route.query.order) === "recorded" ? "recorded" : "updated"
    void load()
  },
  { immediate: true },
)
onBeforeUnmount(() => sequence++)
watch([reading, items], async () => {
  await nextTick()
  listElement.value?.querySelector<HTMLElement>("[aria-current=\"true\"]")?.scrollIntoView({ block: "nearest" })
})
</script>

<template>
  <section class="min-w-0 space-y-4" data-testid="research-documents-list">
    <header class="space-y-2">
      <div class="document-list-heading" data-testid="document-list-toolbar">
        <h2 class="aira-type-section-title m-0">
          {{ compact ? t("page.researchDocuments.recent") : t(hasQuery ? "page.documentUx.matchingCount" : "page.documentUx.documentCount", { count: total }) }}
        </h2>
        <div class="document-list-actions">
          <n-button
            v-if="canWrite"
            type="primary"
            :loading="busy"
            data-testid="new-research-document"
            @click="showCreate = true"
          >
            <template #icon>
              <n-icon :component="PlusIcon" />
            </template>
            {{ t("page.researchDocuments.new") }}
          </n-button>
          <n-dropdown v-if="!compact" trigger="click" :options="moreOptions" @select="moreAction">
            <n-button quaternary :aria-label="t('page.documentUx.moreActions')" data-testid="document-list-more">
              {{ t('common.more') }}
            </n-button>
          </n-dropdown>
        </div>
      </div>
      <document-audience compact :scope="scope" :name="scopeName" />
    </header>
    <div v-if="showBrowseTools" class="document-list-tools" data-testid="document-list-tools">
      <form class="document-list-search" role="search" @submit.prevent="search">
        <n-input v-model:value="q" clearable :theme-overrides="{ heightMedium: '40px', fontSizeMedium: '14px' }" :placeholder="t('page.documentUx.searchDocuments')" :input-props="{ 'aria-label': t('common.search') }" @clear="q = ''; search()" />
        <n-button attr-type="submit">
          {{ t('common.search') }}
        </n-button>
      </form>
      <document-select v-model:value="order" class="document-list-order" :options="[{ value: 'updated', label: t('page.documentBrowse.recentlyUpdated') }, { value: 'recorded', label: t('page.documentBrowse.byDate') }]" :label="t('page.documentBrowse.sort')" data-testid="document-order" @update:value="search" />
      <n-button :type="hasFilters ? 'primary' : 'default'" :ghost="hasFilters" :aria-expanded="filtersOpen" aria-controls="document-filters" data-testid="document-filters-toggle" @click="filtersOpen = !filtersOpen">
        <template #icon>
          <n-icon :component="FilterIcon" />
        </template>
        {{ t(hasFilters ? 'page.documentUx.filtersActive' : 'page.documentUx.filters') }}
      </n-button>
    </div>
    <template v-if="!compact">
      <div v-if="hasFilters" class="flex flex-wrap items-center gap-2">
        <span class="aira-type-meta">{{ [kind ? t(`page.researchDocuments.${kind}`) : '', from, to && to !== from ? `– ${to}` : ''].filter(Boolean).join(' · ') }}</span>
        <n-button text @click="kind = ''; from = ''; to = ''; search()">
          {{ t('page.documentUx.clearFilters') }}
        </n-button>
      </div>
      <section v-if="showBrowseTools && filtersOpen" id="document-filters" class="border rounded-lg p-3 space-y-3">
        <document-select v-model:value="kind" class="max-w-48" :options="options" :label="t('page.researchDocuments.allKinds')" @update:value="search" />
        <div class="flex flex-wrap items-end gap-3" data-testid="document-date-filter">
          <label class="text-sm">{{ t('page.documentBrowse.from') }}<input v-model="from" type="date" class="block max-w-full min-h-10 border rounded px-2" data-testid="document-date-from" @change="search"></label>
          <label class="text-sm">{{ t('page.documentBrowse.to') }}<input v-model="to" type="date" class="block max-w-full min-h-10 border rounded px-2" data-testid="document-date-to" @change="search"></label>
          <n-button v-if="from || to" @click="from = ''; to = ''; search()">
            {{ t('page.documentBrowse.clearDates') }}
          </n-button>
        </div>
        <details @toggle="calendarOpen = ($event.target as HTMLDetailsElement).open">
          <summary class="cursor-pointer text-primary">
            {{ t('page.documentBrowse.calendar') }}
          </summary>
          <document-calendar v-if="calendarOpen" :scope="scope" :q="queryText(route.query.q)" :kind="queryText(route.query.kind)" :selected="from === to ? from : undefined" class="mt-3" @select="chooseDay" />
        </details>
        <p class="aira-type-meta">
          {{ t('page.documentBrowse.dateHint') }}
        </p>
      </section>
    </template>
    <n-alert v-if="error" type="error" role="alert">
      {{ error }}
      <n-button text @click="load">
        {{ t("page.researchDocuments.retry") }}
      </n-button>
    </n-alert>
    <n-spin :show="loading">
      <div v-if="!loading && !error && !items.length" class="document-list-empty" data-testid="document-list-empty">
        <n-icon :component="FileTextIcon" :size="32" class="document-list-empty-icon" aria-hidden="true" />
        <div class="min-w-0">
          <h3 class="aira-type-card-title m-0">
            {{ t(hasQuery ? 'page.documentUx.noMatches' : 'page.documentUx.emptyTitle') }}
          </h3>
          <p class="aira-type-meta mb-0 mt-2">
            {{ t(hasQuery ? 'page.documentUx.noMatchesHint' : canWrite ? 'page.documentUx.emptyHint' : 'page.documentUx.emptyReadOnlyHint') }}
          </p>
          <n-button v-if="hasQuery" class="mt-3" @click="clearSearch">
            {{ t('page.documentUx.resetSearch') }}
          </n-button>
        </div>
      </div>
      <div class="document-browser" :class="{ 'document-browser--reading': reading && selectedIndex >= 0 }">
        <div ref="listElement" class="document-browser-list min-w-0 space-y-3">
          <template v-for="(item, index) in items" :key="item.id">
            <h3 v-if="!compact && order === 'recorded' && (index === 0 || localDocumentDate(item.occurred_at) !== localDocumentDate(items[index - 1].occurred_at))" class="aira-type-section-title m-0 pt-2" data-testid="document-day-heading">
              {{ localDocumentDate(item.occurred_at) }}
            </h3>
            <router-link :to="compact ? { name: 'research-document-detail', params: { documentId: item.id } } : browseTo(item.id)" class="document-row" :class="{ 'document-row--active': reading === item.id }" :aria-current="reading === item.id ? 'true' : undefined" data-testid="research-document-link">
              <div class="min-w-0 flex-1">
                <h3 class="aira-type-card-title m-0 break-words">
                  {{ item.title }}
                </h3>
                <p class="aira-type-meta my-1">
                  {{ t(`page.researchDocuments.${item.kind}`) }} · {{ t('page.documentBrowse.recordedDate') }} {{ localDocumentDate(item.occurred_at) }}
                </p>
                <p class="aira-type-meta my-1">
                  {{ t('page.documentBrowse.updated') }} {{ new Date(item.updated_at).toLocaleString() }}
                </p>
                <p v-if="!compact" class="aira-type-body aira-text-secondary line-clamp-2 m-0 break-words">
                  {{ item.excerpt }}
                </p>
                <div v-if="item.tags.length" class="mt-2 flex flex-wrap gap-1">
                  <n-tag v-for="tag in item.tags" :key="tag" size="small">
                    {{ tag }}
                  </n-tag>
                </div>
              </div>
              <n-tag :type="item.state === 'submitted' ? 'success' : 'default'">
                {{ t(`page.researchDocuments.${item.state}`) }}
              </n-tag>
            </router-link>
          </template>
          <n-pagination v-if="!compact && total > 20" :page="page" :item-count="total" :page-size="20" :page-slot="5" @update:page="router.replace(browseTo('', $event))" />
        </div>
        <document-reader v-if="reading && selectedIndex >= 0" :id="reading" :previous="previous" :next="next" :pending="moving" @previous="move(-1)" @next="move(1)" @close="router.replace(browseTo(''))" />
      </div>
      <n-alert v-if="reading && !loading && selectedIndex < 0 && !error" type="info" class="mt-3">
        {{ t('page.documentBrowse.notInResults') }} <n-button @click="router.replace(browseTo(''))">
          {{ t('page.documentBrowse.backList') }}
        </n-button>
      </n-alert>
    </n-spin>
    <new-document-dialog v-if="showCreate" :scope="scope" @close="showCreate = false" />
    <input v-if="canWrite && !compact" ref="archiveInput" type="file" accept=".zip" hidden :disabled="busy" data-testid="document-archive-input" @change="selectArchive">
    <n-modal
      :show="Boolean(archive?.preview)"
      preset="card"
      class="aira-dialog"
      :title="t('page.researchDocuments.importArchive')"
      :mask-closable="false"
      @update:show="archive = undefined"
    >
      <p>
        {{ t("page.researchDocuments.importHint") }} ·
        {{
          t(
            `page.researchDocuments.scope${scope.scope_type[0].toUpperCase()}${scope.scope_type.slice(1)}`,
          )
        }}
      </p>
      <snapshot-preview :snapshot="archive?.preview?.snapshot" />
      <n-button type="primary" :loading="busy" class="mt-4" @click="importArchive(true)">
        {{ t("page.researchDocuments.confirm") }}
      </n-button>
    </n-modal>
  </section>
</template>

<style scoped>
.document-list-heading { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 12px; }
.document-list-actions { display: flex; align-items: center; gap: 8px; }
.document-list-tools { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.document-list-search { display: flex; flex: 1 1 240px; gap: 8px; min-width: 0; }
.document-list-order { width: 170px; min-height: 40px; }
.document-list-empty { display: flex; align-items: center; gap: 20px; padding: 32px; border: 1px dashed #d1d5db; border-radius: 12px; background: #f9fafb; }
.document-list-empty-icon { flex-shrink: 0; color: #8b98ab; }
@media (max-width: 600px) {
  .document-list-search { flex-basis: 100%; }
  .document-list-order { flex: 1; width: auto; }
  .document-list-empty { align-items: flex-start; gap: 12px; padding: 24px 16px; }
}
.document-browser { display: grid; gap: 16px; align-items: start; }
.document-row--active { border-color: #1677ff !important; background: #eff6ff; }
@media (min-width: 1024px) {
  .document-browser--reading { grid-template-columns: minmax(240px, 0.4fr) minmax(0, 1fr); }
  .document-browser--reading .document-row { flex-direction: column; }
  .document-browser--reading .document-browser-list { max-height: calc(100dvh - 120px); overflow-y: auto; padding: 2px; }
}
@media (max-width: 1023px) {
  .document-browser--reading .document-browser-list { display: none; }
}

.document-row {
  display: flex;
  align-items: flex-start;
  gap: 1rem;
  padding: 1rem;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  color: inherit;
  text-decoration: none;
}
.document-row:hover,
.document-row:focus-visible {
  border-color: #1677ff;
  background: #f8fbff;
}
@media (max-width: 480px) {
  .document-row {
    flex-direction: column;
  }
}
</style>
