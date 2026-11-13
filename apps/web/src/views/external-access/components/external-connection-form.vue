<script setup lang="ts">
import type { ExternalDashboard } from "@/service/api/external-access"
import { createExternalGrant } from "@/service/api/external-access"
import { useAppStore } from "@/store/modules/app"
import { useInstanceStore } from "@/store/modules/instance"
import { useClosableMessage } from "@airalogy/composables"
import { $t } from "@airalogy/shared/locales"
import { copyToClip, documentationPageUrl } from "@airalogy/shared/utils"

const props = defineProps<{ projects: ExternalDashboard["projects"], projectId?: string, failed: boolean }>()
const emit = defineEmits<{ created: [] }>()
const message = useClosableMessage()
const route = useRoute()
const app = useAppStore()
const instance = useInstanceStore()
const documentationUrl = computed(() => documentationPageUrl(instance.documentationUrl, app.locale, "external-agent-access"))
const name = ref("")
const projectId = ref<string | null>(props.projectId || null)
const days = ref<number | null>(7)
const preset = ref("read")
const selectedScopes = ref(["protocols:read", "records:read"])
const token = ref("")
const issuedProject = ref("")
const busy = ref(false)
const checking = ref(false)
const connectionStatus = ref("")
const connectionFailed = ref(false)
const endpoint = `${window.location.origin}/api/mcp`
const command = `codex mcp add airalogy --url ${JSON.stringify(endpoint)} --bearer-token-env-var AIRALOGY_PLATFORM_TOKEN`
const selectedProject = computed(() => props.projects.find(item => item.id === projectId.value))
const projectOptions = computed(() => props.projects.map(p => ({ value: p.id, label: `${p.name}${p.enabled ? "" : ` — ${$t("externalAccess.labDisabled")}`}`, disabled: !p.enabled })))
const presets: Record<string, string[]> = {
  read: ["protocols:read", "records:read"],
  analyze: ["protocols:read", "records:read", "records:export", "analysis:read", "analysis:write"],
  author: ["protocols:read", "protocols:source", "protocols:candidate", "protocols:publish"],
}
const scopeOptions = computed(() => [
  { label: $t("externalAccess.readProtocols"), value: "protocols:read", disabled: true },
  { label: $t("externalAccess.readRecords"), value: "records:read" },
  { label: $t("externalResearch.exportRecords"), value: "records:export" },
  { label: $t("externalResearch.readAnalysis"), value: "analysis:read" },
  { label: $t("externalResearch.writeAnalysis"), value: "analysis:write" },
  { label: $t("externalResearch.complex"), value: "records:complex" },
  { label: $t("externalResearch.knowledge"), value: "knowledge:read" },
  { label: $t("externalResearch.documents"), value: "documents:read" },
  { label: $t("externalResearch.materials"), value: "materials:read" },
  { label: $t("externalResearch.files"), value: "files:read" },
  { label: $t("externalResearch.readSource"), value: "protocols:source" },
  { label: $t("externalResearch.candidate"), value: "protocols:candidate" },
  { label: $t("externalResearch.publish"), value: "protocols:publish" },
  { label: $t("externalAccess.importRecords"), value: "records:import" },
  { label: $t("externalAccess.reviseRecords"), value: "records:revise" },
])
function scopeLabel(scope: string) {
  return scopeOptions.value.find(item => item.value === scope)?.label || scope
}
const permissionUnavailable = computed(() => (selectedScopes.value.some(s => ["records:export", "analysis:read", "analysis:write"].includes(s)) && !selectedProject.value?.can_export)
  || (selectedScopes.value.some(s => ["protocols:candidate", "protocols:publish"].includes(s)) && !selectedProject.value?.can_author))
