<script setup lang="ts">
import type { BusinessRole, Settings } from "@/service/api/project-operations"
import { readOps, writeOps } from "@/service/api/project-operations"
import { useOpsText } from "./fields"

const props = defineProps<{ orgId: string }>()
const tr = useOpsText()
const org = ref<{ enabled: boolean, revision: number }>()
const projects = ref<{ id: string, name: string }[]>([])
const pid = ref("")
const settings = ref<Settings>()
const message = ref("")
const busy = ref(false)
async function load() {
  const id = props.orgId
  const state = await readOps<{ enabled: boolean, revision: number }>(`/organizations/${id}/access`)
  if (id !== props.orgId)
    return
  org.value = state
  projects.value = state.enabled
    ? (await readOps<{ projects: typeof projects.value }>(`/organizations/${id}/projects`)).projects
    : []
  if (!projects.value.some(p => p.id === pid.value))
    pid.value = ""
}
watch(
  () => props.orgId,
  () => {
    settings.value = undefined
    pid.value = ""
    org.value = undefined
    void load().catch(() => (message.value = tr("failed")))
  },
  { immediate: true },
)
async function loadBook(id: string) {
  settings.value = undefined
  if (!id)
    return
  const result = await readOps<Settings>(`/projects/${id}/settings`)
  if (pid.value === id)
    settings.value = result
}
watch(pid, (id) => {
  void loadBook(id).catch(() => (message.value = tr("failed")))
})
async function save(scope: "org" | "book") {
  if (busy.value || !org.value)
    return
  busy.value = true
  message.value = ""
  try {
    if (scope === "org") {
      await writeOps(`/organizations/${props.orgId}`, {
        enabled: !org.value.enabled,
        expected_revision: org.value.revision,
      })
      await load()
      window.dispatchEvent(new Event("operations-settings-changed"))
    }
    else if (settings.value) {
      const grants = Object.fromEntries(
        Object.entries(settings.value.grants).filter(
          ([uid, role]) => role && settings.value!.people.some(person => person.id === uid),
        ),
      )
      await writeOps(`/projects/${pid.value}/settings`, {
        enabled: settings.value.enabled,
        expected_revision: settings.value.revision,
        grants,
      })
      await loadBook(pid.value)
      window.dispatchEvent(new Event("operations-settings-changed"))
    }
    message.value = tr("saved")
  }
  catch {
    message.value = tr("conflictOrFailure")
  }
  finally {
    busy.value = false
  }
}
const roles: BusinessRole[] = ["lead", "finance", "viewer"]
</script>

<template>
  <section class="ops-panel ops" data-testid="ops-settings">
    <h2>{{ tr("orgSettings") }}</h2>
    <div v-if="org" class="ops-line">
      <span>{{ tr(org.enabled ? "enabled" : "disabled") }}</span>
      <button type="button" :disabled="busy" @click="save('org')">
        {{ tr(org.enabled ? "disable" : "enable") }}
      </button>
    </div>
    <template v-if="org?.enabled">
      <label>
        {{ tr("project") }}
        <select v-model="pid" :aria-label="tr('project')">
          <option value="">{{ tr("choose") }}</option>
          <option v-for="p in projects" :key="p.id" :value="p.id">{{ p.name }}</option>
        </select>
      </label>
      <template v-if="settings">
        <label>
          <input v-model="settings.enabled" type="checkbox">
          {{ tr("enableProject") }}
        </label>
        <div v-for="u in settings.people" :key="u.id" class="ops-line">
          <label>
            {{ u.name }} · @{{ u.username }}
            <select v-model="settings.grants[u.id]">
              <option value="">{{ tr("noAccess") }}</option>
              <option v-for="r in roles" :key="r" :value="r">{{ tr(r) }}</option>
            </select>
          </label>
        </div>
        <button type="button" :disabled="busy" @click="save('book')">
          {{ tr("saveAccess") }}
        </button>
      </template>
    </template>
    <p v-if="message" role="status">
      {{ message }}
    </p>
  </section>
</template>

<style src="./operations.css"></style>
