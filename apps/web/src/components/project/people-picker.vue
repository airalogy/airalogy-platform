<script setup lang="ts">
import type { ProjectPerson } from "@/service/api/project-people"
import { meetingMembers } from "@/service/api/meetings"
import { associateProjectPerson, createProjectPerson, listProjectPeople } from "@/service/api/project-people"
import { useDialog } from "naive-ui"
import { useI18n } from "vue-i18n"

const props = defineProps<{ projectId: string, members: { id: string, name: string, username?: string }[], modelValue: string | string[] | null, multiple?: boolean, disabled?: boolean }>()
const emit = defineEmits<{ "update:modelValue": [value: string | string[] | null] }>()
const { t } = useI18n()
const dialog = useDialog()
const people = ref<ProjectPerson[]>([])
const accounts = ref<{ id: string, name: string, username: string }[]>([])
const canManage = ref(false)
const canWrite = ref(false)
const show = ref(false)
const busy = ref(false)
const error = ref("")
const name = ref("")
const organization = ref("")
let requestId = crypto.randomUUID()
const options = computed(() => [
  ...people.value.map(p => ({ value: `person:${p.id}`, label: `${p.name}${p.organization ? ` · ${p.organization}` : ""}${p.user_id ? ` · ${t("page.projectPeople.linked")}` : ""}` })),
  ...props.members.filter(m => !people.value.some(p => p.user_id === m.id) || (Array.isArray(props.modelValue) ? props.modelValue : [props.modelValue]).includes(`user:${m.id}`)).map(m => ({ value: `user:${m.id}`, label: `${m.name || m.username} (@${m.username || m.name})` })),
])
async function load() {
  error.value = ""
  try {
    const result = await listProjectPeople(props.projectId)
    people.value = result.people
    canManage.value = result.can_manage_accounts
    canWrite.value = result.can_write
    if (result.can_manage_accounts)
      accounts.value = (await meetingMembers(props.projectId)).members
  }
  catch { error.value = t("page.projectPeople.failed") }
}
async function add() {
  if (!name.value.trim() || busy.value)
    return
  busy.value = true
  error.value = ""
  try {
    const person = await createProjectPerson(props.projectId, requestId, name.value.trim(), organization.value.trim())
    await load()
    publish(person)
    const value = `person:${person.id}`
    emit("update:modelValue", props.multiple ? [...(Array.isArray(props.modelValue) ? props.modelValue : []), value] : value)
    requestId = crypto.randomUUID()
    name.value = ""
    organization.value = ""
    show.value = false
  }
  catch { error.value = t("page.projectPeople.failed") }
  finally { busy.value = false }
}
function associate(person: ProjectPerson, userId: string | null) {
  if (person.user_id === userId)
    return
  const account = accounts.value.find(m => m.id === userId)
  dialog.warning({
    title: t("page.projectPeople.associate"),
    content: t(userId ? "page.projectPeople.confirm" : "page.projectPeople.disconnectConfirm", { name: person.name, account: account ? `${account.name} (@${account.username})` : t("page.projectPeople.unlinked"), count: person.assigned_count || 0 }),
    positiveText: t("common.confirm"),
    negativeText: t("common.cancel"),
    onPositiveClick: async () => {
      busy.value = true
      try {
        const saved = await associateProjectPerson(person, userId)
        publish(saved)
        await load()
      }
      catch {
        error.value = t("page.projectPeople.failed")
        return false
      }
      finally { busy.value = false }
    },
  })
}
function publish(person: ProjectPerson) {
  window.dispatchEvent(new CustomEvent("airalogy:project-person-saved", { detail: person }))
}
function receive(event: Event) {
  const person = (event as CustomEvent<ProjectPerson>).detail
  if (person.project_id !== props.projectId)
    return
  const index = people.value.findIndex(p => p.id === person.id)
  if (index < 0)
    people.value.push(person)
  else people.value[index] = { ...people.value[index], ...person }
}
onMounted(() => window.addEventListener("airalogy:project-person-saved", receive))
onBeforeUnmount(() => window.removeEventListener("airalogy:project-person-saved", receive))
watch(() => props.projectId, load, { immediate: true })
</script>

<template>
  <div class="min-w-0">
    <n-select :value="modelValue" :multiple="multiple" :disabled="disabled" :options="options" filterable clearable @update:value="emit('update:modelValue', $event)" />
    <n-button v-if="canWrite && !disabled" text size="tiny" class="mt-1" @click="show = true; load()">{{ t("page.projectPeople.manage") }}</n-button>
    <p v-if="error" class="text-sm text-red-600" role="alert">{{ error }}</p>
    <n-modal v-model:show="show" preset="card" :title="t('page.projectPeople.manage')" class="max-w-xl">
      <p class="text-sm text-gray-500">{{ t("page.projectPeople.hint") }}</p>
      <form class="space-y-3" @submit.prevent="add">
        <n-input v-model:value="name" :disabled="busy" :maxlength="255" :placeholder="t('page.projectPeople.name')" data-testid="project-person-name" />
        <n-input v-model:value="organization" :disabled="busy" :maxlength="255" :placeholder="t('page.projectPeople.organization')" />
        <n-button attr-type="submit" type="primary" :loading="busy" :disabled="!name.trim()" data-testid="project-person-add">{{ t("page.projectPeople.add") }}</n-button>
      </form>
      <p v-if="error" class="text-sm text-red-600" role="alert">{{ error }}</p>
      <div v-for="person in people" :key="person.id" class="mt-3 border-t pt-3">
        <p class="mb-1">{{ person.name }} <span class="text-gray-500">{{ person.organization }}</span></p>
        <n-select v-if="canManage" data-testid="project-person-account" :value="person.user_id" :disabled="busy" :placeholder="t('page.projectPeople.unlinked')" :options="accounts.map(m => ({ value: m.id, label: `${m.name} (@${m.username || m.name})`, disabled: people.some(p => p.id !== person.id && p.user_id === m.id) }))" filterable clearable @update:value="associate(person, $event)" />
        <p v-else class="text-xs text-gray-500">{{ t(person.user_id ? 'page.projectPeople.linked' : 'page.projectPeople.adminHint') }}</p>
      </div>
    </n-modal>
  </div>
</template>
