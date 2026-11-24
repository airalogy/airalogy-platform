<template>
  <global-layout>
    <template #assistant>
      <aira-side-panel v-if="hasOpened && projectInfo && !projectInfo.organization_reader" :open="assistantOpen" :label="$t('page.projectAira.panel')" @close="closeAssistant">
        <aira-panel :key="assistantScope" :project-id="projectInfo.id" :project-name="projectTitle" :meeting-name="meetingName" :meeting-id="currentMeetingId" :initial-chat="requestedChat" :can-send="assistantAvailable" @close="closeAssistant" @restart="clearRequestedChat" @review="reviewProposal" />
      </aira-side-panel>
    </template>
    <resource-access-state v-if="failure" :failure="failure" @retry="retry" />
    <n-spin v-else-if="loadingProject" class="mx-auto my-12" />
    <resource-access-state v-else-if="projectInfo?.organization_reader && !['project-overview', 'project-protocols'].includes(String(route.name))" failure="unavailable" />
    <section v-else-if="projectInfo?.organization_reader" class="mx-auto w-full max-w-3xl space-y-4 px-4 py-6">
      <p class="text-sm color-text-secondary">{{ $t('sharing.organization') }}</p>
      <div class="flex flex-wrap items-center justify-between gap-2">
        <h1 class="text-2xl">{{ projectInfo.name }}</h1>
        <workspace-share :project="projectInfo.id" organization-readable />
      </div>
      <p>{{ projectInfo.description }}</p>
      <h2>{{ $t('sharing.protocols') }}</h2>
      <p v-if="!projectInfo.reader_protocols?.length">{{ $t('sharing.emptyCatalog') }}</p>
      <p v-for="item in projectInfo.reader_protocols" :key="item.uid">
        <router-link :to="{ name: 'protocol-detail', params: { labUid: projectInfo.lab_uid, projectUid: projectInfo.uid, protocolUid: item.uid } }" class="text-primary">{{ item.name }}</router-link>
      </p>
    </section>
    <content-layout v-else-if="projectInfo" :title="projectTitle" :tabs="tabs" compact-header>
      <template v-if="authStore.isLogin" #suffix>
        <div class="flex flex-wrap items-center justify-end gap-2">
          <workspace-share v-if="instanceStore.isSingleLab" :key="projectInfo.id" :project="projectInfo.id" :organization-readable="projectInfo.organization_readable" :manage="projectInfo.can_publish" />
          <n-button v-if="assistantAvailable" ref="assistantTrigger" size="small" :aria-expanded="assistantOpen" data-testid="project-aira" @click="headerTrigger = undefined; assistantOpen = !assistantOpen">
            Aira
          </n-button>
          <n-dropdown trigger="click" :options="workspaceNavigation" @select="navigateWorkspace">
            <n-button data-testid="project-more">
              {{ $t('common.more') }}
            </n-button>
          </n-dropdown>
          <add-protocol-modal
            v-if="route.name === 'project-protocols' && canCreateProtocol"
            :compact="false"
            show-icon
            :trigger="$t('common.newProtocol')"
            :project="projectInfo"
            :show-select="false"
            @modal:new-protocol="handleAddProtocol"
          />
        </div>
      </template>
      <template v-if="showIcon" #title>
        <div class="mb-2 mt-2 min-w-0 flex items-start gap-3" data-testid="project-header">
          <project-icon class="shrink-0 !h-9 !w-9" />
          <template v-if="projectInfo">
            <div class="min-w-0 flex-1">
              <router-link
                v-if="authStore.isLogin && !instanceStore.isSingleLab"
                :to="{ name: 'lab-projects', params: { labUid: projectInfo.lab_uid } }"
                class="block break-words text-xs color-text-secondary"
              >
                {{ projectInfo.lab_name || projectInfo.lab_uid }}
              </router-link>
              <span v-else-if="!instanceStore.isSingleLab" class="block break-words text-xs color-text-secondary">
                {{ projectInfo.lab_name || projectInfo.lab_uid }}
              </span>
              <h2 class="m-0 min-w-0 break-words !text-xl !leading-8">
                {{ projectTitle }}
              </h2>
              <p v-if="description" ref="descriptionElement" class="mb-0 mt-1 text-sm color-text-secondary leading-5" :class="{ 'line-clamp-2': !descriptionExpanded }" data-testid="project-description">
                {{ description }}
              </p>
              <button v-if="description && (descriptionOverflow || descriptionExpanded)" type="button" class="mt-1 text-xs text-primary" :aria-expanded="descriptionExpanded" @click="descriptionExpanded = !descriptionExpanded">
                {{ descriptionExpanded ? $t('common.collapse') : $t('common.expand') }}
              </button>
            </div>
            <span v-if="visibilityLabel" class="inline-flex shrink-0 items-center whitespace-nowrap rounded px-2 py-0.5 text-xs font-500" :class="visibilityClass">
              {{ visibilityLabel }}
            </span>
          </template>
          <n-skeleton v-else width="20rem" class="mx-4" />
        </div>
      </template>
    </content-layout>
  </global-layout>
