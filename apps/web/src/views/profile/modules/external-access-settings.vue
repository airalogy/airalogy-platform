<script setup lang="ts">
import type { ExternalAnalysis, ExternalDashboard, ExternalOperation } from "@/service/api/external-access"
import { createExternalGrant, decideExternalOperation, deleteExternalOAuthClient, downloadExternalAnalysisFile, getExternalAnalysis, getExternalDashboard, getExternalOperation, listExternalOAuthClients, registerExternalOAuthClient, revokeExternalGrant } from "@/service/api/external-access"
import { useAppStore } from "@/store/modules/app"
import { useInstanceStore } from "@/store/modules/instance"
import { useClosableMessage } from "@airalogy/composables"
import { $t } from "@airalogy/shared/locales"
import { copyToClip, documentationPageUrl } from "@airalogy/shared/utils"

const message = useClosableMessage()
const route = useRoute()
const appStore = useAppStore()
const instanceStore = useInstanceStore()
const documentationUrl = computed(() => documentationPageUrl(instanceStore.documentationUrl, appStore.locale, "external-agent-access"))
const dashboard = ref<ExternalDashboard>({ projects: [], grants: [], operations: [], audit: [] })
const loading = ref(false)
const failed = ref(false)
const name = ref("")
const projectId = ref<string | null>(null)
const days = ref<number | null>(7)
const selectedScopes = ref<string[]>(["protocols:read", "records:read"])
const token = ref("")
const current = ref<ExternalOperation | null>(null)
const reviewed = ref(false)
const analysis = ref<ExternalAnalysis | null>(null)
const connectionStatus = ref("")
const clientName = ref("")
const clientRedirect = ref("")
const clients = ref<Array<{ client_id: string, name: string, redirect_uris: string[] }>>([])
async function refreshClients() {
  try {
    clients.value = (await listExternalOAuthClients()).items
  }
  catch { message.error($t("externalAccess.failed")) }
}
async function registerClient() {
  loading.value = true
  try {
    await registerExternalOAuthClient(clientName.value, clientRedirect.value)
    clientName.value = ""
    await refreshClients()
  }
  catch { message.error($t("externalAccess.failed")) }
  finally { loading.value = false }
}
async function removeClient(id: string) {
  try {
    await deleteExternalOAuthClient(id)
    await refreshClients()
    await refresh()
  }
  catch { message.error($t("externalAccess.failed")) }
}
const endpoint = `${window.location.origin}/api/mcp`
const command = `codex mcp add airalogy --url ${JSON.stringify(endpoint)} --bearer-token-env-var AIRALOGY_PLATFORM_TOKEN`
const projectOptions = computed(() => dashboard.value.projects.map(p => ({ value: p.id, label: `${p.name}${p.enabled ? "" : ` — ${$t("externalAccess.labDisabled")}`}`, disabled: !p.enabled })))
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
// Show all required permissions before the user creates a credential.
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
const states = computed<Record<string, string>>(() => ({
  pending: $t("externalAccess.pending"),
  approved: $t("externalAccess.approved"),
  succeeded: $t("externalAccess.succeeded"),
  rejected: $t("externalAccess.rejected"),
  expired: $t("externalAccess.expired"),
  revoked: $t("externalAccess.revoked"),
}))
const auditLabels = computed<Record<string, string>>(() => ({
  "grant.created": $t("externalAccess.grantCreated"),
  "grant.revoked": $t("externalAccess.revoked"),
  "policy.updated": $t("externalAccess.saved"),
  "operation.previewed": $t("externalAccess.pending"),
  "operation.approved": $t("externalAccess.approved"),
  "operation.rejected": $t("externalAccess.rejected"),
  "operation.executed": $t("externalAccess.succeeded"),
  "tool.denied": $t("externalAccess.accessDenied"),
}))
function scopeLabel(scope: string) {
  return scopeOptions.value.find(option => option.value === scope)?.label || scope
}
const canCreate = computed(() => name.value.trim() && projectId.value && days.value && !loading.value && !failed.value)
const canDecide = computed(() => current.value?.state === "pending" && Date.parse(current.value.expires_at) > Date.now())

