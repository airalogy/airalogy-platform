<script setup lang="ts">
import MemberActions from "@/components/common/member-actions.vue"
import { type GuestPerson, renameGuest } from "@/service/api/project-guests"
import { useI18n } from "vue-i18n"
import GuestConversion from "./guest-conversion.vue"

defineProps<{ people: GuestPerson[] }>()
const emit = defineEmits<{ updated: [], reset: [person: GuestPerson] }>()
const { t } = useI18n()
const promoting = ref<GuestPerson | null>(null)
const details = ref<GuestPerson | null>(null)
const actions = computed(() => [
  { key: "details", label: t("page.guests.collaborationDetails") },
  { key: "alias", label: t("common.setAlias") },
  { key: "promote", label: t("page.guests.promote") },
  { key: "reset", label: t("page.instance.createResetLink") },
])
function selectAction(key: string | number, person: GuestPerson) {
  if (key === "details")
    details.value = person
  else if (key === "alias")
    edit(person)
  else if (key === "promote")
    promoting.value = person
  else if (key === "reset")
    emit("reset", person)
}
const editing = ref<GuestPerson | null>(null)
const name = ref("")
const saving = ref(false)

function edit(person: GuestPerson) {
  editing.value = person
  name.value = person.display_name || person.name
}
async function save() {
  if (saving.value || !editing.value || !name.value.trim())
    return
  saving.value = true
  try {
    const { data } = await renameGuest(editing.value.id, name.value.trim())
    if (data) {
      editing.value = null
      emit("updated")
    }
  }
  finally { saving.value = false }
}
</script>

<template>
  <n-list-item v-for="person in people" :key="person.id" class="member-list__item" data-testid="guest-row">
    <template #prefix>
      <role-icon type="guest" :src="person.avatar_url" />
    </template>
    <global-member-item :item="{ ...person, avatar_url: person.avatar_url || '' }" directory-entry :is-compact="false" type="lab" class="min-w-0 w-fit">
      <template #role>
        <n-tag type="info" :bordered="false" class="ml-5">
          {{ $t("page.guests.collaborator") }}
        </n-tag>
      </template>
    </global-member-item>
    <template #suffix>
      <member-actions :options="actions" @select="selectAction($event, person)" />
    </template>
  </n-list-item>
  <guest-conversion v-if="promoting" :key="promoting.id" :user-id="promoting.id" :name="promoting.name" to-member @close="promoting = null" @converted="promoting = null; emit('updated')" />
  <n-modal :show="!!details" preset="card" :title="$t('page.guests.collaborationDetails')" style="width: min(26rem, calc(100vw - 2rem))" @update:show="value => { if (!value) details = null }">
    <div v-if="details" class="grid gap-2 break-words">
      <strong>{{ details.name }}</strong>
      <span class="break-all">{{ details.email }}</span>
      <span>{{ details.projects.length ? $t("page.guests.projectList", { projects: details.projects.join(" · ") }) : $t("page.guests.noProjects") }}</span>
    </div>
  </n-modal>
  <n-modal :show="!!editing" preset="card" :title="$t('common.labAliasLabel')" style="width: min(26rem, calc(100vw - 2rem))" @update:show="value => { if (!value) editing = null }">
    <form class="grid gap-4" @submit.prevent="save">
      <label>{{ $t("common.labAliasLabel") }}<n-input v-model:value="name" :maxlength="255" :input-props="{ required: true }" /></label>
      <div class="flex justify-end gap-2">
        <n-button @click="editing = null">
          {{ $t("common.cancel") }}
        </n-button>
        <n-button attr-type="submit" type="primary" :loading="saving" :disabled="!name.trim()">
          {{ $t("common.save") }}
        </n-button>
      </div>
    </form>
  </n-modal>
</template>
