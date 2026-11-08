<script setup lang="ts">
import type { PinnedItem } from "@/service/api/pinned-items"
import type { WorkspaceProject } from "@/service/api/workspace"
import type { ProjectCard } from "@/utils/projectWorkspace"
import type { RouteLocationRaw } from "vue-router"
import { PinnedResourceType } from "@/service/api/pinned-items"
import { fetchProjectList } from "@/service/api/projects"
import { fetchUserProjects } from "@/service/api/users"
import { recentProjectWorkspaces, resolveDraftDestinations } from "@/service/api/workspace"
import { useAuthStore } from "@/store/modules/auth"
import { useInstanceStore } from "@/store/modules/instance"
import { mergeProjectWorkspaces } from "@/utils/projectWorkspace"
import { listRecordDrafts, recordDraftQuery } from "@/utils/recordDrafts"
import CreateProjectModal from "@/views/projects/modules/create-project-modal.vue"
import PinIcon from "~icons/tabler/pin"
import { useI18n } from "vue-i18n"
import { useRouter } from "vue-router"

const props = defineProps<{ pins: PinnedItem[], pinningKeys: Set<string> }>()
const emit = defineEmits<{ togglePin: [payload: { resourceType: PinnedResourceType, resourceId: string }] }>()
const auth = useAuthStore()
const instance = useInstanceStore()
const router = useRouter()
const { t } = useI18n()
const loading = ref(true)
const error = ref(false)
const cards = ref<ProjectCard[]>([])
const expanded = ref(false)
const visibleCards = computed(() => expanded.value ? cards.value : cards.value.slice(0, 4))
const hasHistory = computed(() => cards.value.some(item => item.lastUsed > 0))
let sequence = 0

async function load() {
  const current = ++sequence
  const userId = auth.userInfo.id
  cards.value = []
  if (!userId)
    return
  loading.value = true
  error.value = false
  try {
    const drafts = listRecordDrafts(userId)
    const protocolIds = [...new Set(drafts.map(item => item.protocolId).filter(id => /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id)))].slice(0, 50)
    const [recent, destinations] = await Promise.all([
      recentProjectWorkspaces(),
      protocolIds.length ? resolveDraftDestinations(protocolIds) : Promise.resolve({ items: [] }),
    ])
    let next = mergeProjectWorkspaces(recent.items, destinations.items, drafts)
    if (!next.length) {
      const available = instance.isSingleLab && instance.lab
        ? await fetchProjectList({ page: 1, pageSize: 4, labUid: instance.lab.uid })
        : await fetchUserProjects(userId, { page: 1, pageSize: 4 })
      next = (available?.projects || []).map(item => ({
        id: String(item.id),
        uid: item.uid,
        name: item.name,
        lab_uid: item.lab_uid,
        lab_name: item.lab_name,
        visited_at: null,
        pinned_id: null,
        target: null,
        lastUsed: 0,
      }))
    }
    if (current === sequence && auth.userInfo.id === userId)
      cards.value = next
  }
  catch {
    if (current === sequence && auth.userInfo.id === userId)
      error.value = true
  }
  finally {
    if (current === sequence)
      loading.value = false
  }
}

function projectRoute(item: WorkspaceProject, section: "overview" | "protocols" | "documents" = "overview"): RouteLocationRaw {
  return { name: `project-${section}`, params: { labUid: item.lab_uid, projectUid: item.uid } }
}
function resumeRoute(item: ProjectCard): RouteLocationRaw {
  if (item.draft && item.target) {
    return {
      name: "add-protocol-record",
      params: item.target.route.params,
      query: { ...recordDraftQuery(item.draft.scope?.query || {}), draft: item.draft.draftId, resumeDraft: "true" },
    }
  }
  return item.target?.route || projectRoute(item)
}
function targetLabel(item: ProjectCard) {
  if (!item.lastUsed)
    return t("page.home.workspace.availableProject")
  if (item.draft)
    return t("page.home.workspace.draft")
  return t(`page.home.workspace.target.${item.target?.kind || "project"}`)
}
function targetTitle(item: ProjectCard) {
  const target = item.target
  if (!target)
    return t("page.home.workspace.noTarget")
  if (target.kind === "project")
    return t(`page.home.workspace.section.${target.section || "overview"}`)
  if (target.kind === "record")
    return t("page.home.workspace.recordTitle", { name: target.title, number: target.record_number })
  return target.title
}
function pinKey(item: ProjectCard) {
  return `${PinnedResourceType.Project}:${item.id}`
}
function isPinned(item: ProjectCard) {
  return props.pins.some(pin => pin.resource_type === PinnedResourceType.Project && pin.resource_id === item.id)
}
function onCreated(project: Api.Project.MyProjectInfo) {
  void router.push({ name: "project-overview", params: { labUid: project.lab_uid, projectUid: project.uid } })
}
watch(() => auth.userInfo.id, load, { immediate: true })
watch(() => props.pins.filter(pin => pin.resource_type === PinnedResourceType.Project).map(pin => pin.id).join(","), load)
onBeforeUnmount(() => sequence++)
</script>

