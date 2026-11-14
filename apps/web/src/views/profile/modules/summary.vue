<template>
  <div class="size-full" data-testid="profile-summary">
    <define-summary-item v-slot="{ count, label }">
      <div
        class="min-w-[120px] flex flex-col items-center rounded text-xl font-semibold transition-colors hover:bg-gray-50"
      >
        <!-- <n-number-animation :from="0" :to="count" /> -->
        <div>{{ count }}</div>
        <div class="mt-2 text-sm text-gray-600 font-normal">
          {{ label }}
        </div>
      </div>
    </define-summary-item>

    <define-wrapper-item v-slot="{ $slots, title, handleViewAll, contentClass, showViewAll }">
      <div class="mb-4">
        <div class="mb-4 flex items-center gap-2 text-lg font-medium">
          {{ title }}
          <n-button
            v-if="showViewAll && handleViewAll"
            quaternary
            icon-placement="right"
            size="small"
            class="ml-1"
            @click="handleViewAll"
          >
            {{ $t("common.viewAll") }}
            <template #icon>
              <n-icon size="12">
                <icon-ion-ios-arrow-forward />
              </n-icon>
            </template>
          </n-button>
        </div>
        <n-card class="w-full" size="small" :content-class="contentClass || '!p-1' ">
          <component :is="$slots.default" />
        </n-card>
      </div>
    </define-wrapper-item>

    <div class="size-full" v-bind="$attrs">
      <div v-if="singleOrganizationMembership" class="mb-4 flex flex-wrap items-center gap-2" data-testid="profile-organization">
        <span class="text-gray-500">{{ $t(instanceStore.usesOrganizationVocabulary ? "page.profile.organizationMembership" : "page.profile.labMembership") }}</span>
        <span class="min-w-0 break-words font-medium">{{ singleOrganizationMembership.name }}</span>
        <global-role-tag :item="singleOrganizationMembership" type="lab" />
      </div>

      <wrapper-item :title="$t('page.profile.summary')" content-class="!p-4">
        <div class="flex flex-wrap justify-center gap-2 sm:justify-start" data-testid="profile-statistics">
          <summary-item v-for="key in countKey" :key="key" v-bind="countRecord[key]" />
        </div>
      </wrapper-item>

      <wrapper-item
        v-if="!instanceStore.isSingleOrganization && userLabCount > 0 && userLabList.length > 0"
        :title="$t('page.profile.organizations')"
        :handle-view-all="handleViewAllLabs"
        :show-view-all="viewAllState.lab === true"
      >
        <lab-list data-testid="profile-organizations" :list="viewAllState.lab ? userLabList.slice(0, 5) : userLabList " :show-actions="false" :show-private="showPrivate" />
      </wrapper-item>

      <wrapper-item
        v-if="!instanceStore.isStructuredLab && userGroupCount > 0 && userGroupList.length > 0"
        :title="$t('page.profile.groups')"
        :handle-view-all="handleViewAllGroups"
        :show-view-all="viewAllState.group === true"
      >
        <lab-group-list :list="viewAllState.group ? userGroupList.slice(0, 5) : userGroupList" :show-actions="false" :show-private="showPrivate" />
      </wrapper-item>

      <wrapper-item
        v-if="userProjectCount > 0 && userProjectList.length > 0"
        :title="$t('common.projectsLabel')"
        :handle-view-all="handleViewAllProjects"
        :show-view-all="viewAllState.project === true"
      >
        <project-list data-testid="profile-projects" :list="viewAllState.project ? userProjectList.slice(0, 5) : userProjectList" :show-actions="false" :show-private="showPrivate" />
      </wrapper-item>

      <wrapper-item
        v-if="userProtocolCount > 0 && userProtocolList.length > 0"
        :title="$t('page.profile.protocols')"
        :handle-view-all="handleViewAllProtocols"
        :show-view-all="viewAllState.protocol === true"
      >
        <project-protocol-list :list="viewAllState.protocol ? userProtocolList.slice(0, 5) : userProtocolList" :show-actions="false" :show-private="showPrivate" show-context />
      </wrapper-item>
    </div>
  </div>