async function refresh() {
  loading.value = true
  failed.value = false
  try {
    dashboard.value = await getExternalDashboard()
    const requested = typeof route.query.project_id === "string" ? route.query.project_id : null
    if (!projectId.value && requested && dashboard.value.projects.some(p => p.id === requested))
      projectId.value = requested
    const enabled = dashboard.value.projects.filter(p => p.enabled)
    if (!projectId.value && enabled.length === 1)
      projectId.value = enabled[0].id
  }
  catch { failed.value = true }
  finally { loading.value = false }
}
async function create() {
  if (!canCreate.value)
    return
  loading.value = true
  token.value = ""
  try {
    const scopes = selectedScopes.value
    const result = await createExternalGrant({ name: name.value.trim(), project_id: projectId.value!, scopes, expires_in_days: days.value! })
    token.value = result.token
    name.value = ""
    await refresh()
  }
  catch { message.error($t("externalAccess.failed")) }
  finally { loading.value = false }
}
async function revoke(id: string) {
  loading.value = true
  try {
    await revokeExternalGrant(id)
    token.value = ""
    connectionStatus.value = ""
    await refresh()
  }
  catch { message.error($t("externalAccess.failed")) }
  finally { loading.value = false }
}
async function inspect(id: string) {
  loading.value = true
  reviewed.value = false
  current.value = null
  try {
    current.value = await getExternalOperation(id)
  }
  catch { message.error($t("externalAccess.noLongerAvailable")) }
  finally { loading.value = false }
}
async function decide(approve: boolean) {
  if (!current.value?.digest || (approve && !reviewed.value))
    return
  loading.value = true
  try {
    current.value = await decideExternalOperation(current.value.id, current.value.digest, approve)
    message.success($t(approve ? "externalAccess.approvedHint" : "externalAccess.rejected"))
    await refresh()
  }
  catch { message.error($t("externalAccess.noLongerAvailable")) }
  finally { loading.value = false }
}
async function copy(value: string) {
  try {
    await copyToClip(value)
    message.success($t("externalAccess.copied"))
  }
  catch { message.error($t("externalAccess.failed")) }
}
async function inspectAnalysis(id: string) {
  analysis.value = null
  try {
    analysis.value = await getExternalAnalysis(id)
  }
  catch { message.error($t("externalAccess.noLongerAvailable")) }
}
function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement("a")
  link.href = url
  link.download = filename
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
async function downloadResult(file: { id: string, filename: string }) {
  if (!analysis.value)
    return
  try {
    downloadBlob(await downloadExternalAnalysisFile(analysis.value.id, file.id), file.filename)
  }
  catch { message.error($t("externalAccess.noLongerAvailable")) }
}
function downloadPreview(file: { filename: string, content_base64: string }) {
  const bytes = Uint8Array.from(atob(file.content_base64), char => char.charCodeAt(0))
  downloadBlob(new Blob([bytes], { type: "application/octet-stream" }), file.filename)
}
async function testConnection() {
  connectionStatus.value = ""
  try {
    const response = await fetch("/api/external-access/tools/access_context", {
      method: "POST",
      headers: { "Authorization": `Bearer ${token.value}`, "Content-Type": "application/json" },
      body: "{}",
    })
    if (!response.ok)
      throw new Error("Connection unavailable")
    const context = await response.json()
    connectionStatus.value = `${context.project.name} · ${context.instance.version} · ${context.scopes.map(scopeLabel).join(" · ")}`
  }
  catch { message.error($t("externalAccess.noLongerAvailable")) }
}
onMounted(async () => {
  await refresh()
  if (typeof route.query.analysis_id === "string")
    await inspectAnalysis(route.query.analysis_id)
  await nextTick()
  if (route.hash === "#external-access")
    document.getElementById("external-access")?.scrollIntoView({ block: "start" })
})
onBeforeUnmount(() => {
  token.value = ""
  current.value = null
})
</script>