</template>

<script setup lang="ts">
import type { ProjectInfoNameKey } from "#/page-route"
import type { MeetingProposal } from "@/service/api/meetings"
import type { TabPaneProps } from "naive-ui/es/tabs"
import type { MeetingHandoff } from "../meetings/aira-handoff"
import AiraSidePanel from "@/components/common/aira-side-panel.vue"
import ResourceAccessState from "@/components/common/resource-access-state.vue"
import WorkspaceShare from "@/components/protocol/workspace-share.vue"
import { useProjectPermissions } from "@/composables"
import { useProjectVisibility } from "@/composables/useProjectVisibility"
import { useResourcePage } from "@/composables/useResourcePage"
import { useRouterPush } from "@/composables/useRouterPush"
import { useSeoMeta } from "@/composables/useSeoMeta"
import { projectAiraKey, useAiraNarrowScreen } from "@/composables/useWorkspaceAira"
import ContentLayout from "@/layouts/content-layout/index.vue"
import GlobalLayout from "@/layouts/global-layout/index.vue"
import { meetingDraftAvailability } from "@/service/api/meetings"
import { readOps } from "@/service/api/project-operations"
import { getProjectInfo } from "@/service/api/projects"
import { useAuthStore } from "@/store/modules/auth"
import { useInstanceStore } from "@/store/modules/instance"
import { useRouteStore } from "@/store/modules/route"

import { buildPublicProjectPath, buildSeoUrl } from "@/utils/seo"
import { $t } from "@airalogy/shared/locales"
import { computed, onMounted } from "vue"

import { LAB_OWNER_AND_MANAGER } from "../../composables/useLabPermissions"
import { meetingHandoffKey, meetingNameKey } from "../meetings/aira-handoff"
import AiraPanel from "../meetings/aira-panel.vue"
import { useProvideProjectInfoStore } from "../project-protocols/hooks/useProjectInfoStore"
import AddProtocolModal from "../project-protocols/modules/add-protocol-modal.vue"

defineOptions({
  name: "ProjectLayout",
})

withDefaults(defineProps<Props>(), {
  showPadding: false,
})

interface Props {
  /** Show padding for content */
  showPadding?: boolean
}

const route = useRoute()
const descriptionExpanded = ref(false)
const descriptionElement = ref<HTMLElement>()
const descriptionOverflow = ref(false)
function measureDescription() {
  const element = descriptionElement.value
  if (element && !descriptionExpanded.value)
    descriptionOverflow.value = element.scrollHeight > element.clientHeight + 1
}
useResizeObserver(descriptionElement, measureDescription)
watch(() => route.params.projectUid, () => descriptionExpanded.value = false)
const instanceStore = useInstanceStore()
const authStore = useAuthStore()
const showIcon = computed(
  () =>
    route.name === "lab-projects"
    || route.name === "lab-members"
    || route.name === "project-protocols"
    || route.name === "project-work"
    || route.name === "project-meetings"
    || route.name === "project-overview"
    || route.name === "project-documents"
    || route.name === "project-materials"
    || route.name === "project-knowledge"
    || route.name === "project-research"
    || route.name === "project-workflows"
    || route.name === "project-scenarios"
    || route.name === "project-analysis"
    || route.name === "project-records"
    || route.name === "project-operations"
    || route.name === "project-members"
    || route.name === "project-settings",
)