<template>
  <section data-testid="home-project-workspaces" :aria-label="t('page.home.workspace.projects')">
    <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
      <h2 class="aira-type-section-title m-0">
        {{ t('page.home.workspace.projects') }}
      </h2>
      <router-link :to="{ name: 'project-dashboard' }" class="text-primary hover:underline">
        {{ t('page.home.workspace.allProjects') }} →
      </router-link>
    </div>
    <n-alert v-if="error" type="error" :title="t('page.home.workspace.loadError')" data-testid="home-project-error">
      <n-button size="small" @click="load">
        {{ t('common.retry') }}
      </n-button>
    </n-alert>
    <div v-else-if="loading" class="grid gap-3 sm:grid-cols-2" role="status" :aria-label="t('common.loading')">
      <n-skeleton v-for="index in 2" :key="index" height="180px" :sharp="false" />
    </div>
    <template v-else>
      <p class="aira-type-meta mb-3 mt-0" data-testid="home-project-history-hint">
        {{ t(hasHistory ? 'page.home.workspace.historyHint' : 'page.home.workspace.firstVisitHint') }}
      </p>
      <div v-if="cards.length" class="grid gap-3 sm:grid-cols-2">
        <article v-for="item in visibleCards" :key="item.id" class="project-workspace" data-testid="home-project-card" :data-project-id="item.id">
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0">
              <p v-if="!instance.isSingleLab" class="aira-type-meta m-0 break-words">
                {{ item.lab_name }}
              </p>
              <router-link :to="projectRoute(item)" class="aira-type-card-title mt-1 block break-words hover:text-primary" data-testid="home-open-project">
                {{ item.name }}
              </router-link>
            </div>
            <n-button quaternary size="small" :aria-label="t(isPinned(item) ? 'icon.unpin' : 'icon.pin')" :title="t(isPinned(item) ? 'icon.unpin' : 'icon.pin')" :aria-pressed="isPinned(item)" :loading="pinningKeys.has(pinKey(item))" @click="emit('togglePin', { resourceType: PinnedResourceType.Project, resourceId: item.id })">
              <n-icon :component="PinIcon" :size="18" :class="{ 'text-primary': isPinned(item) }" />
            </n-button>
          </div>
          <div class="project-workspace__last">
            <p class="aira-type-meta mb-1 mt-0">
              {{ targetLabel(item) }}<template v-if="item.lastUsed">
                · <n-time :time="item.lastUsed" type="relative" />
              </template>
            </p>
            <p class="aira-type-body line-clamp-2 m-0 break-words">
              {{ targetTitle(item) }}
            </p>
          </div>
          <div class="mt-auto flex flex-wrap items-center gap-x-4 gap-y-2 pt-3">
            <router-link v-if="item.target" :to="resumeRoute(item)" class="project-workspace__resume" data-testid="home-resume-project">
              {{ t(item.draft ? 'page.home.workspace.resumeDraft' : item.target.kind === 'recording' ? 'page.home.workbench.viewProtocolAction' : 'page.home.workspace.resume') }} →
            </router-link>
            <router-link v-else :to="projectRoute(item)" class="project-workspace__resume">
              {{ t('page.home.workbench.openProjectAction') }} →
            </router-link>
            <router-link :to="projectRoute(item, 'protocols')" class="text-primary hover:underline">
              {{ t('page.home.workspace.section.protocols') }}
            </router-link>
            <router-link :to="projectRoute(item, 'documents')" class="text-primary hover:underline">
              {{ t('page.home.workspace.section.documents') }}
            </router-link>
          </div>
          <p v-if="item.draft" class="aira-type-meta mb-0 mt-2">
            {{ t('page.home.workbench.savedOnDevice') }}
          </p>
        </article>
      </div>
      <div v-else class="border border-gray-300 rounded-xl border-dashed p-5">
        <p class="aira-type-body mb-4 mt-0">
          {{ t('page.home.workspace.empty') }}
        </p>
        <create-project-modal :button-props="{ type: 'primary' }" :show-icon="false" :trigger="t('page.home.workbench.createProjectAction')" @modal:new-project="onCreated" />
      </div>
      <n-button v-if="cards.length > 4" class="mt-3" quaternary @click="expanded = !expanded">
        {{ t(expanded ? 'page.home.workspace.showLess' : 'page.home.workspace.showMore', { count: cards.length }) }}
      </n-button>
    </template>
  </section>
</template>

<style scoped>
.project-workspace { display: flex; min-width: 0; flex-direction: column; border: 1px solid #dce5f0; border-radius: 0.875rem; padding: 1rem 1.125rem; background: linear-gradient(135deg, #f7faff, #fff 65%); }
.project-workspace__last { margin-top: 1rem; padding-top: 0.75rem; border-top: 1px solid #e8edf4; }
.project-workspace__resume { display: inline-flex; align-items: center; min-height: 2.25rem; padding: 0.375rem 0.75rem; border: 1px solid #c8def9; border-radius: 0.5rem; background: white; color: #1765bc; font-weight: 500; }
.project-workspace a:focus-visible { outline: 2px solid #1976ed; outline-offset: 3px; }
</style>
