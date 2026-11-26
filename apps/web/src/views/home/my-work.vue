<script setup lang="ts">
import { loadWorkPage, loadWorkProjects, type Period, type Scope, type WorkView } from "@/service/api/my-work"
import { useAuthStore } from "@/store/modules/auth"
import { localDocumentDate } from "@/utils/documentBrowse"
import AssignedTask from "@/views/meetings/assigned-task.vue"
import OrganizationRoom from "@/views/meetings/organization-room.vue"
import { useI18n } from "vue-i18n"

const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const view = computed<WorkView>(() => route.query.view === "todos" ? "todos" : "meetings")
const scope = computed<Scope>(() => route.query.scope === "managed" || route.query.scope === "visible" ? route.query.scope : "mine")
const period = computed<Period>(() => route.query.period === "past" || route.query.period === "undated" ? route.query.period : "upcoming")
const page = computed(() => Math.max(1, Math.min(1000000, Number.parseInt(String(route.query.page || 1), 10) || 1)))
const project = computed(() => typeof route.query.project === "string" ? route.query.project : undefined)
const result = ref<Awaited<ReturnType<typeof loadWorkPage>>>()
const projects = ref<{ name: string, id: string }[]>([])
const failed = ref(false)
const projectError = ref(false)
const retry = ref(0)
const scopes = computed(() => [
  { value: "mine", label: t(view.value === "meetings" ? "page.myWork.mineMeetings" : "page.myWork.mineTodos") },
  { value: "managed", label: t("page.myWork.managed") },
  { value: "visible", label: t("page.myWork.visible") },
])
const periods = computed(() => (["upcoming", "past", "undated"] as const).map(value => ({ value, label: t(`page.myWork.${value}`) })))
function setFilter(key: string, value?: string | number | null) {
  const query = { ...route.query, page: undefined, [key]: value || undefined }
  if (key === "scope")
    delete query.project
  void router.push({ name: "my-work", query })
}
watch([scope, () => auth.userInfo.id, retry], async (_, __, onCleanup) => {
  let current = true
  onCleanup(() => {
    current = false
  })
  projects.value = []
  projectError.value = false
  try {
    const data = await loadWorkProjects(scope.value)
    if (current)
      projects.value = data.projects
  }
  catch {
    if (current)
      projectError.value = true
  }
}, { immediate: true })
watch([view, scope, period, project, page, () => auth.userInfo.id, retry], async (_, __, onCleanup) => {
  let current = true
  onCleanup(() => {
    current = false
  })
  result.value = undefined
  failed.value = false
  try {
    const data = await loadWorkPage(view.value, { scope: scope.value, period: period.value, project_id: project.value, page: page.value })
    if (current)
      result.value = data
  }
  catch {
    if (current)
      failed.value = true
  }
}, { immediate: true })
function statusLabel(kind: string, status: string) {
  if (kind === "followup")
    return t(`page.meetingSpace.${status}`)
  if (kind === "approval")
    return t("page.myWork.pending")
  const group = kind === "manual" ? "research.workItemStatus" : kind === "research" ? "research.taskStatus" : "projectWork.states"
  return t(`page.${group}.${status}`)
}
function kindLabel(kind: string) {
  if (kind === "followup")
    return t("page.meetingSpace.actions")
  return t(["approval", "manual", "research"].includes(kind) ? `page.myWork.${kind}` : `page.projectWork.kinds.${kind}`)
}
</script>