const { routerPushByKey, routerPush } = useRouterPush()
const { projectInfo } = useProvideProjectInfoStore(null)

const { canShowSettings: canShowProjectSettings, canCreateProtocol } = useProjectPermissions(projectInfo)
const canShowSettings = computed(() =>
  canShowProjectSettings.value || LAB_OWNER_AND_MANAGER.includes(projectInfo.value?.user_lab_role),
)

const router = useRouter()
const narrow = useAiraNarrowScreen()
const assistantOpen = ref(false)
const hasOpened = ref(false)
const meetingName = ref("")
provide(meetingNameKey, meetingName)
const assistantTrigger = ref<{ $el: HTMLElement }>()
const pendingProposal = ref<MeetingHandoff | null>(null)
provide(meetingHandoffKey, pendingProposal)
const assistantScope = computed(() => JSON.stringify([authStore.userInfo.id, route.params.labUid, route.params.projectUid]))
const assistantAvailable = ref(false)
const requestedChat = ref("")
const currentMeetingId = computed(() => route.name === "project-meetings" && typeof route.query.meeting === "string" && route.query.meeting !== "new" ? route.query.meeting : null)
const projectAssistant = computed(() => assistantAvailable.value || Boolean(requestedChat.value && projectInfo.value && authStore.isLogin))
let headerTrigger: HTMLElement | undefined
provide(projectAiraKey, {
  available: projectAssistant,
  visible: assistantOpen,
  open(trigger) {
    headerTrigger = trigger
    assistantOpen.value = true
  },
})
watch([assistantScope, () => projectInfo.value?.id, () => instanceStore.aiEnabled, () => authStore.isLogin], async (_, __, cleanup) => {
  const controller = new AbortController()
  cleanup(() => controller.abort())
  assistantAvailable.value = false
  const project = projectInfo.value
  const organizationUid = route.params.labUid || instanceStore.organization?.uid
  if (!authStore.isLogin || !instanceStore.aiEnabled || !project || project.uid !== route.params.projectUid || project.lab_uid !== organizationUid)
    return
  try {
    const status = await meetingDraftAvailability(project.id, controller.signal)
    if (!controller.signal.aborted)
      assistantAvailable.value = status.available
  }
  catch {
    // Opening the project does not require access to meeting drafting.
  }
}, { immediate: true })
watch([assistantScope, () => authStore.isLogin], () => {
  assistantOpen.value = false
  hasOpened.value = false
  pendingProposal.value = null
  meetingName.value = ""
  requestedChat.value = ""
})
watch([assistantScope, () => route.query.aira, () => authStore.isLogin], ([, id, signedIn]) => {
  if (signedIn && typeof id === "string" && /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(id)) {
    requestedChat.value = id
    hasOpened.value = true
    assistantOpen.value = true
  }
}, { immediate: true })
watch(assistantOpen, (open) => {
  if (open)
    hasOpened.value = true
})
function clearRequestedChat() {
  requestedChat.value = ""
  if (route.query.aira)
    void router.replace({ path: route.path, query: { ...route.query, aira: undefined }, hash: route.hash })
}
function closeAssistant() {
  assistantOpen.value = false
  nextTick(() => {
    (headerTrigger?.isConnected ? headerTrigger : assistantTrigger.value?.$el)?.focus({ preventScroll: true })
    headerTrigger = undefined
  })
}
async function reviewProposal(proposal: MeetingProposal) {
  if (!projectInfo.value)
    return
  const key = crypto.randomUUID()
  const previous = pendingProposal.value
  pendingProposal.value = { key, projectId: projectInfo.value.id, proposal }
  const failed = await router.push({ name: "project-meetings", params: route.params, query: { meeting: "new", draft: key } })
  if (failed) {
    if (pendingProposal.value?.key === key)
      pendingProposal.value = previous
  }
  else if (narrow.value) {
    assistantOpen.value = false
  }
}