const canCreate = computed(() => name.value.trim() && selectedProject.value?.enabled && days.value && !busy.value && !props.failed && !permissionUnavailable.value)
watch(() => props.projects, () => {
  const requested = props.projectId || (typeof route.query.project_id === "string" ? route.query.project_id : null)
  if (requested && props.projects.some(p => p.id === requested))
    projectId.value = requested
  else if (!projectId.value && props.projects.filter(p => p.enabled).length === 1)
    projectId.value = props.projects.find(p => p.enabled)!.id
}, { immediate: true })
function applyPreset(value: string) {
  preset.value = value
  selectedScopes.value = [...presets[value]]
}
watch(selectedScopes, (scopes) => {
  const required = new Set(["protocols:read", ...scopes])
  if (scopes.some(s => ["records:export", "analysis:read", "analysis:write"].includes(s))) {
    required.add("records:export")
    required.add("records:read")
  }
  if (scopes.some(s => ["records:revise", "records:complex"].includes(s)))
    required.add("records:read")
  if (scopes.some(s => ["protocols:candidate", "protocols:publish"].includes(s))) {
    required.add("protocols:source")
    required.add("protocols:candidate")
  }
  if (required.size !== scopes.length)
    selectedScopes.value = [...required]
})
async function create() {
  if (!canCreate.value)
    return
  busy.value = true
  try {
    const result = await createExternalGrant({ name: name.value.trim(), project_id: projectId.value!, scopes: selectedScopes.value, expires_in_days: days.value! })
    issuedProject.value = selectedProject.value!.name
    token.value = result.token
    emit("created")
  }
  catch { message.error($t("externalAccess.failed")) }
  finally { busy.value = false }
}
async function copy(value: string) {
  try {
    await copyToClip(value)
    message.success($t("externalAccess.copied"))
  }
  catch { message.error($t("externalAccess.failed")) }
}
async function testConnection() {
  checking.value = true
  connectionFailed.value = false
  connectionStatus.value = ""
  try {
    const response = await fetch("/api/external-access/tools/access_context", { method: "POST", headers: { "Authorization": `Bearer ${token.value}`, "Content-Type": "application/json" }, body: "{}" })
    if (!response.ok)
      throw new Error("Connection unavailable")
    const context = await response.json()
    connectionStatus.value = `${context.project.name} · ${context.instance.version} · ${context.scopes.map(scopeLabel).join(" · ")}`
  }
  catch { connectionFailed.value = true }
  finally { checking.value = false }
}
function dismiss() {
  token.value = ""
  connectionStatus.value = ""
  connectionFailed.value = false
}
onBeforeUnmount(dismiss)
</script>

