<template>
  <div data-testid="home-workspace" class="my-6 min-w-0 lg:my-8 space-y-6">
    <getting-started-card />
    <main data-testid="home-work" class="min-w-0">
      <task-workbench :pins="pinnedItems" :pinning-keys="pinningKeys" @toggle-pin="handleTogglePin" />
    </main>
    <section data-testid="home-resources" class="border border-gray-200 rounded-xl bg-gray-50 p-4">
      <nav class="flex flex-wrap items-center gap-x-6 gap-y-3" :aria-label="$t('page.home.workspace.resources')">
        <span class="aira-type-label">{{ $t('page.home.workspace.resources') }}</span>
        <router-link v-for="entry in resourceEntries" :key="entry.name" :to="{ name: entry.name, params: entry.params }" class="text-primary hover:underline">
          {{ $t(entry.label) }}
        </router-link>
      </nav>
      <details class="mt-4">
        <summary class="cursor-pointer text-gray-600">
          {{ $t('page.home.workspace.pinnedResources') }}
        </summary>
        <pinned-items class="mt-3" :items="pinnedItems" :loading="pinnedLoading" :pinning-keys="pinningKeys" :max-count="maxPinnedCount" :hide-projects="true" @toggle-pin="handleTogglePin" @reorder-pinned="handleReorderPinned" />
      </details>
    </section>
    <details v-if="loading || totalCount > 0" class="min-w-0" data-testid="home-activity">
      <summary class="aira-type-card-title mb-3 cursor-pointer">
        {{ $t('page.home.activities') }}
      </summary>
      <n-spin :show="loading" class="min-h-20">
        <activity-card v-for="item in activityList" :key="item.id" v-bind="item" :loading="loading && totalCount === 0" />
        <n-button v-if="hasMore" :loading="loading" class="mt-4 w-full" @click="handleLoadMore">
          {{ $t('page.home.loadMore') }}
        </n-button>
      </n-spin>
    </details>
    <testing-notification-dialog v-if="!instanceStore.isSingleLab" v-model:show="showTestingDialog" @get-started="handleGetStarted" @dismiss="handleDismissDialog" />
  </div>
</template>

<script setup lang="ts">
import { useOrganizationTranslation } from "@/composables/useOrganizationTranslation"
import { getActivities } from "@/service/api/activities"
import {
  createPinnedItem,
  deletePinnedItem,
  getPinnedItems,
  type PinnedItem,
  PinnedResourceType,
  reorderPinnedItems,
} from "@/service/api/pinned-items"
import { getProtocolInfo } from "@/service/api/protocol"

import { useAuthStore } from "@/store/modules/auth"
import { useInstanceStore } from "@/store/modules/instance"
import { singleLabSharedEntries } from "@/utils/singleLabWorkspace"

import TestingNotificationDialog from "@/views/auth/components/testing-notification-dialog.vue"
import { useClosableMessage, useLoading } from "@airalogy/composables"
import ActivityCard, { type IProps as ICardItem } from "./components/activity-card.vue"
import GettingStartedCard from "./components/getting-started-card.vue"
import PinnedItems from "./components/pinned-items.vue"
import TaskWorkbench from "./components/task-workbench.vue"

const { t: $t } = useOrganizationTranslation()

const authStore = useAuthStore()
const instanceStore = useInstanceStore()

const resourceEntries = computed(() => [
  ...(instanceStore.isSingleLab && instanceStore.lab
    ? singleLabSharedEntries.map(entry => ({ ...entry, params: { labUid: instanceStore.lab!.uid } }))
    : [{ name: "labs-my", label: "common.labs" }]),
  { name: "protocols-my", label: "page.home.workspace.section.protocols" },
  { name: "knowledge-home", label: instanceStore.isSingleLab ? "page.knowledge.myKnowledge" : "page.home.workspace.section.knowledge" },
  { name: "research-tasks", label: "page.research.title" },
] as { name: App.Global.RouteNameKey, label: I18n.I18nKey, params?: { labUid: string } }[])

