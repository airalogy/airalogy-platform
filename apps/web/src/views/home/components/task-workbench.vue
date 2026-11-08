<script setup lang="ts">
import type { PinnedItem, PinnedResourceType } from "@/service/api/pinned-items"
import { recentResearchDocuments } from "@/service/api/research-documents"
import {
  fetchResearchApprovals,
  fetchResearchTasks,
  fetchResearchWorkItems,
  type ResearchApprovalDetail,
  type ResearchTaskSummary,
  type ResearchWorkItemDetail,
  startResearchWorkItem,
} from "@/service/api/research-tasks"
import { useAuthStore } from "@/store/modules/auth"
import { useInstanceStore } from "@/store/modules/instance"
import ResearchApprovalActions from "@/views/research/components/research-approval-actions.vue"
import { useI18n } from "vue-i18n"
import { useRouter } from "vue-router"
import ProjectWorkspaces from "./project-workspaces.vue"

defineProps<{ pins: PinnedItem[], pinningKeys: Set<string> }>()
const emit = defineEmits<{ togglePin: [payload: { resourceType: PinnedResourceType, resourceId: string }] }>()
const authStore = useAuthStore()
const instanceStore = useInstanceStore()
const router = useRouter()
const { t } = useI18n()
const displayName = computed(() => authStore.userInfo.name || authStore.userInfo.username)
const loading = ref(true)
const loadError = ref(false)
const documentError = ref(false)
const recentDocuments = ref<Awaited<ReturnType<typeof recentResearchDocuments>>["items"]>([])
const researchTasks = ref<ResearchTaskSummary[]>([])
const researchWorkItems = ref<ResearchWorkItemDetail[]>([])
const researchApprovals = ref<ResearchApprovalDetail[]>([])
const attentionCount = ref(0)
let sequence = 0

async function loadWorkbench() {
  const current = ++sequence
  const userId = authStore.userInfo.id
  if (!userId)
    return
  loading.value = true
  loadError.value = false
  documentError.value = false
  recentDocuments.value = []
  researchTasks.value = []
  researchWorkItems.value = []
  researchApprovals.value = []
  const [tasks, work, approvals, documents] = await Promise.allSettled([
    fetchResearchTasks({ page: 1, pageSize: 3, status: ["review_required"] }),
    fetchResearchWorkItems({ page: 1, pageSize: 3 }),
    fetchResearchApprovals({ page: 1, pageSize: 3 }),
    recentResearchDocuments("personal"),
  ])
  if (current !== sequence || userId !== authStore.userInfo.id)
    return
  if (tasks.status === "fulfilled" && work.status === "fulfilled" && approvals.status === "fulfilled") {
    researchTasks.value = tasks.value.tasks
    researchWorkItems.value = work.value.work_items
    researchApprovals.value = approvals.value.approvals
    attentionCount.value = tasks.value.total_count + work.value.total_count + approvals.value.total_count
  }
  else {
    loadError.value = true
  }
  if (documents.status === "fulfilled")
    recentDocuments.value = documents.value.items
  else
    documentError.value = true
  loading.value = false
}

async function executeResearchWork(item: ResearchWorkItemDetail) {
  if (item.action.kind === "human_work_item") {
    await router.push({ name: "research-work-item-detail", params: { workItemId: item.id } })
    return
  }
  const protocol = item.action.protocol
  if (!protocol) {
    await router.push({ name: "research-task-detail", params: { taskId: item.task.id } })
    return
  }
  if (["open", "changes_requested"].includes(item.status))
    await startResearchWorkItem(item.id, item.revision)
  await router.push({
    name: "add-protocol-record",
    params: { labUid: protocol.lab_uid || item.lab.uid, projectUid: protocol.project_uid || item.project.uid, protocolUid: protocol.uid },
    query: { researchWorkItem: item.id },
  })
}
watch(() => authStore.userInfo.id, loadWorkbench, { immediate: true })
onBeforeUnmount(() => sequence++)
</script>