<template>
  <div class="min-w-0 space-y-4" data-testid="external-connection-setup">
    <p class="text-sm color-text-secondary">
      {{ $t("externalOnboarding.steps") }}
    </p>
    <n-form v-if="!token" label-placement="top" @submit.prevent="create">
      <div class="grid gap-x-4 sm:grid-cols-2">
        <n-form-item :label="$t('externalAccess.project')">
          <div v-if="props.projectId" class="break-words font-medium" data-testid="external-fixed-project">
            {{ selectedProject?.name }}
          </div>
          <n-select v-else v-model:value="projectId" data-testid="external-grant-project" :options="projectOptions" filterable :placeholder="$t('externalAccess.projectHint')" />
        </n-form-item>
        <n-form-item :label="$t('externalAccess.name')">
          <n-input v-model:value="name" data-testid="external-grant-name" :maxlength="100" :placeholder="$t('externalAccess.nameHint')" />
        </n-form-item>
      </div>
      <n-alert v-if="selectedProject && !selectedProject.enabled" type="warning" class="mb-4">
        {{ $t("externalOnboarding.disabledHint") }}
      </n-alert>
      <n-form-item :label="$t('externalOnboarding.purpose')">
        <div class="grid w-full gap-2 sm:grid-cols-3">
          <n-button v-for="kind in ['read', 'analyze', 'author']" :key="kind" :data-testid="`external-preset-${kind}`" :aria-pressed="preset === kind" :type="preset === kind ? 'primary' : 'default'" :secondary="preset === kind" class="min-h-12 h-auto! whitespace-normal! py-2!" :disabled="(kind === 'analyze' && !selectedProject?.can_export) || (kind === 'author' && !selectedProject?.can_author)" @click="applyPreset(kind)">
            {{ $t(kind === 'read' ? 'externalOnboarding.read' : kind === 'analyze' ? 'externalOnboarding.analyze' : 'externalOnboarding.author') }}
          </n-button>
        </div>
      </n-form-item>
      <p class="mb-3 text-sm color-text-secondary">
        {{ $t("externalOnboarding.scopeHint") }}
      </p>
      <p class="mb-3 break-words" data-testid="external-selected-scopes">
        {{ selectedScopes.map(scopeLabel).join(' · ') }}
      </p>
      <n-collapse class="mb-4">
        <n-collapse-item :title="$t('externalOnboarding.customScopes')" name="scopes">
          <n-checkbox-group v-model:value="selectedScopes" class="flex flex-wrap gap-3" @update:value="preset = 'custom'">
            <n-checkbox v-for="option in scopeOptions" :key="option.value" :value="option.value" :disabled="option.disabled">
              {{ option.label }}
            </n-checkbox>
          </n-checkbox-group>
        </n-collapse-item>
      </n-collapse>
      <n-alert v-if="permissionUnavailable" type="warning" class="mb-4">
        {{ $t("externalOnboarding.permissionUnavailable") }}
      </n-alert>
      <n-form-item :label="$t('externalAccess.days')">
        <n-input-number v-model:value="days" :min="1" :max="90" class="max-w-60 w-full" />
      </n-form-item>
      <p class="mb-4 text-sm color-text-secondary">
        {{ $t("externalAccess.policyHint") }}
      </p>
      <n-button data-testid="external-grant-create" type="primary" :disabled="!canCreate" :loading="busy" attr-type="submit">
        {{ $t("externalAccess.create") }}
      </n-button>
    </n-form>
    <template v-else>
      <h3 class="text-base font-semibold">
        {{ $t("externalOnboarding.configure") }} · {{ issuedProject }}
      </h3>
      <n-alert type="warning">
        <p class="mb-2">
          {{ $t("externalAccess.oneTime") }}
        </p>
        <n-input data-testid="external-grant-token" :value="token" type="password" show-password-on="click" readonly :input-props="{ autocomplete: 'off' }" />
        <n-button class="mt-2" @click="copy(token)">
          {{ $t("externalAccess.copyToken") }}
        </n-button>
      </n-alert>
      <p>{{ $t("externalOnboarding.environmentHint") }}</p>
      <pre class="overflow-auto whitespace-pre-wrap break-all rounded bg-gray-100 p-3 text-sm dark:bg-gray-800">{{ command }}</pre>
      <div class="flex flex-wrap gap-3">
        <n-button @click="copy(command)">
          {{ $t("externalAccess.copyCommand") }}
        </n-button>
        <a :href="documentationUrl" target="_blank" rel="noopener" class="self-center underline">{{ $t("externalAccess.documentation") }}</a>
      </div>
      <details class="border rounded p-3">
        <summary class="cursor-pointer">
          {{ $t("externalOnboarding.otherClients") }}
        </summary>
        <p class="mt-2 break-all">
          {{ endpoint }}
        </p><p>{{ $t("externalOnboarding.otherClientsHint") }}</p>
      </details>
      <n-button data-testid="external-test-connection" :loading="checking" @click="testConnection">
        {{ $t("externalResearch.testConnection") }}
      </n-button>
      <n-alert v-if="connectionStatus" type="success" data-testid="external-connection-result">
        {{ $t("externalOnboarding.tokenVerified") }} {{ connectionStatus }}
      </n-alert>
      <n-alert v-if="connectionFailed" type="error">
        {{ $t("externalAccess.noLongerAvailable") }}
      </n-alert>
      <h3 class="text-base font-semibold">
        {{ $t("externalOnboarding.startTask") }}
      </h3>
      <p>{{ $t("externalOnboarding.firstTask") }}</p>
      <n-button @click="copy($t('externalOnboarding.firstTask'))">
        {{ $t("externalResearch.copyTask") }}
      </n-button>
      <p class="text-sm color-text-secondary">
        {{ $t("externalOnboarding.resultsHint") }}
      </p>
      <n-button @click="dismiss">
        {{ $t("externalAccess.dismissToken") }}
      </n-button>
    </template>
  </div>
</template>
