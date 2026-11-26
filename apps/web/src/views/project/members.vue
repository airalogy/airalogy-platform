<script setup lang="ts">
import type { ProjectTeam } from "@/service/api/project-people"
import GlobalMemberList from "@/components/common/global-member-list.vue"
import { LAB_OWNER_AND_MANAGER } from "@/composables/useLabPermissions"
import { useProjectPermissions } from "@/composables/useProjectPermissions"
import { ProjectType } from "@/enum"
import { getProjectTeam } from "@/service/api/project-people"
import { fetchProjectMembers } from "@/service/api/projects"
import { useInstanceStore } from "@/store/modules/instance"
import { useOrProvideProjectInfoStore } from "../project-protocols/hooks/useProjectInfoStore"
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
const revision = ref(0)
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

watch([projectId, page, revision], async ([id, currentPage], _, onCleanup) => {
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
    const { data, error } = await fetchProjectMembers(id, { page: currentPage, pageSize })
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
          <global-add-member-table-modal
            v-if="!instance.isSingleLab" :id="projectInfo.id" :show-icon="false" :button-props="{ text: true }"
            :trigger="$t('page.projectTeam.lookupAccount')" type="project" :is-private="projectInfo.type === ProjectType.PRIVATE"
            @modal:new-member="reload"
          />
        </div>
      </header>
      <n-alert v-if="membersFailed || teamFailed" type="error">
        {{ $t("page.projectTeam.loadFailed") }}
        <n-button text @click="reload">
          {{ $t("common.retry") }}
        </n-button>
      </n-alert>
      <global-member-list
        v-if="projectId && members.length" :id="projectId" :list="members" type="project"
        @update:role="reload"
      />
      <n-pagination v-if="total > pageSize" v-model:page="page" :page-size="pageSize" :item-count="total" :page-slot="5" />
      <ul v-if="team?.additional_members.length" class="team-list">
        <li v-for="member in team.additional_members" :key="member.id">
          <router-link :to="{ name: 'user-profile', params: { username: member.username } }" class="break-all text-primary">
            {{ member.display_name || member.name || member.username }}
          </router-link>
          <span class="aira-type-meta">{{ $t("page.projectTeam.otherAccess") }}</span>
        </li>
      </ul>
      <p v-if="loadingMembers || (!team && !teamFailed)" class="aira-type-meta" role="status">
        {{ $t("page.projectTeam.loading") }}
      </p>
      <p v-else-if="team && !membersFailed && !members.length && !team.additional_members.length" class="aira-type-meta">
        {{ $t("page.projectTeam.noMembers") }}
      </p>
    </section>
    <project-guest-team v-if="instance.isSingleLab && canAddMembers && projectId" :key="projectId" :project-id="projectId" />
    <section aria-labelledby="project-team-names" class="team-section" data-testid="team-participants">
      <h2 id="project-team-names" class="aira-type-section-title m-0">
        {{ $t("page.projectTeam.namedParticipants") }}
      </h2>
      <p class="aira-type-meta m-0">
        {{ $t("page.projectTeam.namedHint") }}
      </p>
      <ul v-if="team?.participants.length" class="team-list">
        <li v-for="person in team.participants" :key="person.id">
          <span class="break-words">{{ person.name }}</span>
          <span v-if="person.organization" class="aira-type-meta break-words">{{ person.organization }}</span>
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
