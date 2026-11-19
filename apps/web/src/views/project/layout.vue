<template>
  <global-layout>
    <div class="project-shell" :class="{ 'with-assistant': assistantOpen && assistantAvailable }">
      <div class="min-w-0">
        <content-layout :title="projectTitle" :tabs="tabs" compact-header>
          <template v-if="authStore.isLogin" #suffix>
            <div class="flex flex-wrap items-center justify-end gap-2">
              <n-button v-if="assistantAvailable" ref="assistantTrigger" size="small" :aria-expanded="assistantOpen" data-testid="project-aira" @click="headerTrigger = undefined; assistantOpen = !assistantOpen">Aira</n-button>
              <n-dropdown trigger="click" :options="workspaceNavigation" @select="navigateWorkspace">
                <n-button>{{ $t('common.more') }}</n-button>
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
                  <p v-if="description" ref="descriptionElement" class="mb-0 mt-1 text-sm leading-5 color-text-secondary" :class="{ 'line-clamp-2': !descriptionExpanded }" data-testid="project-description">
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
      </div>
      <dialog v-if="assistantAvailable && hasOpened && projectInfo" ref="assistantDialog" class="project-assistant" :aria-label="$t('page.projectAira.panel')" @cancel.prevent="closeAssistant">
        <aira-panel :key="assistantScope" :project-id="projectInfo.id" :project-name="projectTitle" @close="closeAssistant" @review="reviewProposal" />
      </dialog>
    </div>
  </global-layout>
</template>

<script setup lang="ts">
import type { ProjectInfoNameKey } from "#/page-route"
import type { MeetingProposal } from "@/service/api/meetings"
import type { TabPaneProps } from "naive-ui/es/tabs"
import type { MeetingHandoff } from "../meetings/aira-handoff"
import { useProjectPermissions } from "@/composables"
import { useProjectVisibility } from "@/composables/useProjectVisibility"
import { useRouterPush } from "@/composables/useRouterPush"
import { useSeoMeta } from "@/composables/useSeoMeta"
import { projectAiraKey } from "@/composables/useWorkspaceAira"
import ContentLayout from "@/layouts/content-layout/index.vue"
import GlobalLayout from "@/layouts/global-layout/index.vue"
import { meetingDraftAvailability } from "@/service/api/meetings"
import { useAppStore } from "@/store/modules/app"
import { useAuthStore } from "@/store/modules/auth"
import { useInstanceStore } from "@/store/modules/instance"
import { useRouteStore } from "@/store/modules/route"

import { buildPublicProjectPath, buildSeoUrl } from "@/utils/seo"
import { $t } from "@airalogy/shared/locales"
import { useMediaQuery } from "@vueuse/core"
import { computed, onMounted } from "vue"

import { LAB_OWNER_AND_MANAGER } from "../../composables/useLabPermissions"
import { meetingHandoffKey } from "../meetings/aira-handoff"
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
    || route.name === "project-members"
    || route.name === "project-settings",
)

const { routerPushByKey, routerPush } = useRouterPush()
const { fetchProjectInfo, refetchProjectInfo, projectInfo } = useProvideProjectInfoStore(null)

const { canShowSettings: canShowProjectSettings, canCreateProtocol } = useProjectPermissions(projectInfo)
const canShowSettings = computed(() =>
  canShowProjectSettings.value || LAB_OWNER_AND_MANAGER.includes(projectInfo.value?.user_lab_role),
)

const router = useRouter()
const narrow = useMediaQuery("(max-width: 899px)")
const assistantOpen = ref(false)
const hasOpened = ref(false)
const assistantDialog = ref<HTMLDialogElement>()
const assistantTrigger = ref<{ $el: HTMLElement }>()
const pendingProposal = ref<MeetingHandoff | null>(null)
provide(meetingHandoffKey, pendingProposal)
const assistantScope = computed(() => JSON.stringify([authStore.userInfo.id, route.params.labUid, route.params.projectUid]))
const assistantAvailable = ref(false)
let headerTrigger: HTMLElement | undefined
provide(projectAiraKey, {
  available: assistantAvailable,
  open(trigger) {
    headerTrigger = trigger
    assistantOpen.value = true
  },
})
watch(() => [assistantScope.value, projectInfo.value?.id, instanceStore.aiEnabled, authStore.isLogin] as const, async (_, __, cleanup) => {
  let current = true
  cleanup(() => {
    current = false
  })
  assistantAvailable.value = false
  const project = projectInfo.value
  const organizationUid = route.params.labUid || instanceStore.organization?.uid
  if (!authStore.isLogin || !instanceStore.aiEnabled || !project || project.uid !== route.params.projectUid || project.lab_uid !== organizationUid)
    return
  try {
    const status = await meetingDraftAvailability(project.id)
    if (current)
      assistantAvailable.value = status.available
  }
  catch {
    // Opening the project does not require access to meeting drafting.
  }
}, { immediate: true })
watch(assistantScope, () => {
  assistantOpen.value = false
  hasOpened.value = false
  pendingProposal.value = null
})
watch(assistantOpen, (open) => {
  if (open)
    hasOpened.value = true
})
watch([assistantDialog, assistantOpen, narrow], ([element, open, modal]) => {
  if (!element)
    return
  if (element.open)
    element.close()
  if (open) {
    if (modal)
      element.showModal()
    else element.show()
  }
}, { flush: "post" })
function closeAssistant() {
  assistantOpen.value = false
  nextTick(() => {
    (headerTrigger?.isConnected ? headerTrigger : assistantTrigger.value?.$el)?.focus()
    headerTrigger = undefined
  })
}
async function reviewProposal(proposal: MeetingProposal) {
  if (!projectInfo.value)
    return
  const key = crypto.randomUUID()
  pendingProposal.value = { key, projectId: projectInfo.value.id, proposal }
  const failed = await router.push({ name: "project-meetings", params: route.params, query: { meeting: "new", draft: key } })
  if (!failed) {
    assistantOpen.value = false
    hasOpened.value = false
  }
}