<template>
  <n-card id="external-access" :title="$t('externalAccess.title')" class="min-w-0 scroll-mt-24">
    <div class="min-w-0 space-y-4">
      <n-alert type="info" :show-icon="false">
        {{ $t("externalAccess.description") }}
      </n-alert>
      <n-button :loading="loading" @click="refresh">
        {{ $t("externalAccess.refresh") }}
      </n-button>
      <n-alert v-if="failed" type="error">
        {{ $t("externalAccess.failed") }}
      </n-alert>
      <n-form label-placement="top" @submit.prevent="create">
        <div class="grid gap-x-4 sm:grid-cols-2">
          <n-form-item :label="$t('externalAccess.name')">
            <n-input v-model:value="name" data-testid="external-grant-name" :maxlength="100" :placeholder="$t('externalAccess.nameHint')" />
          </n-form-item>
          <n-form-item :label="$t('externalAccess.project')">
            <n-select v-model:value="projectId" data-testid="external-grant-project" :options="projectOptions" filterable :placeholder="$t('externalAccess.projectHint')" />
          </n-form-item>
          <n-form-item :label="$t('externalAccess.days')">
            <n-input-number v-model:value="days" :min="1" :max="90" class="w-full" />
          </n-form-item>
          <n-form-item :label="$t('externalAccess.scopes')">
            <n-checkbox-group v-model:value="selectedScopes" class="flex flex-wrap gap-2">
              <n-checkbox v-for="option in scopeOptions" :key="option.value" :value="option.value" :disabled="option.disabled">
                {{ option.label }}
              </n-checkbox>
            </n-checkbox-group>
          </n-form-item>
        </div>
        <p class="mb-3 text-sm color-text-secondary">
          {{ $t("externalAccess.policyHint") }}
        </p>
        <n-button data-testid="external-grant-create" type="primary" :disabled="!canCreate" :loading="loading" attr-type="submit">
          {{ $t("externalAccess.create") }}
        </n-button>
      </n-form>
      <n-alert v-if="token" type="warning">
        <p class="mb-2">
          {{ $t("externalAccess.oneTime") }}
        </p>
        <n-input data-testid="external-grant-token" :value="token" type="password" show-password-on="click" readonly :input-props="{ autocomplete: 'off' }" />
        <div class="mt-2 flex flex-wrap gap-2">
          <n-button @click="copy(token)">
            {{ $t("externalAccess.copyToken") }}
          </n-button>
          <n-button data-testid="external-test-connection" @click="testConnection">
            {{ $t("externalResearch.testConnection") }}
          </n-button>
          <n-button @click="token = ''; connectionStatus = ''">
            {{ $t("externalAccess.dismissToken") }}
          </n-button>
        </div>
      </n-alert>
      <n-alert v-if="connectionStatus" type="success" data-testid="external-connection-result">
        {{ connectionStatus }}
      </n-alert>
      <n-collapse>
        <n-collapse-item :title="$t('externalAccess.connect')" name="connect">
          <p>{{ $t("externalAccess.connectHint") }}</p>
          <p class="my-3">
            {{ $t("externalResearch.taskExample") }}
          </p>
          <n-button @click="copy($t('externalResearch.taskExample'))">
            {{ $t("externalResearch.copyTask") }}
          </n-button>
          <pre class="my-2 overflow-auto whitespace-pre-wrap break-all rounded bg-gray-100 p-3 text-sm dark:bg-gray-800">{{ command }}</pre>
          <n-button @click="copy(command)">
            {{ $t("externalAccess.copyCommand") }}
          </n-button>
          <a :href="documentationUrl" target="_blank" rel="noopener" class="ml-3 underline">{{ $t("externalAccess.documentation") }}</a>
        </n-collapse-item>
      </n-collapse>
      <n-collapse @update:expanded-names="refreshClients">
        <n-collapse-item :title="$t('externalResearch.oauthClients')" name="oauth">
          <p>{{ $t("externalResearch.oauthRegistration") }}</p>
          <n-form label-placement="top" @submit.prevent="registerClient">
            <n-form-item :label="$t('externalAccess.name')">
              <n-input v-model:value="clientName" :maxlength="100" />
            </n-form-item>
            <n-form-item :label="$t('externalResearch.redirectUri')">
              <n-input v-model:value="clientRedirect" :maxlength="2048" placeholder="http://127.0.0.1:8765/callback" />
            </n-form-item>
            <n-button attr-type="submit" :disabled="!clientName.trim() || !clientRedirect.trim()" :loading="loading">
              {{ $t("externalResearch.registerClient") }}
            </n-button>
          </n-form>
          <div v-for="client in clients" :key="client.client_id" class="my-3 break-all space-y-2">
            <p>{{ client.name }} · {{ client.redirect_uris.join(' · ') }}</p>
            <p>Client ID: {{ client.client_id }}</p>
            <n-popconfirm @positive-click="removeClient(client.client_id)">
              {{ $t("externalResearch.removeClientHint") }}
              <template #trigger>
                <n-button type="error" secondary>
                  {{ $t("externalAccess.revoke") }}
                </n-button>
              </template>
            </n-popconfirm>
          </div>
        </n-collapse-item>
      </n-collapse>
      <h3 class="text-base font-semibold">
        {{ $t("externalAccess.grants") }}
      </h3>
      <n-empty v-if="!dashboard.grants.length" :description="$t('externalAccess.emptyGrants')" />
      <div v-for="grant in dashboard.grants" :key="grant.id" :data-testid="`external-grant-${grant.id}`" class="flex flex-wrap items-center justify-between gap-3 border-b py-3">
        <div class="min-w-0 flex-1 break-words">
          <div class="font-medium">
            {{ grant.name }}
          </div>
          <div class="text-sm color-text-secondary">
            {{ grant.scopes.map(scopeLabel).join(' · ') }}
          </div>
          <div class="text-sm color-text-secondary">
            {{ grant.token_prefix }}… · {{ $t("externalAccess.expires") }} {{ new Date(grant.expires_at).toLocaleString() }}
          </div>
        </div>
        <n-tag v-if="grant.revoked_at">
          {{ $t("externalAccess.revoked") }}
        </n-tag>
        <n-popconfirm v-else @positive-click="revoke(grant.id)">
          {{ $t("externalAccess.revokeConfirm") }}
          <template #trigger>
            <n-button type="error" secondary :disabled="loading">
              {{ $t("externalAccess.revoke") }}
            </n-button>
          </template>
        </n-popconfirm>
      </div>
      <h3 class="text-base font-semibold">
        {{ $t("externalResearch.analyses") }}
      </h3>
      <p class="text-sm color-text-secondary">
        {{ $t("externalResearch.privateResults") }}
      </p>
      <div v-for="run in (dashboard.analyses || []).filter(item => !projectId || item.project_id === projectId)" :key="run.id" class="flex flex-wrap items-center justify-between gap-3 border-b py-3">
        <span>{{ run.title }}</span><n-button @click="inspectAnalysis(run.id)">
          {{ $t("externalResearch.openResult") }}
        </n-button>
      </div>
      <h3 class="text-base font-semibold">
        {{ $t("externalAccess.operations") }}
      </h3>
      <n-empty v-if="!dashboard.operations.length" :description="$t('externalAccess.emptyOperations')" />
      <div v-for="operation in dashboard.operations" :key="operation.id" :data-testid="`external-operation-${operation.id}`" class="flex flex-wrap items-center justify-between gap-3 border-b py-3">
        <div class="min-w-0 flex-1 break-all">
          {{ operation.kind === 'protocol' ? $t('externalResearch.protocolReview') : operation.kind === 'analysis' ? $t('externalResearch.writeAnalysis') : operation.kind === 'import' ? $t('externalAccess.importRecords') : $t('externalAccess.reviseRecords') }}
          <span class="ml-2">{{ states[operation.state] || operation.state }}</span>
          <div class="text-xs color-text-secondary">
            {{ operation.id }}
          </div>
        </div>
        <n-button :disabled="loading" @click="inspect(operation.id)">
          {{ $t("externalAccess.review") }}
        </n-button>
      </div>
      <n-collapse>
        <n-collapse-item :title="$t('externalAccess.audit')" name="audit">
          <div v-for="event in dashboard.audit" :key="event.id" class="flex flex-wrap justify-between gap-2 border-b py-2 text-sm">
            <span>{{ auditLabels[event.event] || $t('externalAccess.toolCalled') }}</span><span>{{ new Date(event.created_at).toLocaleString() }}</span>
          </div>
        </n-collapse-item>
      </n-collapse>
    </div>
    <n-modal :show="Boolean(current)" data-testid="external-operation-dialog" preset="card" :title="$t('externalAccess.review')" class="max-w-[calc(100vw-32px)] w-200" @update:show="value => { if (!value) current = null }">
      <div v-if="current" class="min-w-0 space-y-4">
        <n-alert type="warning">
          {{ $t("externalAccess.reviewHint") }}
        </n-alert>
        <p>{{ current.tool_name }} · {{ states[current.state] || current.state }}</p>
        <dl v-if="current.summary" class="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 break-words">
          <dt>{{ $t('externalAccess.destination') }}</dt><dd class="min-w-0">
            {{ current.summary.project_name }} / {{ current.summary.protocol_name }}
          </dd>
          <template v-if="current.summary.row_count !== undefined">
            <dt>{{ $t(current.kind === 'analysis' ? 'externalResearch.exportedRows' : 'externalAccess.rowCount') }}</dt><dd>{{ current.summary.row_count }}</dd>
          </template>
          <template v-if="current.summary.protocol_version">
            <dt>{{ $t('externalAccess.protocolVersion') }}</dt><dd>{{ current.summary.protocol_version }}</dd>
          </template>
          <template v-if="current.summary.record_id">
            <dt>Record</dt><dd class="min-w-0 break-all">
              {{ current.summary.record_id }} · v{{ current.summary.expected_version }}
            </dd>
          </template>
          <dt>{{ $t('externalAccess.expires') }}</dt><dd>{{ new Date(current.expires_at).toLocaleString() }}</dd>
        </dl>
        <div v-if="current.summary?.changes" class="max-h-80 overflow-auto">
          <n-table size="small">
            <thead><tr><th>{{ $t('externalAccess.field') }}</th><th>{{ $t('externalAccess.before') }}</th><th>{{ $t('externalAccess.after') }}</th></tr></thead>
            <tbody>
              <tr v-for="(change, field) in current.summary.changes" :key="field">
                <td>{{ field }}</td><td class="max-w-60 whitespace-pre-wrap break-all">
                  {{ JSON.stringify(change.before) }}
                </td><td class="max-w-60 whitespace-pre-wrap break-all">
                  {{ JSON.stringify(change.after) }}
                </td>
              </tr>
            </tbody>
          </n-table>
          <p class="mt-3 whitespace-pre-wrap break-words">
            {{ $t('externalAccess.reason') }}: {{ current.summary.reason }}
          </p>
        </div>
        <section v-if="current.kind === 'protocol'" class="space-y-3" data-testid="external-protocol-preview">
          <n-alert type="warning">
            {{ $t("externalResearch.protocolHint") }}
          </n-alert>
          <p>{{ current.summary?.base_version || '—' }} → {{ current.summary?.version }}</p>
          <p class="break-all">
            {{ current.summary?.source_digest }}
          </p>
          <h3>{{ $t("externalResearch.diff") }}</h3>
          <div v-for="change in current.summary?.file_changes" :key="change.path">
            <h4>{{ change.path }} · {{ change.status }}</h4>
            <pre class="max-h-96 overflow-auto whitespace-pre-wrap break-all">{{ change.diff }}</pre>
          </div>
          <n-button v-for="(encoded, filename) in current.payload?.binary_files" :key="filename" @click="downloadPreview({ filename, content_base64: encoded })">
            {{ filename }}
          </n-button>
          <h3>{{ $t("externalResearch.compatibility") }}</h3>
          <pre class="max-h-80 overflow-auto whitespace-pre-wrap break-all">{{ JSON.stringify(current.summary?.compatibility, null, 2) }}</pre>
        </section>
        <section v-if="current.kind === 'analysis'" class="space-y-3" data-testid="external-analysis-preview">
          <n-alert type="info">
            {{ $t("externalResearch.externalExecution") }}
          </n-alert>
          <h3>{{ current.summary?.title }}</h3>
          <p>{{ $t("externalResearch.snapshot") }}: {{ current.summary?.snapshot_id }}</p>
          <p class="break-all">
            {{ current.summary?.snapshot_digest }}
          </p>
          <n-alert v-if="current.summary?.reproducibility === 'incomplete'" type="warning">
            {{ $t("externalResearch.incomplete") }}
          </n-alert>
          <pre class="max-h-96 overflow-auto whitespace-pre-wrap break-words">{{ current.payload?.report }}</pre>
          <h4>{{ $t("externalResearch.method") }}</h4>
          <pre class="max-h-64 overflow-auto whitespace-pre-wrap break-words">{{ current.payload?.method }}
          {{ JSON.stringify(current.payload?.environment, null, 2) }}</pre>
          <p class="whitespace-pre-wrap">
            {{ current.payload?.limitations }}
          </p>
          <n-button v-for="file in current.payload?.files" :key="file.filename" class="mr-2" @click="downloadPreview(file)">
            {{ file.filename }}
          </n-button>
        </section>
        <n-input v-if="current.payload?.csv" :value="current.payload.csv" type="textarea" readonly :autosize="{ minRows: 4, maxRows: 14 }" />
        <div v-if="current.result?.links" class="flex flex-col gap-2">
          <router-link v-for="link in current.result.links" :key="link" :to="link" class="break-all underline">
            {{ $t("externalResearch.openResult") }}
          </router-link>
        </div>
        <template v-if="canDecide">
          <n-checkbox v-model:checked="reviewed">
            {{ $t("externalAccess.reviewed") }}
          </n-checkbox>
          <div class="flex flex-wrap justify-end gap-3">
            <n-button :disabled="loading" @click="decide(false)">
              {{ $t("externalAccess.reject") }}
            </n-button>
            <n-button type="primary" :disabled="!reviewed || loading" :loading="loading" @click="decide(true)">
              {{ $t("externalAccess.approve") }}
            </n-button>
          </div>
        </template>
        <p v-else-if="current.state === 'approved'">
          {{ $t("externalAccess.approvedHint") }}
        </p>
      </div>
    </n-modal>
    <n-modal :show="Boolean(analysis)" preset="card" :title="$t('externalResearch.openResult')" class="max-w-[calc(100vw-32px)] w-240" @update:show="value => { if (!value) analysis = null }">
      <div v-if="analysis" class="space-y-4" data-testid="external-analysis-report">
        <n-alert type="info">
          {{ $t("externalResearch.externalExecution") }}
        </n-alert>
        <h2>{{ analysis.result.title }}</h2>
        <p>{{ analysis.question }}</p>
        <n-alert v-if="analysis.result.reproducibility === 'incomplete'" type="warning">
          {{ $t("externalResearch.incomplete") }}
        </n-alert>
        <pre class="max-h-120 overflow-auto whitespace-pre-wrap break-words">{{ analysis.result.report }}</pre>
        <h3>{{ $t("externalResearch.method") }} <span v-if="analysis.result.method">v{{ analysis.result.method.revision }}</span></h3>
        <pre class="max-h-80 overflow-auto whitespace-pre-wrap break-words">{{ analysis.recipe.method }}
        {{ JSON.stringify(analysis.recipe.environment, null, 2) }}</pre>
        <p class="whitespace-pre-wrap">
          {{ analysis.result.limitations }}
        </p>
        <div class="flex flex-wrap gap-2">
          <n-button v-for="file in analysis.result.files" :key="file.id" @click="downloadResult(file)">
            {{ file.filename }}
          </n-button>
        </div>
        <n-collapse>
          <n-collapse-item :title="$t('externalResearch.snapshot')" name="sources">
            <pre class="max-h-96 overflow-auto whitespace-pre-wrap break-all">{{ JSON.stringify(analysis.source_snapshot, null, 2) }}</pre>
          </n-collapse-item>
        </n-collapse>
        <n-button @click="copy($t('externalResearch.rerunTask', { id: analysis.id }))">
          {{ $t("externalResearch.rerun") }}
        </n-button>
      </div>
    </n-modal>
  </n-card>
</template>
