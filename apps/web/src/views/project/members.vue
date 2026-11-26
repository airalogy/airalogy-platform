<script setup lang="ts">
import type { ProjectTeam } from "@/service/api/project-people"
import GlobalMemberList from "@/components/common/global-member-list.vue"
import { LAB_OWNER_AND_MANAGER } from "@/composables/useLabPermissions"
import { useProjectPermissions } from "@/composables/useProjectPermissions"
import { ProjectType } from "@/enum"
import { guestTeam, type GuestTeam } from "@/service/api/project-guests"
import { getProjectTeam } from "@/service/api/project-people"
import { fetchProjectMembers } from "@/service/api/projects"
import { useInstanceStore } from "@/store/modules/instance"
import { useOrProvideProjectInfoStore } from "../project-protocols/hooks/useProjectInfoStore"
import ProjectGuestRows from "./project-guest-rows.vue"
import ProjectGuestTeam from "./project-guest-team.vue"
import ProjectMemberPicker from "./project-member-picker.vue"

defineOptions({ name: "ProjectMembers" })

const { projectInfo } = useOrProvideProjectInfoStore(null)
const projectId = computed(() => projectInfo.value?.id)
const instance = useInstanceStore()
const { canShowSettings, canSetManager } = useProjectPermissions(projectInfo)
const canAddMembers = computed(() => canShowSettings.value || LAB_OWNER_AND_MANAGER.includes(projectInfo.value?.user_lab_role))
const team = ref<ProjectTeam>()
const members = ref<Api.Project.MemberListItem[]>([])
const page = ref(1)
const pageSize = 10
const total = ref(0)
const loadingMembers = ref(false)
const teamFailed = ref(false)
const membersFailed = ref(false)
const route = useRoute()
const router = useRouter()
const person = computed(() => typeof route.query.person === "string" ? route.query.person : undefined)
const guests = ref<GuestTeam>()
const guestFailed = ref(false)
const inviter = ref<InstanceType<typeof ProjectGuestTeam>>()
const revision = ref(0)
watch([projectId, revision, () => instance.isSingleLab], async ([id, , single], _, onCleanup) => {
  let active = true
  onCleanup(() => {
    active = false
  })
  guests.value = undefined
  guestFailed.value = false
  if (!single || !id)
    return
  const { data } = await guestTeam(id)
  if (active) {
    guests.value = data || undefined
    guestFailed.value = !data
  }
}, { immediate: true })
const guestRows = computed(() => (guests.value?.people || []).filter(row => !person.value || row.id === person.value))
const additional = computed(() => (team.value?.additional_members || []).filter(row => !person.value || row.id === person.value))

function reload() {
  revision.value++
}
watch([projectId, revision], async ([id], _, onCleanup) => {
  let active = true
  onCleanup(() => {
    active = false
  })
  team.value = undefined
  teamFailed.value = false
  page.value = 1
  if (!id)
    return
  try {
    const result = await getProjectTeam(id)
    if (active)
      team.value = result
  }
  catch {
    if (active)
      teamFailed.value = true
  }
}, { immediate: true })

watch([projectId, page, revision, person], async ([id, currentPage, , filter], _, onCleanup) => {
  let active = true
  onCleanup(() => {
    active = false
  })
  members.value = []
  membersFailed.value = false
  total.value = 0
  loadingMembers.value = Boolean(id)
  if (!id)
    return
  try {
    const { data, error } = await fetchProjectMembers(id, { page: filter ? 1 : currentPage, pageSize, person: filter })
    if (!active)
      return
    if (error || !data) {
      membersFailed.value = true
    }
    else {
      members.value = data.users
      total.value = data.total_count
      if (!data.users.length && currentPage > 1)
        page.value = Math.max(1, Math.ceil(total.value / pageSize))
    }
  }
  catch {
    if (active)
      membersFailed.value = true
  }
  finally {
    if (active)
      loadingMembers.value = false
  }
}, { immediate: true })
</script>

