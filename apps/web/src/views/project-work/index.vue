<script setup lang="ts">
import type { ProjectWork, WorkState } from "@/service/api/project-work"
import { templateError } from "@/service/api/document-templates"
import { listProjectWork, projectWorkMembers, workStates } from "@/service/api/project-work"
import { useProjectInfoStore } from "@/views/project-protocols/hooks/useProjectInfoStore"
import { useI18n } from "vue-i18n"
import WorkEditor from "./work-editor.vue"

const { projectInfo } = useProjectInfoStore()
const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const items = ref<ProjectWork[]>([])
const members = ref<{ id: string, name: string }[]>([])
const total = ref(0)
const page = ref(1)
const q = ref("")
const mine = ref(false)
const appliedQuery = ref("")
const stateFilter = ref<WorkState | "all" | "active">("all")
const hasFilters = computed(() => Boolean(appliedQuery.value || mine.value || stateFilter.value !== "all"))
const stateOptions = computed(() => [
  { value: "all", label: t("page.projectWork.allStates") },
  { value: "active", label: t("page.projectWork.activeOnly") },
  ...workStates.map(value => ({ value, label: t(`page.projectWork.states.${value}`) })),
])
const loading = ref(false)
const error = ref("")
const canWrite = ref(false)
const view = ref("list")
const showNew = ref(false)
const selectedId = computed(() =>
  typeof route.query.item === "string" ? route.query.item : undefined,
)
const active = computed(() =>
  items.value.filter(item => !["done", "cancelled"].includes(item.state)),
)
function owner(item: ProjectWork) {
  return members.value.find(m => m.id === item.assignee_user_id)?.name
    || (item.assignee_user_id ? t("page.projectWork.formerMember") : t("page.projectWork.unassigned"))
}
const plan = computed(() => items.value.filter(item => item.planned_start && item.planned_end))
const minDate = computed(() => plan.value.map(item => item.planned_start!).sort()[0])
const maxDate = computed(() =>
  plan.value
    .map(item => item.planned_end!)
    .sort()
    .at(-1),
)
const day = (value: string) => Date.parse(`${value}T00:00:00Z`) / 86400000
const planDays = computed(() =>
  minDate.value && maxDate.value ? Math.max(1, day(maxDate.value) - day(minDate.value) + 1) : 1,
)
function bar(item: ProjectWork) {
  return {
    marginLeft: `${(100 * (day(item.planned_start!) - day(minDate.value))) / planDays.value}%`,
    width: `${Math.max(1, (100 * (day(item.planned_end!) - day(item.planned_start!) + 1)) / planDays.value)}%`,
  }
}
let sequence = 0
async function load() {
  const ticket = ++sequence
  const projectId = projectInfo.value?.id
  if (!projectId) {
    loading.value = false
    return
  }
  loading.value = true
  error.value = ""
  try {
    const [result, team] = await Promise.all([
      listProjectWork({
        project_id: projectId,
        q: appliedQuery.value,
        mine: mine.value,
        state: workStates.includes(stateFilter.value as WorkState) ? stateFilter.value as WorkState : undefined,
        active_only: stateFilter.value === "active",
        page: page.value,
        page_size: 100,
      }),
      projectWorkMembers(projectId),
    ])
    if (ticket !== sequence)
      return
    items.value = result.items
    total.value = result.total
    canWrite.value = result.can_write
    members.value = team.members
  }
  catch (err) {
    if (ticket === sequence)
      error.value = templateError(err, t("page.projectWork.failed"))
  }
  finally {
    if (ticket === sequence)
      loading.value = false
  }
}
function search() {
  appliedQuery.value = q.value.trim()
  page.value = 1
  void load()
}
function clearFilters() {
  q.value = ""
  mine.value = false
  stateFilter.value = "all"
  search()
}
function open(id: string) {
  void router.push({
    name: "project-work",
    params: route.params,
    query: { ...route.query, item: id },
  })
}
function close() {
  showNew.value = false
  void router.replace({
    name: "project-work",
    params: route.params,
    query: { ...route.query, item: undefined, create: undefined },
  })
}
function saved(id: string) {
  if (showNew.value) {
    showNew.value = false
    void router.replace({
      name: "project-work",
      params: route.params,
      query: { ...route.query, item: id, create: undefined },
    })
  }
  void load()
}
watch(
  () => projectInfo.value?.id,
  () => {
    page.value = 1
    items.value = []
    canWrite.value = false
    showNew.value = false
    void load()
  },
  { immediate: true },
)
watch([() => route.query.create, canWrite], ([create, allowed]) => {
  if (create === "1" && allowed && !selectedId.value)
    showNew.value = true
}, { immediate: true })
onBeforeUnmount(() => sequence++)
</script>