<template>
  <organization-room v-if="typeof route.query.room === 'string'" :key="route.query.room" :id="route.query.room" />
  <div v-else-if="typeof route.query.task === 'string'" class="mx-auto max-w-4xl p-4"><router-link to="/my-work?view=todos">← {{ t("page.myWork.todos") }}</router-link><assigned-task :key="route.query.task" :id="route.query.task" /></div>
  <main v-else class="my-work mx-auto max-w-5xl w-full p-4 sm:p-6">
    <h1 class="aira-type-page-title mb-4">
      {{ t("page.myWork.title") }}
    </h1>
    <router-link v-if="view === 'meetings'" class="mb-3 inline-block text-primary" to="/my-work?room=new">{{ t("page.meetingSpace.newRoom") }}</router-link>
    <nav :aria-label="t('page.myWork.title')" class="mb-4 flex gap-5 border-b border-gray-200">
      <router-link
        v-for="tab in (['meetings', 'todos'] as const)" :key="tab"
        :to="{ name: 'my-work', query: { ...route.query, view: tab, page: undefined } }"
        :aria-current="view === tab ? 'page' : undefined" class="view-link px-1 py-2"
      >
        {{ t(tab === 'meetings' ? 'page.myWork.meetings' : 'page.myWork.todos') }}
      </router-link>
    </nav>
    <div class="mb-5 flex flex-wrap gap-2">
      <n-select :value="scope" :options="scopes" class="max-w-full w-42" :aria-label="t('page.myWork.scope')" @update:value="setFilter('scope', $event)" />
      <n-select
        :value="project || null" :options="projects" value-field="id" label-field="name" filterable clearable
        class="max-w-full w-60" :aria-label="t('page.myWork.projects')" :placeholder="t('page.myWork.projects')" @update:value="setFilter('project', $event)"
      />
      <n-select v-if="view === 'meetings'" :value="period" :options="periods" class="max-w-full w-40" :aria-label="t('page.myWork.period')" @update:value="setFilter('period', $event)" />
    </div>
    <n-alert v-if="failed || projectError" type="error" class="mb-4">
      {{ t("page.myWork.error") }} <n-button text @click="retry++">
        {{ t("common.retry") }}
      </n-button>
    </n-alert>
    <n-skeleton v-if="!result && !failed" text :repeat="3" />
    <div v-if="result" aria-live="polite">
      <p v-if="!result.items.length" class="aira-type-body aira-text-muted py-6">
        {{ t(view === 'meetings' ? 'page.myWork.emptyMeetings' : 'page.myWork.emptyTodos') }}
      </p>
      <ol v-else class="m-0 list-none p-0">
        <li v-for="(entry, index) in result.items" :key="entry.href + entry.id" class="min-w-0">
          <template v-if="'open_count' in entry">
            <div v-if="!index || !('day' in result.items[index - 1]!) || (result.items[index - 1] as { day: string | null }).day !== entry.day" class="mt-4 font-semibold">
              {{ entry.day || t("page.myWork.undated") }}
            </div>
            <div class="meeting-line my-1 border-l-2 border-gray-200 py-2 pl-4">
              <router-link :to="entry.href" class="break-words font-medium hover:underline">
                {{ entry.title }}
              </router-link>
              <div class="aira-type-meta mt-1 flex flex-wrap items-center gap-x-2">
                <time v-if="entry.at && entry.time_precision === 'datetime'" :datetime="entry.at">{{ new Date(entry.at).toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' }) }}</time>
                <span>{{ entry.project }}</span><span>{{ t(`page.meetings.${entry.status}`) }}</span>
                <router-link v-if="entry.open_count" class="text-primary" :to="`${entry.href}#meeting-actions`">
                  {{ t("page.myWork.open", { count: entry.open_count }) }}
                </router-link>
              </div>
            </div>
          </template>
          <article v-else class="border-b border-gray-200 py-3">
            <router-link :to="entry.href" class="break-words font-medium hover:underline">
              {{ entry.title }}
            </router-link>
            <div class="aira-type-meta mt-1 flex flex-wrap gap-x-3 gap-y-1">
              <span>{{ entry.project }}</span><span>{{ kindLabel(entry.kind) }} · {{ statusLabel(entry.kind, entry.status) }}</span>
              <span>{{ entry.assignee ? t("page.myWork.assignee", { name: entry.assignee }) : t("page.projectWork.unassigned") }}</span>
              <span v-if="entry.due" :class="{ 'text-red-700': entry.due < localDocumentDate() }">
                <template v-if="entry.due < localDocumentDate()">{{ t("page.myWork.overdue") }} · </template>
                {{ entry.due === localDocumentDate() ? t("page.myWork.today") : t("page.myWork.due", { day: entry.due }) }}
              </span>
            </div>
            <router-link v-for="meeting in entry.meetings" :key="meeting.id" :to="meeting.href" class="mt-1 block break-words text-sm text-primary hover:underline">
              {{ t(meeting.relation === 'created' ? 'page.myWork.created' : 'page.myWork.discussed') }} · {{ meeting.title }}
            </router-link>
          </article>
        </li>
      </ol>
      <div v-if="page > 1 || result.has_more" class="mt-5 flex items-center gap-3">
        <n-button :disabled="page <= 1" @click="setFilter('page', page - 1)">
          {{ t("common.previous") }}
        </n-button>
        <span>{{ t("page.myWork.page", { page }) }}</span>
        <n-button :disabled="!result.has_more" @click="setFilter('page', page + 1)">
          {{ t("common.next") }}
        </n-button>
      </div>
    </div>
  </main>
</template>

<style scoped>
.view-link[aria-current="page"] { color: var(--primary-color, #1677ff); border-bottom: 2px solid currentColor; }
.meeting-line { overflow-wrap: anywhere; }
</style>
