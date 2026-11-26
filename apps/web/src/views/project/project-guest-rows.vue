<script setup lang="ts">
import MemberActions from "@/components/common/member-actions.vue"
import { changeGuestAccess, type GuestRole, type GuestTeam, removeGuest } from "@/service/api/project-guests"
import { isAxiosError } from "axios"
import { useDialog } from "naive-ui"
import { useI18n } from "vue-i18n"

type Person = GuestTeam["people"][number]
const props = defineProps<{ people: Person[], projectId: string, manage: boolean }>()
const emit = defineEmits<{ updated: [] }>()
const { t } = useI18n()
const dialog = useDialog()
const editing = ref<Person>()
const role = ref<GuestRole>("reader")
const until = ref<number | null>(null)
const busy = ref(false)
const roles = computed(() => (["reader", "recorder", "editor"] as const).map(value => ({ value, label: t(`page.guests.${value}`) })))
const actions = computed(() => [{ key: "edit", label: t("page.guests.manageAccess") }, { key: "revoke", label: t("page.guests.revoke") }])
function act(key: string | number, row: Person) {
  if (key === "edit") {
    role.value = row.role
    until.value = row.access_until ? Date.parse(row.access_until) : null
    editing.value = row
    return
  }
  dialog.warning({
    title: t("page.guests.revoke"),
    content: `${row.name} · ${t("page.guests.revokePrompt")}`,
    positiveText: t("common.confirm"),
    negativeText: t("common.cancel"),
    onPositiveClick: async () => {
      const { error } = await removeGuest(props.projectId, "people", row.id)
      if (!error)
        emit("updated")
      return !error
    },
  })
}
async function save() {
  if (!editing.value || busy.value)
    return
  busy.value = true
  try {
    const { error } = await changeGuestAccess(props.projectId, editing.value.id, role.value, until.value, editing.value)
    if (!error || (isAxiosError(error) && error.response?.status === 409)) {
      editing.value = undefined
      emit("updated")
    }
  }
  finally { busy.value = false }
}
</script>

<template>
  <n-list-item v-for="row in people" :key="row.id" class="member-list__item" data-testid="external-team">
    <template #prefix>
      <role-icon type="guest" :src="row.avatar_url" />
    </template>
    <global-member-item directory-entry type="project" :is-compact="false" :item="{ ...row, avatar_url: row.avatar_url || '' }">
      <template #role>
        <span class="ml-2 inline-flex flex-wrap items-center gap-1">
          <n-tag size="small" type="info" :bordered="false">{{ t("page.guests.collaborator") }}</n-tag>
          <n-tag size="small" :bordered="false">{{ t(`page.guests.${row.role}`) }}</n-tag>
          <n-tag v-if="row.expired" size="small" type="warning">{{ t("page.guests.expired") }}</n-tag>
        </span>
      </template>
    </global-member-item>
    <template v-if="manage" #suffix>
      <member-actions :options="actions" @select="act($event, row)" />
    </template>
  </n-list-item>
  <n-modal :show="!!editing" preset="card" :title="t('page.guests.manageAccess')" style="width: min(30rem, calc(100vw - 2rem))" @update:show="value => { if (!value) editing = undefined }">
    <form v-if="editing" class="grid gap-4" @submit.prevent="save">
      <strong>{{ editing.name }} · @{{ editing.username }}</strong>
      <label>{{ t("page.guests.access") }}<n-select v-model:value="role" :options="roles" /></label>
      <p v-if="role === 'editor'" class="aira-type-meta m-0">
        {{ t("page.guests.editorHint") }}
      </p>
      <label>{{ t("page.guests.until") }}<n-date-picker v-model:value="until" type="datetime" clearable /></label>
      <n-button type="primary" attr-type="submit" :loading="busy">
        {{ t("common.save") }}
      </n-button>
    </form>
  </n-modal>
</template>