<template>
  <section data-testid="task-workbench" class="space-y-6">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div class="min-w-0">
        <h1 class="aira-type-page-title m-0 break-words">
          {{ t('page.home.workbench.title', { name: displayName }) }}
        </h1>
        <p class="aira-type-body aira-text-muted mb-0 mt-2">
          {{ t('page.home.workspace.description') }}
        </p>
      </div>
      <n-button v-if="instanceStore.aiEnabled" secondary type="primary" data-testid="home-aira" @click="router.push({ name: 'global-chat' })">
        {{ t('page.home.workspace.askAira') }}
      </n-button>
    </div>
    <project-workspaces :pins="pins" :pinning-keys="pinningKeys" @toggle-pin="emit('togglePin', $event)" />
    <div class="grid min-w-0 gap-4 lg:grid-cols-2">
      <section class="min-w-0 border border-gray-200 rounded-xl p-4" data-testid="home-attention-panel">
        <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 class="aira-type-card-title m-0">
            {{ t('page.home.workbench.attentionLabel') }}<span v-if="!loadError && !loading && attentionCount" class="ml-2 text-primary">{{ attentionCount }}</span>
          </h2>
          <router-link :to="{ name: 'research-tasks' }" class="text-primary hover:underline">
            {{ t('page.research.title') }} →
          </router-link>
        </div>
        <n-skeleton v-if="loading" text :repeat="2" />
        <n-alert v-else-if="loadError" type="error" :title="t('page.home.workbench.loadError')">
          <n-button size="small" @click="loadWorkbench">
            {{ t('common.retry') }}
          </n-button>
        </n-alert>
        <div v-else-if="attentionCount" class="space-y-3" data-testid="workbench-attention">
          <div v-for="item in researchWorkItems" :key="item.id" class="workbench-task">
            <div class="min-w-0 flex-1">
              <p class="aira-type-label m-0 break-words">
                {{ item.action.title }}
              </p>
              <p class="aira-type-meta mb-0 mt-1 break-words">
                {{ item.project.name }} · {{ item.task.title }}
              </p>
            </div>
            <n-button size="small" secondary @click="executeResearchWork(item)">
              {{ t('page.home.workspace.handle') }}
            </n-button>
          </div>
          <div v-for="item in researchApprovals" :key="item.id" class="workbench-task">
            <div class="min-w-0 flex-1">
              <router-link :to="{ name: 'research-task-detail', params: { taskId: item.task.id } }" class="aira-type-label break-words hover:text-primary">
                {{ item.action.title }}
              </router-link>
              <p class="aira-type-meta mb-0 mt-1">
                {{ t('page.research.approvalRequired') }} · {{ item.project.name }}
              </p>
            </div>
            <research-approval-actions :approval="item" :action-revision="item.action.revision" @decided="loadWorkbench" />
          </div>
          <div v-for="item in researchTasks" :key="item.id" class="workbench-task">
            <div class="min-w-0 flex-1">
              <p class="aira-type-label m-0 break-words">
                {{ item.title }}
              </p>
              <p class="aira-type-meta mb-0 mt-1">
                {{ t('page.research.reviewResult') }} · {{ item.project.name }}
              </p>
            </div>
            <n-button size="small" secondary @click="router.push({ name: 'research-task-detail', params: { taskId: item.id } })">
              {{ t('page.home.workspace.handle') }}
            </n-button>
          </div>
        </div>
        <p v-else class="aira-type-meta mb-0" data-testid="workbench-clear">
          {{ t('page.home.workspace.noAttention') }}
        </p>
      </section>
      <section class="min-w-0 border border-gray-200 rounded-xl p-4" data-testid="home-recent-documents">
        <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 class="aira-type-card-title m-0">
            {{ t('page.home.workspace.personalDocuments') }}
          </h2>
          <router-link :to="{ name: 'research-documents' }" class="text-primary hover:underline">
            {{ t('page.home.workspace.openPersonal') }} →
          </router-link>
        </div>
        <p class="aira-type-meta mb-3 mt-0">
          {{ t('page.home.workspace.personalHint') }}
        </p>
        <n-skeleton v-if="loading" text :repeat="2" />
        <n-alert v-else-if="documentError" type="error" :title="t('page.home.workspace.documentsError')">
          <n-button size="small" @click="loadWorkbench">
            {{ t('common.retry') }}
          </n-button>
        </n-alert>
        <div v-else-if="recentDocuments.length" class="space-y-2">
          <div v-for="item in recentDocuments.slice(0, 3)" :key="item.id" class="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
            <router-link :to="{ name: 'research-document-detail', params: { documentId: item.id } }" class="min-w-0 break-words text-primary hover:underline">
              {{ item.title }}
            </router-link>
            <span class="aira-type-meta"><n-time :time="new Date(item.updated_at)" type="relative" /></span>
          </div>
        </div>
        <p v-else class="aira-type-body m-0">
          {{ t('page.home.workspace.personalEmpty') }}
        </p>
      </section>
    </div>
  </section>
</template>

<style scoped>
.workbench-task { display: flex; flex-wrap: wrap; align-items: center; gap: 0.75rem; border-top: 1px solid #edf0f4; padding-top: 0.75rem; }
.workbench-task:first-child { border-top: 0; padding-top: 0; }
</style>
