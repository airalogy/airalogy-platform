<template>
  <n-radio-group v-if="canManageGuests" v-model:value="directory" class="mb-3" :aria-label="$t('page.labs.members')">
    <n-radio-button value="staff">{{ $t("page.guests.members") }}</n-radio-button>
    <n-radio-button value="guests">{{ $t("page.guests.external") }}</n-radio-button>
  </n-radio-group>
  <guest-directory v-if="canManageGuests && directory === 'guests'" />
  <loading-list-wrapper v-else ref="wrapperRef" :fetcher="fetcher">
    <template #default="{ data }">
      <global-member-list
        :id="labId" :list="data" type="lab"
        @update:role="handleUpdateRole"
      />
    </template>
    <template #empty>
      <div class="absolute-center">
        No members
      </div>
    </template>
  </loading-list-wrapper>
</template>

<script setup lang="ts">
import type { FetchData, FetchPayload } from "@/components/common/loading-list-wrapper.vue"
import GlobalMemberList from "@/components/common/global-member-list.vue"
import LoadingListWrapper from "@/components/common/loading-list-wrapper.vue"
import { useRouterPush } from "@/composables/useRouterPush"
import { fetchLabMemberList } from "@/service/api/labs"
import { useInstanceStore } from "@/store/modules/instance"
import { useOrProvideLabInfoStore } from "./hooks/useLabsInfoStore"
import GuestDirectory from "./modules/guest-directory.vue"

defineOptions({
  name: "LabsMembers",
})

const wrapperRef = ref<{ reload: () => void }>()

const route = useRoute()

const directory = ref("staff")
const instance = useInstanceStore()
const { labInfo, isManager, fetchLabInfoByUid } = useOrProvideLabInfoStore(null)
const canManageGuests = computed(() => instance.isSingleLab && isManager.value)

const labId = computed(() => {
  return String(labInfo.value?.id ?? "")
})

const { routerPushByKey } = useRouterPush()

async function fetcher(params: FetchPayload): Promise<FetchData> {
  if (!labId.value) {
    return null
  }

  try {
    const { currentPage, currentPageSize, requestId } = params
    const data = await fetchLabMemberList(labId.value, {
      page: currentPage,
      pageSize: currentPageSize,
    }, requestId)
    if (data && Array.isArray(data.users)) {
      const { users, total_count } = data
      return { list: users, total: total_count }
    }
  }
  catch (e) {
    // TODO
  }
  finally {
    routerPushByKey.bind(null, "lab-not-found")
  }
  return null
}

async function handleUpdateRole() {
  wrapperRef.value?.reload()
}

onMounted(async () => {
  if (!labInfo.value) {
    const { labUid } = route.params
    await fetchLabInfoByUid(labUid as string, routerPushByKey.bind(null, "not-found"))
  }
})

watch(() => labInfo.value?.id, async () => {
  await wrapperRef.value?.reload()
}, { immediate: true })
</script>

<style scoped lang="sass">
@use "@styles/sass/list.sass" as *
</style>