const canManageOperations = computed(() => LAB_OWNER_AND_MANAGER.includes(projectInfo.value?.user_lab_role))
const canViewBook = ref(false)
const showOperations = computed(() => canViewBook.value || canManageOperations.value)
watch(() => [projectInfo.value?.id, authStore.userInfo.id] as const, async ([id], _, cleanup) => {
  let current = true
  cleanup(() => {
    current = false
  })
  canViewBook.value = false
  if (!id || !authStore.isLogin)
    return
  try {
    const result = await readOps<{ role: string | null }>(`/projects/${id}/access`)
    if (current)
      canViewBook.value = Boolean(result.role)
  }
  catch { /* Optional books stay hidden without access. */ }
}, { immediate: true })

const baseTabs = computed<(TabPaneProps & { name: App.Global.TabKey })[]>(() => {
  const tabs: (TabPaneProps & { name: App.Global.TabKey })[] = [
    { name: "project-protocols", tab: $t("page.project.tab.protocols") },
  ]

  if (authStore.isLogin) {
    tabs.unshift({ name: "project-overview", tab: $t("page.researchDocuments.overview") })
    tabs.push(
      { name: "project-work", tab: $t("page.project.tab.work") },
      { name: "project-meetings", tab: $t("page.meetings.title") },
      { name: "project-members", tab: $t("page.project.members") },
      { name: "project-documents", tab: $t("page.documentUx.documents") },
      { name: "project-materials", tab: $t("page.researchDocuments.materials") },
      { name: "project-knowledge", tab: $t("page.knowledge.title") },
      { name: "project-analysis", tab: $t("page.analysis.title") },
    )
    if (showOperations.value || route.name === "project-operations")
      tabs.push({ name: "project-operations", tab: $t("page.project.tab.operations") })
    const additional = [
      { name: "project-research", tab: $t("page.research.title") },
      { name: "project-workflows", tab: $t("page.workflowDefinitions.title") },
      { name: "project-scenarios", tab: $t("page.scenarioKits.workbench") },
      { name: "project-records", tab: $t("page.recordDiary.tab") },
      ...(canShowSettings.value ? [{ name: "project-settings", tab: $t("page.project.tab.settings") }] : []),
    ]
    const selected = additional.find(item => item.name === route.name)
    if (selected)
      tabs.push(selected as TabPaneProps & { name: App.Global.TabKey })
  }

  return tabs
})

const tabs = baseTabs
const workspaceNavigation = computed(() => [
  { key: "activity", type: "group", label: $t("page.researchDocuments.title"), children: [
    ...(showOperations.value ? [{ key: "project-operations", label: $t("page.project.tab.operations") }] : []),
    { key: "project-records", label: $t("page.recordDiary.tab") },
    { key: "project-scenarios", label: $t("page.scenarioKits.workbench") },
  ] },
  { key: "automation", type: "group", label: $t("page.researchDocuments.automation"), children: [
    { key: "project-research", label: $t("page.research.title") },
    { key: "project-workflows", label: $t("page.workflowDefinitions.title") },
    { key: "external-access", label: $t("externalResearch.connectProject") },
  ] },
  ...(canShowSettings.value
    ? [{ key: "management", type: "group", label: $t("page.researchDocuments.manage"), children: [
        { key: "project-settings", label: $t("page.project.tab.settings") },
      ] }]
    : []),
])
function navigateWorkspace(name: string) {
  if (name === "external-access") {
    void routerPush({ name: "project-analysis", params: { labUid: route.params.labUid, projectUid: route.params.projectUid }, query: { view: "external", connect: "1" } })
    return
  }
  void routerPushByKey(name as ProjectInfoNameKey, { params: { labUid: route.params.labUid as string, projectUid: route.params.projectUid as string } })
}

const projectTitle = computed(() => {
  const { name, uid } = projectInfo.value || {}

  return name || uid || "Project"
})

const { visibilityLabel, visibilityClass } = useProjectVisibility(() => projectInfo.value?.type, () => projectInfo.value?.organization_readable)

const description = computed(() => {
  return projectInfo.value?.description ?? ""
})

watch(description, measureDescription, { flush: "post" })