const { loading, startLoading, endLoading } = useLoading()
const {
  loading: pinnedLoading,
  startLoading: startPinnedLoading,
  endLoading: endPinnedLoading,
} = useLoading(true)
const message = useClosableMessage()

const activityRecord = ref<
  Record<"records" | "labs" | "projects" | "groups", Api.Activity.ActivityItem[]>
>({
  records: [],
  labs: [],
  projects: [],
  groups: [],
})
const totalCount = computed(() =>
  Object.values(activityRecord.value).reduce((acc, curr) => acc + curr.length, 0),
)

const currentPage = ref(1)
const pageSize = ref(5)
const hasMore = ref(true)

const maxPinnedCount = 10
const pinnedItems = ref<PinnedItem[]>([])
const pinningKeys = ref(new Set<string>())

const pinnedMap = computed(() => {
  const map = new Map<string, PinnedItem>()
  pinnedItems.value.forEach((item) => {
    map.set(`${item.resource_type}:${item.resource_id}`, item)
  })
  return map
})

type ActivityCategory = "projects" | "labs" | "records" | "protocols" | "groups"

function getLocalizedActivityAction(action: string) {
  const normalizedAction = action.trim().toLowerCase()

  switch (normalizedAction) {
    case "added":
      return $t("page.home.activityAction.added")
    case "created":
      return $t("page.home.activityAction.created")
    case "updated":
      return $t("page.home.activityAction.updated")
    case "deleted":
      return $t("page.home.activityAction.deleted")
    case "joined":
      return $t("page.home.activityAction.joined")
    case "left":
      return $t("page.home.activityAction.left")
    default:
      return action
  }
}

function getActivityText(key: ActivityCategory, action: string) {
  switch (key) {
    case "projects":
      return $t("page.home.activityText.project", {
        action: getLocalizedActivityAction(action),
      })
    case "labs":
      return $t("page.home.activityText.lab", {
        action: getLocalizedActivityAction(action),
      })
    case "records":
      return $t("page.home.activityText.record")
    case "protocols":
      return $t("page.home.activityText.protocol")
    case "groups":
      return $t("page.home.activityText.group", {
        action: getLocalizedActivityAction(action),
      })
    default:
      return action
  }
}

const activityList = computed((): ICardItem[] => {
  const entries = Object.entries(activityRecord.value)
  const list = entries
    .map(([key, val]) =>
      val.map((it): ICardItem => {
        const {
          lab,
          project,
          record,
          group,
          node,
          action,
          created_at,
          id,
          description,
          uid,
          name,
          protocol,
        } = it

        const activity = getActivityText(key as ActivityCategory, action)

        return {
          activity,
          project: key === "projects" ? { id, uid, name } : project,
          lab: key === "labs" ? { id, uid, name } : lab,
          record,
          protocol,
          group,
          node,
          time: created_at,
          id: `${key}-${id}`,
          user: authStore.userInfo,
          description,
        }
      }),
    )
    .flat()

  return list.sort((a, b) => new Date(b.time).getTime() - new Date(a.time).getTime())
})

async function handleLoadMore() {
  currentPage.value++
  await fetchData({
    currentPage: currentPage.value,
    currentPageSize: pageSize.value,
    isLoadMore: true,
  })
}

async function fetchData({
  currentPage: currPage,
  currentPageSize: currSize,
  isLoadMore = false,
}: {
  currentPage: number
  currentPageSize: number
  isLoadMore?: boolean
}) {
  try {
    startLoading()

    const { data, error } = await getActivities({
      userId: authStore.userInfo.id,
      page: currPage,
      pageSize: currSize,
    })

    if (data) {
      // If loading more, append to existing data
      if (isLoadMore) {
        Object.keys(data).forEach((key) => {
          const typedKey = key as keyof typeof activityRecord.value
          activityRecord.value[typedKey] = [...activityRecord.value[typedKey], ...data[typedKey]]
        })
      }
      else {
        activityRecord.value = data
      }

      // Check if we have more data to load
      const newItemsCount = Object.values(data).reduce((acc, curr) => acc + curr.length, 0)
      hasMore.value = newItemsCount === currSize
    }
    else if (error) {
      if (isLoadMore)
        currentPage.value--
    }
  }
  catch (error) {
    if (isLoadMore)
      currentPage.value--
  }
  finally {
    endLoading()
  }
}

