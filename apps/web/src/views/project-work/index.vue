<script setup lang="ts">
import type { ProjectPerson } from "@/service/api/project-people"
import type { ProjectWork, WorkState } from "@/service/api/project-work"
import { templateError } from "@/service/api/document-templates"
import { listProjectPeople } from "@/service/api/project-people"
import { listProjectWork, projectWorkMembers, workStates } from "@/service/api/project-work"
import { useProjectInfoStore } from "@/views/project-protocols/hooks/useProjectInfoStore"
import { useI18n } from "vue-i18n"
import WorkBoard from "./work-board.vue"
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
const personFilter = ref<string | null>(null)
const people = ref<ProjectPerson[]>([])
const appliedQuery = ref("")
const stateFilter = ref<WorkState | "all" | "active">("all")
const hasFilters = computed(() => Boolean(appliedQuery.value || mine.value || personFilter.value || stateFilter.value !== "all"))
const showControls = computed(() => total.value > 0 || hasFilters.value)
const stateOptions = computed(() => [
  { value: "all", label: t("page.projectWork.allStates") },
  { value: "active", label: t("page.projectWork.activeOnly") },
  ...workStates.map(value => ({ value, label: t(`page.projectWork.states.${value}`) })),
])
const loading = ref(true)
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
  return people.value.find(p => p.id === item.assignee_person_id)?.display_name
    || item.people_snapshot?.find(p => p.id === item.assignee_person_id)?.name
    || members.value.find(m => m.id === item.assignee_user_id)?.name
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
    loading.value = true
    return
  }
  loading.value = true
  error.value = ""
  try {
    const [result, team, contacts] = await Promise.all([
      listProjectWork({
        project_id: projectId,
        q: appliedQuery.value,
        mine: mine.value,
        person_id: personFilter.value?.startsWith("person:") ? personFilter.value.slice(7) : undefined,
        assignee_id: personFilter.value?.startsWith("user:") ? personFilter.value.slice(5) : undefined,
        state: workStates.includes(stateFilter.value as WorkState) ? stateFilter.value as WorkState : undefined,
        active_only: stateFilter.value === "active",
        page: page.value,
        page_size: 100,
      }),
      projectWorkMembers(projectId),
      listProjectPeople(projectId),
    ])
    if (ticket !== sequence)
      return
    items.value = result.items
    total.value = result.total
    canWrite.value = result.can_write
    members.value = team.members
    people.value = contacts.people
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
  personFilter.value = null
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
    total.value = 0
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
      <n-button v-if="canWrite && showControls" type="primary" data-testid="work-new" @click="showNew = true"
      >+ {{ t("page.projectWork.new") }}</n-button
      >
    </header>
    <n-alert v-if="error" type="error"
    >{{ error }}<n-button @click="load">{{ t("page.projectWork.reload") }}</n-button></n-alert
    >
    <form
      v-if="showControls"
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
      <n-select v-model:value="personFilter" :options="[...people.map(p => ({ value: p.user_id ? `user:${p.user_id}` : `person:${p.id}`, label: `${p.display_name || p.name}${p.organization ? ` · ${p.organization}` : ''}` })), ...members.filter(m => !people.some(p => p.user_id === m.id)).map(m => ({ value: `user:${m.id}`, label: m.name }))]" :placeholder="t('page.projectWork.assignee')" filterable clearable class="!w-44" @update:value="search" />
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
    <div v-if="showControls" class="flex flex-wrap gap-x-6 gap-y-2 text-sm text-gray-600">
      <span>{{ t("page.projectWork.count", { count: total }) }}</span>
      <span>{{ t("page.projectWork.inProgressCount", { count: active.length }) }}</span>
      <span>{{
        t("page.projectWork.blockedCount", {
          count: items.filter(item => item.state === "blocked").length,
        })
      }}</span>
    </div>
    <n-spin :show="loading" class="min-h-64">
      <div
        v-if="!items.length && !loading && !error"
        class="work-empty"
        data-testid="work-empty"
      >
        <div class="work-empty-icon" aria-hidden="true"><n-icon :size="26"><icon-tabler-clipboard-list /></n-icon></div>
        <h2 class="m-0 text-lg font-semibold">{{ t(hasFilters ? "page.projectWork.noMatches" : "page.projectWork.empty") }}</h2>
        <p class="mb-6 mt-2 max-w-sm text-sm leading-relaxed text-gray-500">{{ t(hasFilters ? "page.projectWork.noMatchesHint" : canWrite ? "page.projectWork.emptyHint" : "page.projectWork.emptyReadOnlyHint") }}</p>
        <n-button v-if="hasFilters" @click="clearFilters">{{ t("page.projectWork.clearFilters") }}</n-button>
        <n-button v-else-if="canWrite" type="primary" data-testid="work-new" @click="showNew = true"><template #icon><n-icon><icon-tabler-plus /></n-icon></template>{{
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
      <work-board
        v-else-if="view === 'board' && projectInfo"
        :key="projectInfo.id"
        :project-id="projectInfo.id"
        :items="items"
        :loading="loading"
        :can-write="canWrite"
        :owner="owner"
        @open="open"
        @saved="load"
      />
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
      :people="people"
      @close="close"
      @saved="saved"
    />
  </section>
</template>

<style scoped>
.work-empty {
  display: flex;
  min-height: 280px;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  padding: 40px 24px;
  background: white;
  text-align: center;
}
.work-empty-icon {
  display: grid;
  width: 52px;
  height: 52px;
  margin-bottom: 16px;
  place-items: center;
  border-radius: 50%;
  background: #f3f4f6;
  color: #6b7280;
}
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