const publicProjectSeo = computed(() => {
  const info = projectInfo.value
  if (instanceStore.isSingleLab || !info || info.type !== 2 || route.name !== "project-protocols") {
    return null
  }

  const projectName = info.name || info.uid || "Project"
  const canonicalPath = buildPublicProjectPath({
    labUid: info.lab_uid,
    projectUid: info.uid,
  })
  const seoDescription = info.description?.trim()
    || `${projectName} is a public project on Airalogy for sharing protocols and reproducible research workflows.`
  const image = info.logo_url || "/images/project_placeholder.png"

  return {
    title: `${projectName} | Public Project | Airalogy`,
    description: seoDescription,
    canonical: canonicalPath,
    robots: "index,follow",
    ogType: "website" as const,
    image,
    modifiedTime: info.updated_at || null,
    jsonLd: {
      "@context": "https://schema.org",
      "@type": "CollectionPage",
      "name": projectName,
      "description": seoDescription,
      "url": buildSeoUrl(canonicalPath),
      "image": buildSeoUrl(image),
      "dateModified": info.updated_at || undefined,
      "isPartOf": {
        "@type": "WebSite",
        "name": "Airalogy",
        "url": buildSeoUrl("/"),
      },
    },
  }
})

useSeoMeta(publicProjectSeo)

function handleAddProtocol(payload: {
  id: string
  uid: string
  labUid: string
  labId: string
  projectUid: string
  name: string
}) {
  const { uid, projectUid, labUid } = payload
  void routerPushByKey("protocol-info", {
    params: {
      labUid,
      protocolUid: uid,
      projectUid,
    },
  })
}

const routerStore = useRouteStore()

async function setBreadcrumbs(info?: Api.Project.MyProjectInfo | null) {
  if (!info) {
    return
  }

  const { setDynamicBreadcrumbs } = routerStore

  const { lab_uid: labUid, uid: projectUid, parent_project_uid: parentProjectUid, parent_project_name: parentProjectName } = info || {}

  const breadcrumbs: any[] = [
    {
      breadcrumbLabel: labUid || "",
      key: "",
      label: labUid || "",
      routeKey: "lab" as App.Global.RouteKey,
      routePath: "/lab",
      to: authStore.isLogin
        ? {
            name: "lab-projects",
            params: { labUid },
          }
        : undefined,
    },
  ]

  if (parentProjectUid) {
    breadcrumbs.push({
      breadcrumbLabel: parentProjectName || parentProjectUid,
      key: "",
      label: parentProjectName || parentProjectUid,
      routeKey: "project-protocols" as App.Global.RouteKey,
      routePath: "/project",
      to: {
        name: "project-protocols",
        params: { labUid, projectUid: parentProjectUid },
      },
    })
  }

  breadcrumbs.push(
    {
      breadcrumbLabel: info.name || projectUid || "",
      key: "",
      label: info.name || projectUid || "",
      routeKey: "project-protocols" as App.Global.RouteKey,
      routePath: "/project",
      options: [
        {
          key: "project-protocols",
          label: "Project protocols",
          i18nKey: "page.project.protocols",
        },
        {
          key: "project-research",
          label: "Project research",
          i18nKey: "page.research.title",
          breadcrumbLabel: "Project research",
        },
        {
          key: "project-workflows",
          label: "Project workflows",
          i18nKey: "page.workflowDefinitions.title",
          breadcrumbLabel: "Project workflows",
        },
        {
          key: "project-analysis",
          label: "Project analysis",
          i18nKey: "page.analysis.title",
          breadcrumbLabel: "Project analysis",
        },
        {
          key: "project-records",
          label: "Project records",
          i18nKey: "page.recordDiary.tab",
          breadcrumbLabel: "Project records",
        },
        {
          key: "project-members",
          label: "Project members",
          i18nKey: "page.project.members",
          breadcrumbLabel: "Project members",
        },
      ],
    },
  )

  setDynamicBreadcrumbs(breadcrumbs)
}

const { failure, loading: loadingProject, retry } = useResourcePage(
  () => [route.params.labUid, route.params.projectUid].join("/"),
  async (signal) => {
    const { labUid, projectUid } = route.params as Record<string, string>
    const info = await getProjectInfo({ labUid, projectUid }, signal)
    if (!info)
      throw new Error("Empty project response")
    return info
  },
  (info) => {
    projectInfo.value = info
    if (info)
      void setBreadcrumbs(info)
    else
      routerStore.setDynamicBreadcrumbs([])
  },
)

onUnmounted(() => {
  const { setDynamicBreadcrumbs } = routerStore
  setDynamicBreadcrumbs([])
})
</script>
