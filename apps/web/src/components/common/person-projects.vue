<script setup lang="ts">
import { getRoleLabel } from "@/composables/useRoleDescription"
import { ProjectRole } from "@/enum"
import { type PersonProject, personProjects } from "@/service/api/project-guests"
import { useI18n } from "vue-i18n"

const props = defineProps<{ person: { id: string, name: string, email?: string | null } }>()
const emit = defineEmits<{ close: [] }>()
const { t, locale } = useI18n()
const rows = ref<PersonProject[]>()
const failed = ref(false)
const retry = ref(0)
watch([() => props.person.id, retry], async ([id], _, onCleanup) => {
  let active = true
  onCleanup(() => {
    active = false
  })
  rows.value = undefined
  failed.value = false
  const { data } = await personProjects(id)
  if (active) {
    rows.value = data || undefined
    failed.value = !data
  }
}, { immediate: true })
function role(row: PersonProject) {
  if (row.source === "guest")
    return t(row.role === ProjectRole.PROTOCOL_EDITOR ? "page.guests.editor" : row.role === ProjectRole.RECORDER ? "page.guests.recorder" : "page.guests.reader")
  return row.role && getRoleLabel(row.role, "project")
}
</script>

<template>
  <n-modal show preset="card" :title="t('page.guests.collaborationDetails')" style="width: min(34rem, calc(100vw - 2rem))" @update:show="show => { if (!show) emit('close') }">
    <div class="max-h-65vh overflow-auto">
      <strong>{{ person.name }}</strong>
      <span v-if="person.email" class="ml-2 break-all">{{ person.email }}</span>
      <n-alert v-if="failed" type="error">
        {{ t("page.projectTeam.loadFailed") }} <n-button text @click="retry++">
          {{ t("common.retry") }}
        </n-button>
      </n-alert>
      <p v-else-if="!rows" role="status">
        {{ t("page.projectTeam.loading") }}
      </p>
      <p v-else-if="!rows.length">
        {{ t("page.guests.noProjects") }}
      </p>
      <ul v-else class="list-none p-0">
        <li v-for="row in rows" :key="row.id + row.source" class="flex flex-wrap items-center justify-between gap-2 border-t border-slate-200 py-3">
          <div class="min-w-0 break-words">
            <strong>{{ row.name }}</strong>
            <div class="aira-type-meta">
              {{ t(`page.guests.source_${row.source}`) }} · {{ role(row) || t("page.projectTeam.otherAccess") }}
            </div>
            <div v-if="row.access_until" class="aira-type-meta">
              {{ t(row.expired ? "page.guests.expired" : "page.guests.until") }} · {{ new Date(row.access_until).toLocaleString(locale) }}
            </div>
          </div>
          <router-link v-if="row.path" :to="{ path: row.path, query: { person: person.id } }" :aria-label="`${t('page.guests.openTeam')} · ${row.name}`" class="text-primary" @click="emit('close')">
            {{ t("page.guests.openTeam") }}
          </router-link>
        </li>
      </ul>
    </div>
  </n-modal>
</template>