<template>
  <div class="min-w-0 space-y-5" data-testid="project-team">
    <section class="team-section" aria-labelledby="project-team-accounts" data-testid="team-accounts">
      <header class="flex flex-wrap items-center justify-between gap-2">
        <h2 id="project-team-accounts" class="aira-type-section-title m-0">
          {{ $t("page.projectTeam.accessMembers") }}
        </h2>
        <div v-if="canAddMembers && projectInfo" class="flex flex-wrap items-center gap-2">
          <project-member-picker
            :key="projectInfo.id" :project-id="projectInfo.id" :is-private="projectInfo.type === ProjectType.PRIVATE"
            :can-set-manager="canSetManager || LAB_OWNER_AND_MANAGER.includes(projectInfo.user_lab_role)"
            @added="reload"
          />
          <n-button v-if="guests?.can_manage" @click="inviter?.open()">
            {{ $t("page.guests.invite") }}
          </n-button>
          <global-add-member-table-modal
            v-if="!instance.isSingleLab" :id="projectInfo.id" :show-icon="false" :button-props="{ text: true }"
            :trigger="$t('page.projectTeam.lookupAccount')" type="project" :is-private="projectInfo.type === ProjectType.PRIVATE"
            @modal:new-member="reload"
          />
        </div>
      </header>
      <n-button v-if="person" text class="justify-self-start" @click="router.replace({ path: route.path, query: { ...route.query, person: undefined } })">
        {{ $t("page.guests.showTeam") }}
      </n-button>
      <n-alert v-if="membersFailed || teamFailed || guestFailed" type="error">
        {{ $t("page.projectTeam.loadFailed") }}
        <n-button text @click="reload">
          {{ $t("common.retry") }}
        </n-button>
      </n-alert>
      <global-member-list
        v-if="projectId && (members.length || guestRows.length || additional.length)" :id="projectId" :list="members" type="project"
        @update:role="reload"
      >
        <template #additional-rows>
          <n-list-item v-for="member in additional" :key="member.id" class="member-list__item">
            <template #prefix>
              <role-icon type="project" :src="member.avatar_url" />
            </template>
            <global-member-item directory-entry type="project" :is-compact="false" :item="{ ...member, name: member.display_name || member.name, avatar_url: member.avatar_url || '' }">
              <template #role>
                <n-tag class="ml-2" size="small" :bordered="false">
                  {{ $t("page.projectTeam.otherAccess") }}
                </n-tag>
              </template>
            </global-member-item>
          </n-list-item>
          <project-guest-rows :people="guestRows" :project-id="projectId" :manage="!!guests?.can_manage" @updated="reload" />
        </template>
      </global-member-list>
      <project-guest-team v-if="projectId && guests?.can_manage" :key="projectId" ref="inviter" :project-id="projectId" :team="guests" @updated="reload" />
      <n-pagination v-if="total > pageSize" v-model:page="page" :page-size="pageSize" :item-count="total" :page-slot="5" />
      <p v-if="loadingMembers || (!team && !teamFailed)" class="aira-type-meta" role="status">
        {{ $t("page.projectTeam.loading") }}
      </p>
      <p v-else-if="team && !membersFailed && !members.length && !additional.length && !guestRows.length" class="aira-type-meta">
        {{ $t("page.projectTeam.noMembers") }}
      </p>
    </section>
    <section aria-labelledby="project-team-names" class="team-section" data-testid="team-participants">
      <h2 id="project-team-names" class="aira-type-section-title m-0">
        {{ $t("page.projectTeam.namedParticipants") }}
      </h2>
      <p class="aira-type-meta m-0">
        {{ $t("page.projectTeam.namedHint") }}
      </p>
      <ul v-if="team?.participants.length" class="team-list">
        <li v-for="participant in team.participants" :key="participant.id">
          <span class="break-words">{{ participant.name }}</span>
          <span v-if="participant.organization" class="aira-type-meta break-words">{{ participant.organization }}</span>
        </li>
      </ul>
      <p v-else-if="team" class="aira-type-meta">
        {{ $t("page.projectTeam.noParticipants") }}
      </p>
    </section>
  </div>
</template>

<style scoped>
.team-section { display: grid; gap: 0.6rem; min-width: 0; }
.team-section + .team-section { border-top: 1px solid var(--n-border-color, #e5e7eb); padding-top: 1rem; }
.team-list { list-style: none; padding: 0; margin: 0; }
.team-list li { display: flex; align-items: baseline; flex-wrap: wrap; gap: 0.25rem 0.75rem; padding: 0.45rem 0; overflow-wrap: anywhere; }
</style>
