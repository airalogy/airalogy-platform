<script setup lang="ts">
import type { ExternalDashboard } from "@/service/api/external-access"
import type { Coverage, ProjectTarget } from "./project-coverage"
import { $t } from "@airalogy/shared/locales"

const props = defineProps<{ projects: ExternalDashboard["projects"], organizations?: ExternalDashboard["organizations"] }>()
const target = defineModel<ProjectTarget>({ required: true })
const modeOptions = computed(() => [
  { value: "single", label: $t("accountSettings.oneProject") },
  { value: "selected", label: $t("accountSettings.selectedProjects") },
  { value: "accessible", label: $t("accountSettings.ongoingProjects") },
])
const orgOptions = computed(() => (props.organizations || []).filter(o => o.enabled).map(o => ({ label: o.name, value: o.id })))
const choices = computed(() => props.projects.filter(p => p.enabled && p.lab_id === target.value.organization).map(p => ({ label: p.name, value: p.id })))
function changeMode(mode: Coverage) {
  target.value = { mode, organization: target.value.organization || (orgOptions.value.length === 1 ? orgOptions.value[0].value : null), ids: [] }
}
</script>

<template>
  <div class="w-full space-y-2">
    <n-select :value="target.mode" :options="modeOptions" :aria-label="$t('externalAccess.target')" @update:value="changeMode" />
    <slot v-if="target.mode === 'single'" />
    <template v-else>
      <n-select :value="target.organization" :options="orgOptions" :placeholder="$t('externalAccess.organization')" :aria-label="$t('externalAccess.organization')" @update:value="organization => target = { ...target, organization, ids: [] }" />
      <template v-if="target.mode === 'selected'">
        <n-select :value="target.ids" multiple filterable clearable :options="choices" :placeholder="$t('externalAccess.projectHint')" @update:value="ids => target = { ...target, ids }" />
        <n-button size="small" text type="primary" :disabled="!choices.length" @click="target = { ...target, ids: choices.map(p => p.value) }">
          {{ $t("accountSettings.allCurrent", { count: choices.length }) }}
        </n-button>
      </template>
      <p class="text-sm color-text-secondary">
        {{ $t(target.mode === 'accessible' ? 'accountSettings.ongoingHint' : 'accountSettings.snapshotHint') }}
      </p>
    </template>
  </div>
</template>