</template>

<script lang="ts" setup>
import { useAuthStore } from "@/store/modules/auth"
import { useInstanceStore } from "@/store/modules/instance"
import LabGroupList from "@/views/labs/modules/group/lab-group-list.vue"
import LabList from "@/views/labs/modules/lab/lab-list.vue"
import ProjectProtocolList from "@/views/project/modules/project-protocol-list.vue"
import ProjectList from "@/views/projects/modules/project-list.vue"
import { $t } from "@airalogy/shared/locales"
import { useProfileStore } from "../hooks/useProfileStore"

defineOptions({ name: "ProfileSummary", inheritAttrs: false })

interface SummaryItemProps {
  count: number
  label: string
}

const [DefineSummaryItem, SummaryItem] = createReusableTemplate<SummaryItemProps>()
const [DefineWrapperItem, WrapperItem] = createReusableTemplate<{
  title: string
  handleViewAll?: () => void
  contentClass?: string
  showViewAll?: boolean
}>()

type CountKey = "labs" | "projects" | "protocols" | "groups"
const instanceStore = useInstanceStore()
const countKey = computed<CountKey[]>(() => [
  ...(!instanceStore.isSingleOrganization ? ["labs" as const] : []),
  "projects",
  "protocols",
  ...(!instanceStore.isStructuredLab ? ["groups" as const] : []),
])
const {
  userLabCount,
  userProjectCount,
  userProtocolCount,
  userGroupCount,
  fetchUserLabsData,
  fetchUserProjectsData,
  fetchUserProtocolsData,
  fetchUserGroupsData,
  userInfo,
  userLabList,
  userProjectList,
  userProtocolList,
  userGroupList,
  viewAllState,
} = useProfileStore()!
const authStore = useAuthStore()

const showPrivate = computed(() => {
  if (authStore.userInfo.id === userInfo.value?.id) {
    return true
  }

  return false
})

const singleOrganizationMembership = computed(() => instanceStore.isSingleOrganization
  ? userLabList.value.find(item => item.uid === instanceStore.organization?.uid && (showPrivate.value || item.type !== 1))
  : undefined)

const countRecord = computed<Record<CountKey, SummaryItemProps>>(() => ({
  labs: { count: userLabCount.value, label: $t("page.profile.organizations") },
  projects: { count: userProjectCount.value, label: $t("common.projectsLabel") },
  protocols: { count: userProtocolCount.value, label: $t("page.profile.protocols") },
  groups: { count: userGroupCount.value, label: $t("page.profile.groups") },
}))

async function handleViewAllLabs() {
  const id = userInfo.value?.id
  if (!id) {
    return
  }

  await fetchUserLabsData(id, { page: 1, pageSize: 9999 })
  viewAllState.lab = false
}

async function handleViewAllProjects() {
  const id = userInfo.value?.id
  if (!id) {
    return
  }

  await fetchUserProjectsData(id, { page: 1, pageSize: 9999 })
  viewAllState.project = false
}

async function handleViewAllProtocols() {
  const id = userInfo.value?.id
  if (!id) {
    return
  }

  await fetchUserProtocolsData(id, { page: 1, pageSize: 9999 })
  viewAllState.protocol = false
}

async function handleViewAllGroups() {
  const id = userInfo.value?.id
  if (!id) {
    return
  }

  await fetchUserGroupsData(id, { page: 1, pageSize: 9999 })
  viewAllState.group = false
}

watch(
  () => userInfo.value?.id,
  async (id) => {
    if (id) {
      await Promise.all([
        fetchUserLabsData(id),
        fetchUserProjectsData(id),
        fetchUserProtocolsData(id),
        ...(!instanceStore.isStructuredLab ? [fetchUserGroupsData(id)] : []),
      ])
    }
  },
  { immediate: true },
)
</script>

<style lang="sass" scoped></style>
