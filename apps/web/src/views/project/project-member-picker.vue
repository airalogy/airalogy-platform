<script setup lang="ts">
import type { ProjectMemberCandidate } from "@/service/api/project-people"
import { ProjectRole } from "@/enum"
import { addOrganizationProjectMembers, getProjectMemberCandidates } from "@/service/api/project-people"
import { useClosableMessage } from "@airalogy/composables"
import { $t } from "@airalogy/shared/locales"
import { refDebounced } from "@vueuse/core"

const props = defineProps<{ projectId: string, isPrivate: boolean, canSetManager: boolean }>()
const emit = defineEmits<{ added: [] }>()
const message = useClosableMessage()
const open = ref(false)
const query = ref("")
const term = refDebounced(query, 200)
const page = ref(1)
const refresh = ref(0)
const users = ref<ProjectMemberCandidate[]>([])
const hasMore = ref(false)
const loading = ref(false)
const failed = ref(false)
const saving = ref(false)
const saveFailed = ref(false)
const selected = ref(new Map<string, { user: ProjectMemberCandidate, role: ProjectRole }>())
const selectedOnly = ref(false)
const visibleUsers = computed(() => selectedOnly.value ? Array.from(selected.value.values(), entry => entry.user) : users.value)
const options = computed(() => [
  ...(props.canSetManager ? [{ value: ProjectRole.MANAGER, label: $t("role.manager") }] : []),
  { value: ProjectRole.COLLABORATOR, label: $t("role.collaborator") },
  { value: ProjectRole.RECORDER, label: $t("role.recorder") },
  ...(props.isPrivate
    ? []
    : [
        { value: ProjectRole.RECORDER_SELF_ONLY, label: $t("role.recorder_self_only") },
        { value: ProjectRole.EXPLORER, label: $t("role.explorer") },
        { value: ProjectRole.EXPLORER_SELF_ONLY, label: $t("role.explorer_self_only") },
        { value: ProjectRole.VIEWER, label: $t("role.viewer") },
        { value: ProjectRole.VIEWER_SELF_ONLY, label: $t("role.viewer_self_only") },
      ]),
])

watch(term, () => {
  page.value = 1
}, { flush: "sync" })
watch([open, term, page, refresh], async ([shown, search, currentPage], _, onCleanup) => {
  let active = true
  onCleanup(() => {
    active = false
  })
  if (!shown)
    return
  loading.value = true
  failed.value = false
  users.value = []
  hasMore.value = false
  try {
    const data = await getProjectMemberCandidates(props.projectId, search.trim(), currentPage)
    if (active) {
      users.value = data.users
      hasMore.value = data.has_more
    }
  }
  catch {
    if (active)
      failed.value = true
  }
  finally {
    if (active)
      loading.value = false
  }
})

function start() {
  selected.value.clear()
  selectedOnly.value = false
  saveFailed.value = false
  query.value = ""
  page.value = 1
  open.value = true
}

function toggle(user: ProjectMemberCandidate, checked: boolean) {
  if (checked)
    selected.value.set(user.id, { user, role: props.isPrivate ? ProjectRole.RECORDER : ProjectRole.COLLABORATOR })
  else
    selected.value.delete(user.id)
  if (!selected.value.size)
    selectedOnly.value = false
}

function changeRole(id: string, role: ProjectRole) {
  const entry = selected.value.get(id)
  if (entry)
    entry.role = role
}

async function save() {
  if (!selected.value.size || saving.value)
    return
  saving.value = true
  saveFailed.value = false
  try {
    const members = Array.from(selected.value, ([user_id, { role }]) => ({ user_id, role }))
    const result = await addOrganizationProjectMembers(props.projectId, members)
    emit("added")
    open.value = false
    message.success($t("page.projectTeam.addedCount", { count: result.added }))
  }
  catch {
    saveFailed.value = true
    refresh.value++
  }
  finally {
    saving.value = false
  }
}
</script>

<template>
  <n-button @click="start">
    <template #icon>
      <icon-local-user-plus />
    </template>
    {{ $t("common.addMember") }}
  </n-button>
  <n-modal v-model:show="open" preset="card" :title="$t('common.addMember')" class="project-picker" :mask-closable="!saving" :closable="!saving" :close-on-esc="!saving">
    <n-input v-if="!selectedOnly" v-model:value="query" clearable :maxlength="255" :placeholder="$t('page.projectTeam.searchDirectory')" :aria-label="$t('page.projectTeam.searchDirectory')" />
    <div class="my-2 flex flex-wrap items-center justify-between gap-2">
      <strong>{{ selectedOnly ? $t("page.projectTeam.selection") : $t("page.projectTeam.organizationMembers") }}</strong>
      <n-button v-if="selected.size" text type="primary" @click="selectedOnly = !selectedOnly">
        {{ selectedOnly ? $t("page.projectTeam.organizationMembers") : $t("page.projectTeam.selectedCount", { count: selected.size }) }}
      </n-button>
    </div>
    <div class="picker-list" data-testid="project-member-directory" :aria-busy="!selectedOnly && loading">
      <p v-if="!selectedOnly && loading" role="status">
        {{ $t("page.projectTeam.loading") }}
      </p>
      <div v-else-if="!selectedOnly && failed" role="alert">
        {{ $t("page.projectTeam.loadFailed") }}
        <n-button text @click="refresh++">
          {{ $t("common.retry") }}
        </n-button>
      </div>
      <p v-else-if="!visibleUsers.length" role="status">
        {{ query.trim() ? $t("page.projectTeam.noMatches") : $t("page.projectTeam.noCandidates") }}
      </p>
      <div v-for="user in visibleUsers" :key="user.id" class="picker-row">
        <n-checkbox :checked="selected.has(user.id)" :disabled="saving || (!selected.has(user.id) && selected.size >= 100)" @update:checked="checked => toggle(user, checked)">
          <span class="break-all">{{ user.display_name }}</span>
          <span class="aira-type-meta ml-1 break-all">@{{ user.username }}</span>
        </n-checkbox>
        <n-select v-if="selected.has(user.id)" :aria-label="$t('common.role')" :value="selected.get(user.id)?.role" :options="options" :disabled="saving" size="small" class="picker-role" @update:value="role => changeRole(user.id, role)" />
      </div>
    </div>
    <div v-if="!selectedOnly && (page > 1 || hasMore)" class="mt-2 flex justify-end gap-2">
      <n-button size="small" :disabled="page === 1 || loading" @click="page--">
        {{ $t("page.projectTeam.previousPage") }}
      </n-button>
      <n-button size="small" :disabled="!hasMore || loading" @click="page++">
        {{ $t("page.projectTeam.nextPage") }}
      </n-button>
    </div>
    <p v-if="saveFailed" role="alert">
      {{ $t("page.projectTeam.saveFailed") }}
    </p>
    <template #footer>
      <div class="flex justify-end gap-2">
        <n-button :disabled="saving" @click="open = false">
          {{ $t("common.cancel") }}
        </n-button>
        <n-button type="primary" :disabled="!selected.size" :loading="saving" @click="save">
          {{ $t("page.projectTeam.addSelected", { count: selected.size }) }}
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<style scoped>
.project-picker { width: min(34rem, calc(100vw - 1.5rem)); }
.picker-list { overflow-y: auto; max-height: min(48dvh, 24rem); }
.picker-row { display: flex; align-items: center; justify-content: space-between; gap: .5rem; padding: .55rem 0; border-bottom: 1px solid var(--n-border-color); }
.picker-role { width: 8.5rem; flex-shrink: 0; }
@media (max-width: 480px) {
  .picker-row { flex-wrap: wrap; }
}
</style>
