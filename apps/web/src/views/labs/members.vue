<template>
  <n-radio-group v-if="canManageGuests" :value="directory" class="mb-3" role="radiogroup" :aria-label="$t('page.labs.members')" @update:value="selectDirectory">
    <n-radio-button value="all">
      {{ $t("common.all") }}
    </n-radio-button>
    <n-radio-button value="staff">
      {{ $t("page.guests.members") }}
    </n-radio-button>
    <n-radio-button value="guest">
      {{ $t("page.guests.external") }}
    </n-radio-button>
  </n-radio-group>
  <loading-list-wrapper :key="`${labId}-${canManageGuests}-${directory}`" ref="wrapperRef" :fetcher="fetcher">
    <template #default="{ data }">
      <global-member-list
        :id="labId" :list="canManageGuests ? staffRows(data) : data" type="lab"
        @update:role="handleUpdateRole"
      >
        <template v-if="canManageGuests" #additional-rows="{ resetPassword }">
          <guest-directory :people="guestRows(data)" @reset="resetPassword" @updated="wrapperRef?.reload(false)" />
        </template>
      </global-member-list>
    </template>
    <template #empty>
      <div class="absolute-center">
        {{ $t("page.guests.emptyRoster") }}
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
import { type DirectoryFilter, type DirectoryPerson, organizationPeople } from "@/service/api/project-guests"
import { useInstanceStore } from "@/store/modules/instance"
import { useOrProvideLabInfoStore } from "./hooks/useLabsInfoStore"
import GuestDirectory from "./modules/guest-directory.vue"

defineOptions({
  name: "LabsMembers",
})

const wrapperRef = ref<{ reload: (resetPage?: boolean) => void }>()

const route = useRoute()
const router = useRouter()

const directory = ref<DirectoryFilter>("all")
const instance = useInstanceStore()
const { labInfo, isManager, fetchLabInfoByUid } = useOrProvideLabInfoStore(null)
const canManageGuests = computed(() => instance.isSingleLab && isManager.value)

const labId = computed(() => {
  return String(labInfo.value?.id ?? "")
})

const { routerPushByKey } = useRouterPush()

async function selectDirectory(value: DirectoryFilter) {
  if (directory.value === value)
    return
  if (route.query.page)
    await router.replace({ path: route.path, query: { ...route.query, page: undefined }, hash: route.hash })
  directory.value = value
}

function staffRows(people: DirectoryPerson[]) {
  return people.filter(person => person.kind === "staff")
}
function guestRows(people: DirectoryPerson[]) {
  return people.filter(person => person.kind === "guest")
}

async function fetcher({ currentPage, currentPageSize, requestId }: FetchPayload): Promise<FetchData> {
  if (!labId.value)
    return null
  if (canManageGuests.value) {
    const { data } = await organizationPeople(directory.value, currentPage, currentPageSize)
    return data || null
  }
  const data = await fetchLabMemberList(labId.value, { page: currentPage, pageSize: currentPageSize }, requestId)
  return data ? { list: data.users, total: data.total_count } : null
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
</script>

<style scoped lang="sass">
@use "@styles/sass/list.sass" as *
</style>