async function fetchPinnedItems() {
  startPinnedLoading()
  try {
    const { data, error } = await getPinnedItems()
    if (data) {
      const items = data.items || []
      const protocolItems = items.filter(item => item.resource_type === PinnedResourceType.Protocol)
      if (protocolItems.length > 0) {
        const results = await Promise.allSettled(
          protocolItems.map(item => getProtocolInfo(item.resource_id)),
        )
        results.forEach((result, index) => {
          if (result.status === "fulfilled" && result.value.data) {
            protocolItems[index]!.resource = result.value.data
          }
        })
      }
      pinnedItems.value = items
    }
    else if (error) {
      message.error("Failed to load pinned items")
    }
  }
  catch {
    message.error("Failed to load pinned items")
  }
  finally {
    endPinnedLoading()
  }
}

async function handleTogglePin(payload: { resourceType: PinnedResourceType, resourceId: string }) {
  const { resourceType, resourceId } = payload
  if (!resourceId) {
    return
  }

  const key = `${resourceType}:${resourceId}`
  if (pinningKeys.value.has(key)) {
    return
  }

  pinningKeys.value.add(key)
  try {
    const existing = pinnedMap.value.get(key)
    if (existing) {
      await deletePinnedItem(existing.id)
    }
    else {
      await createPinnedItem({ resource_type: resourceType, resource_id: resourceId })
    }
    await fetchPinnedItems()
  }
  finally {
    pinningKeys.value.delete(key)
  }
}

async function handleReorderPinned(pinnedItemIds: number[]) {
  if (!Array.isArray(pinnedItemIds) || pinnedItemIds.length === 0) {
    return
  }

  // The compact list excludes project pins; keep them and their ordering intact.
  const ordered = [...pinnedItemIds]
  pinnedItemIds = pinnedItems.value.map(item => (item.resource_type === PinnedResourceType.Project || (instanceStore.isSingleLab && item.resource_type === PinnedResourceType.Lab)) ? item.id : ordered.shift()!).filter(id => id !== undefined)
  const itemMap = new Map(pinnedItems.value.map(item => [item.id, item]))
  const nextItems = pinnedItemIds.map(id => itemMap.get(id)).filter(Boolean) as PinnedItem[]
  if (nextItems.length > 0) {
    pinnedItems.value = nextItems
  }

  try {
    await reorderPinnedItems(pinnedItemIds)
  }
  catch {
    message.error("Failed to reorder pinned items")
    await fetchPinnedItems()
  }
}

// Testing notification dialog state
const showTestingDialog = ref(false)
const hasShownTestingDialog = ref(false)

// Handle testing dialog actions
function handleGetStarted() {
  // Clear the signup flag and allow natural navigation
  authStore.clearSignupFlag()
  hasShownTestingDialog.value = true
}

function handleDismissDialog() {
  // Clear the signup flag and allow natural navigation
  authStore.clearSignupFlag()
  hasShownTestingDialog.value = true
}

onMounted(async () => {
  await Promise.all([
    fetchPinnedItems(),
    fetchData({ currentPage: currentPage.value, currentPageSize: pageSize.value }),
  ])
})

// Also watch for auth state changes in case user navigates between pages
watch(
  () => authStore.justSignedUp,
  (newValue) => {
    if (newValue && !hasShownTestingDialog.value && !loading.value) {
      showTestingDialog.value = true
      hasShownTestingDialog.value = true
    }
  },
  { immediate: true },
)
</script>