<template>
  <section class="min-w-0 space-y-4" data-testid="project-work">
    <header class="flex flex-wrap items-center justify-between gap-3">
      <div
      ><h1 class="aira-type-page-title m-0">{{ t("page.projectWork.title") }}</h1
      ><p class="mb-0 mt-1 text-sm text-gray-500">{{ t("page.projectWork.intro") }}</p></div
      >
      <n-button v-if="canWrite" type="primary" data-testid="work-new" @click="showNew = true"
      >+ {{ t("page.projectWork.new") }}</n-button
      >
    </header>
    <n-alert v-if="error" type="error"
    >{{ error }}<n-button @click="load">{{ t("page.projectWork.reload") }}</n-button></n-alert
    >
    <form
      class="flex flex-wrap items-center gap-2 rounded-lg bg-gray-50 p-3"
      @submit.prevent="search"
    >
      <n-input
        v-model:value="q"
        class="min-w-40 !w-auto sm:flex-1"
        clearable
        :placeholder="t('page.projectWork.search')"
        @clear="q = ''; search()"
      />
      <n-button attr-type="submit" :loading="loading">{{ t("common.search") }}</n-button>
      <n-select
        v-model:value="stateFilter"
        :options="stateOptions"
        :aria-label="t('page.projectWork.state')"
        class="!w-40"
        data-testid="work-state-filter"
        @update:value="search"
      />
      <n-checkbox
        v-model:checked="mine"
        @update:checked="search"
      >{{ t("page.projectWork.mine") }}</n-checkbox
      >
      <n-button v-if="hasFilters" quaternary data-testid="work-clear-filters" @click="clearFilters">{{ t("page.projectWork.clearFilters") }}</n-button>
      <n-radio-group
        v-model:value="view"
        size="small"
        class="sm:ml-auto"
        :aria-label="t('page.projectWork.view')"
      >
        <n-radio-button v-for="mode in ['list', 'board', 'plan']" :key="mode" :value="mode">{{
          t(`page.projectWork.views.${mode}`)
        }}</n-radio-button>
      </n-radio-group>
    </form>
    <div class="flex flex-wrap gap-x-6 gap-y-2 text-sm text-gray-600">
      <span>{{ t("page.projectWork.count", { count: total }) }}</span>
      <span>{{ t("page.projectWork.inProgressCount", { count: active.length }) }}</span>
      <span>{{
        t("page.projectWork.blockedCount", {
          count: items.filter(item => item.state === "blocked").length,
        })
      }}</span>
    </div>
    <n-spin :show="loading">
      <div
        v-if="!items.length && !loading && !error"
        class="rounded-lg border border-dashed border-gray-300 p-8 text-center"
      >
        <h2 class="text-lg">{{ t(hasFilters ? "page.projectWork.noMatches" : "page.projectWork.empty") }}</h2
        ><p class="text-gray-500">{{ t(hasFilters ? "page.projectWork.noMatchesHint" : "page.projectWork.emptyHint") }}</p>
        <n-button v-if="hasFilters" @click="clearFilters">{{ t("page.projectWork.clearFilters") }}</n-button>
        <n-button v-else-if="canWrite" type="primary" @click="showNew = true">{{
          t("page.projectWork.new")
        }}</n-button>
      </div>
      <div v-else-if="view === 'list'" class="space-y-2">
        <button
          v-for="item in items"
          :key="item.id"
          type="button"
          class="work-row"
          @click="open(item.id)"
        >
          <div class="min-w-0 flex-1"
          ><div class="flex flex-wrap items-baseline gap-2"
          ><span class="text-xs text-gray-500">{{
            t(`page.projectWork.kinds.${item.kind}`)
          }}</span
          ><strong class="break-words">{{ item.title }}</strong></div
          ><p
            v-if="item.blocker && item.state === 'blocked'"
            class="mb-0 mt-1 text-sm text-amber-700"
          >{{ item.blocker }}</p
          ><p v-else-if="item.next_step" class="mb-0 mt-1 text-sm text-gray-500">{{
            item.next_step
          }}</p></div
          >
          <span class="text-sm text-gray-500">{{ owner(item) }}</span>
          <time v-if="item.planned_end" class="text-sm text-gray-500">{{ item.planned_end }}</time>
          <n-tag
            size="small"
            :type="
              item.state === 'blocked' ? 'warning' : item.state === 'done' ? 'success' : 'default'
            "
          >{{ t(`page.projectWork.states.${item.state}`) }}</n-tag
          >
        </button>
      </div>
      <div
        v-else-if="view === 'board'"
        class="max-w-full overflow-x-auto pb-4"
        tabindex="0"
        :aria-label="t('page.projectWork.views.board')"
      >
        <div class="grid grid-cols-6 min-w-300 gap-3">
          <section
            v-for="state in workStates"
            :key="state"
            class="min-w-0 rounded-lg bg-gray-50 p-3"
            :aria-label="t(`page.projectWork.states.${state}`)"
          >
            <h2 class="m-0 mb-3 text-sm font-semibold"
            >{{ t(`page.projectWork.states.${state}`) }} ·
              {{ items.filter(item => item.state === state).length }}</h2
            >
            <button
              v-for="item in items.filter(item => item.state === state)"
              :key="item.id"
              type="button"
              class="mb-3 w-full rounded border border-gray-200 bg-white p-3 text-left hover:border-primary"
              @click="open(item.id)"
            >
              <small>{{ t(`page.projectWork.kinds.${item.kind}`) }}</small
              ><strong class="my-2 block break-words">{{ item.title }}</strong
              ><span class="text-sm text-gray-500">{{ owner(item) }}</span
              ><time v-if="item.planned_end" class="mt-1 block text-xs">{{
                item.planned_end
              }}</time>
            </button>
          </section>
        </div>
      </div>
      <div v-else-if="view === 'plan'" class="rounded-lg border border-gray-200 p-4">
        <p class="mt-0 text-sm text-gray-500">{{ t("page.projectWork.planHint") }}</p>
        <div v-if="plan.length" class="overflow-x-auto" tabindex="0">
          <div class="min-w-160"
          ><div class="mb-3 ml-48 flex justify-between text-xs text-gray-500"
           ><time>{{ minDate }}</time
           ><time>{{ maxDate }}</time></div
           >
            <button
              v-for="item in plan"
              :key="item.id"
              type="button"
              class="mb-3 grid w-full grid-cols-[12rem_1fr] items-center gap-3 text-left"
              @click="open(item.id)"
            ><span class="truncate">{{ item.title }}</span
            ><div class="min-w-0 rounded bg-gray-100"
            ><div
              :style="bar(item)"
              class="min-h-7 rounded bg-blue-200 px-2 text-xs leading-7"
              :title="`${item.planned_start} → ${item.planned_end}`"
            >{{ t(`page.projectWork.states.${item.state}`) }}</div
            ></div
            ></button
            >
          </div>
        </div>
        <p v-else>{{ t("page.projectWork.noPlan") }}</p>
        <p v-if="items.length > plan.length" class="text-sm text-gray-500">{{
          t("page.projectWork.unplanned", { count: items.length - plan.length })
        }}</p>
      </div>
    </n-spin>
    <n-pagination
      v-if="total > 100"
      v-model:page="page"
      :page-size="100"
      :item-count="total"
      @update:page="load"
    />
    <work-editor
      v-if="(showNew || selectedId) && projectInfo"
      :key="selectedId || 'new'"
      :item-id="selectedId"
      :project-id="projectInfo.id"
      :project-name="projectInfo.name"
      :lab-id="projectInfo.lab_id"
      :items="items"
      @close="close"
      @saved="saved"
    />
  </section>
</template>

<style scoped>
.work-row {
  display: flex;
  width: 100%;
  align-items: center;
  gap: 16px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 16px;
  text-align: left;
  background: white;
}
.work-row:hover {
  border-color: #91caff;
  background: #fafcff;
}
@media (max-width: 640px) {
  .work-row {
    flex-wrap: wrap;
    gap: 8px;
  }
  .work-row > div {
    flex-basis: 100%;
  }
}
</style>