const baseTabs = computed<(TabPaneProps & { name: App.Global.TabKey })[]>(() => {
  const tabs: (TabPaneProps & { name: App.Global.TabKey })[] = [
    { name: "project-protocols", tab: $t("page.project.tab.protocols") },
  ]

  if (authStore.isLogin) {
    tabs.unshift({ name: "project-overview", tab: $t("page.researchDocuments.overview") })
    tabs.push(
      { name: "project-work", tab: $t("page.projectWork.title") },
      { name: "project-meetings", tab: $t("page.meetings.title") },
      { name: "project-members", tab: $t("page.project.members") },
      { name: "project-documents", tab: $t("page.documentUx.documents") },
      { name: "project-materials", tab: $t("page.researchDocuments.materials") },
      { name: "project-knowledge", tab: $t("page.knowledge.title") },
      { name: "project-analysis", tab: $t("page.analysis.title") },
    )
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

const { visibilityLabel, visibilityClass } = useProjectVisibility(() => projectInfo.value?.type)

const description = computed(() => {
  return projectInfo.value?.description ?? ""
})

watch(description, measureDescription, { flush: "post" })

const publicProjectSeo = computed(() => {
  const info = projectInfo.value
  if (!info || route.name !== "project-protocols") {
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

const { reloadPage } = useAppStore()

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

async function handleEditProject() {
  const { labUid, projectUid } = route.params

  const currProjectInfo = await refetchProjectInfo(0, {
    labUid: labUid as string,
    projectUid: projectUid as string,
  })

  if (currProjectInfo) {
    projectInfo.value = currProjectInfo
  }
  else {
    routerPushByKey("project-not-found")
  }

  await nextTick(async () => {
    await setBreadcrumbs()
    await reloadPage(10)
  })
}

// Moving between tabs cancels requests belonging to the previous route. Until the
// project has loaded, each new tab must be able to finish its own lookup.
watch(
  [() => route.params.labUid, () => route.params.projectUid, () => route.name],
  async ([labUid, projectUid], _, onCleanup) => {
    if (typeof labUid !== "string" || typeof projectUid !== "string")
      return
    if (projectInfo.value?.lab_uid === labUid && projectInfo.value.uid === projectUid)
      return

    let current = true
    onCleanup(() => {
      current = false
    })
    projectInfo.value = null
    const info = await fetchProjectInfo({ labUid, projectUid })
    if (!current)
      return
    if (info) {
      projectInfo.value = info
      await setBreadcrumbs(info)
    }
    else {
      await routerPushByKey("project-not-found")
    }
  },
  { immediate: true },
)

onUnmounted(() => {
  const { setDynamicBreadcrumbs } = routerStore
  setDynamicBreadcrumbs([])
})
</script>

<style scoped>
.project-assistant { position: sticky; top: 16px; width: 100%; min-width: 0; max-width: none; max-height: none; padding: 0; margin: 0; border: 0; background: white; }
@media (max-width: 899px) {
  .project-assistant { position: fixed; inset: 0 0 0 auto; width: min(420px, 100%); height: 100dvh; }
  .project-assistant::backdrop { background: rgb(20 30 48 / 25%); }
}
@media (max-width: 599px) { .project-assistant { width: 100%; } }
@media (min-width: 900px) {
  .project-shell.with-assistant { display: grid; grid-template-columns: minmax(0, 1fr) clamp(320px, 30vw, 440px); align-items: start; gap: 20px; }
}
</style>
