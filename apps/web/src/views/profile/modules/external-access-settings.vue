<script setup lang="ts">
import type { ExternalAnalysis, ExternalDashboard, ExternalOperation } from "@/service/api/external-access"
import { decideExternalOperation, deleteExternalOAuthClient, downloadExternalAnalysisFile, getExternalAnalysis, getExternalDashboard, getExternalOperation, listExternalOAuthClients, registerExternalOAuthClient, revokeExternalGrant } from "@/service/api/external-access"
import ExternalConnectionForm from "@/views/external-access/components/external-connection-form.vue"
import ExternalGuideLink from "@/views/external-access/components/external-guide-link.vue"
import { scopeLabel } from "@/views/external-access/components/project-coverage"
import { useClosableMessage } from "@airalogy/composables"
import { $t } from "@airalogy/shared/locales"
import { copyToClip } from "@airalogy/shared/utils"

const props = defineProps<{ projectId?: string }>()
const setupOpen = ref(false)
const connectionKey = ref(0)
const managementOpen = ref(false)
const showHistory = ref(false)
const reportSearch = ref("")
const detailError = ref(false)
const router = useRouter()
const message = useClosableMessage()
const route = useRoute()
const dashboard = ref<ExternalDashboard>({ projects: [], grants: [], operations: [], audit: [] })
const loading = ref(false)
const failed = ref(false)
const current = ref<ExternalOperation | null>(null)
const reviewed = ref(false)
const analysis = ref<ExternalAnalysis | null>(null)
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
const visibleOperations = computed(() => dashboard.value.operations.filter(item => showHistory.value || ["pending", "approved"].includes(item.state)))
const visibleAnalyses = computed(() => (dashboard.value.analyses || []).filter(item => item.title.toLocaleLowerCase().includes(reportSearch.value.trim().toLocaleLowerCase())))
const canDecide = computed(() => current.value?.state === "pending" && Date.parse(current.value.expires_at) > Date.now())

async function refresh() {
  loading.value = true
  failed.value = false
  try {
    dashboard.value = await getExternalDashboard(props.projectId)
  }
  catch {
    failed.value = true
    dashboard.value = { projects: [], grants: [], operations: [], audit: [] }
  }
  finally { loading.value = false }
}
async function revoke(id: string) {
  loading.value = true
  try {
    await revokeExternalGrant(id)
    connectionKey.value += 1
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
    detailError.value = false
    current.value = await getExternalOperation(id, props.projectId)
  }
  catch {
    detailError.value = true
    message.error($t("externalAccess.noLongerAvailable"))
  }
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
  catch {
    detailError.value = true
    message.error($t("externalAccess.noLongerAvailable"))
  }
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
    detailError.value = false
    analysis.value = await getExternalAnalysis(id, props.projectId)
  }
  catch {
    detailError.value = true
    message.error($t("externalAccess.noLongerAvailable"))
  }
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
  catch {
    detailError.value = true
    message.error($t("externalAccess.noLongerAvailable"))
  }
}
function downloadPreview(file: { filename: string, content_base64: string }) {
  const bytes = Uint8Array.from(atob(file.content_base64), char => char.charCodeAt(0))
  downloadBlob(new Blob([bytes], { type: "application/octet-stream" }), file.filename)
}
async function loadMore() {
  if (dashboard.value.analysis_next_offset == null || loading.value)
    return
  loading.value = true
  try {
    const next = await getExternalDashboard(props.projectId, dashboard.value.analysis_next_offset)
    const ids = new Set((dashboard.value.analyses || []).map(item => item.id))
    dashboard.value.analyses = [...(dashboard.value.analyses || []), ...(next.analyses || []).filter(item => !ids.has(item.id))]
    dashboard.value.analysis_next_offset = next.analysis_next_offset
  }
  catch { message.error($t("externalAccess.failed")) }
  finally { loading.value = false }
}
async function openFromRoute() {
  setupOpen.value = route.query.connect === "1"
  if (!route.query.analysis_id)
    analysis.value = null
  if (!route.query.operation_id)
    current.value = null
  if (typeof route.query.analysis_id === "string")
    await inspectAnalysis(route.query.analysis_id)
  if (typeof route.query.operation_id === "string")
    await inspect(route.query.operation_id)
}
function clearQuery(key: string) {
  if (key in route.query) {
    const query = { ...route.query }
    delete query[key]
    void router.replace({ path: route.path, query, hash: route.hash })
  }
}
watch(setupOpen, (value) => {
  if (!value)
    clearQuery("connect")
})
watch(() => [route.query.analysis_id, route.query.operation_id, route.query.connect], openFromRoute)
onMounted(async () => {
  await refresh()
  await openFromRoute()
  await nextTick()
  if (route.hash === "#external-access")
    document.getElementById("external-access")?.scrollIntoView({ block: "start" })
})
</script>

<template>
  <n-card id="external-access" :title="$t(props.projectId ? 'externalOnboarding.workspace' : 'externalAccess.title')" class="min-w-0 scroll-mt-24" data-testid="external-research-workspace">
    <template #header-extra>
      <n-button :loading="loading" :aria-label="$t('externalAccess.refresh')" @click="refresh">
        {{ $t("externalAccess.refresh") }}
      </n-button>
    </template>
    <div class="min-w-0 space-y-5">
      <p class="color-text-secondary">
        {{ $t("externalOnboarding.workspaceHint") }} <external-guide-link />
      </p>
      <n-alert v-if="failed" type="error">
        {{ $t("externalAccess.failed") }}
      </n-alert>
      <n-alert v-if="detailError" type="error" closable @close="detailError = false">
        {{ $t("externalAccess.noLongerAvailable") }}
      </n-alert>
      <div v-if="props.projectId" class="flex flex-wrap items-center gap-3">
        <n-button type="primary" data-testid="external-connect-project" :disabled="failed || loading" @click="setupOpen = true">
          {{ $t("externalResearch.connectProject") }}
        </n-button>
        <n-button quaternary data-testid="external-manage-connections" @click="managementOpen = !managementOpen">
          {{ $t("externalOnboarding.manageConnections") }}
        </n-button>
      </div>
      <template v-else>
        <p class="text-sm color-text-secondary">
          {{ $t("accountSettings.externalHint") }}
        </p>
        <external-connection-form :key="connectionKey" :organizations="dashboard.organizations" :projects="dashboard.projects" :failed="failed" @created="refresh" />
      </template>
      <section class="space-y-3">
        <div class="flex flex-wrap items-center justify-between gap-3">
          <h3 class="text-base font-semibold">
            {{ $t("externalAccess.operations") }}
          </h3>
          <n-checkbox v-model:checked="showHistory">
            {{ $t("externalOnboarding.showHistory") }}
          </n-checkbox>
        </div>
        <p v-if="!failed && !loading && !visibleOperations.length" class="text-sm color-text-secondary">
          {{ $t("externalAccess.emptyOperations") }}
        </p>
        <div v-for="operation in visibleOperations" :key="operation.id" :data-testid="`external-operation-${operation.id}`" class="flex flex-wrap items-center justify-between gap-3 border-b py-3">
          <div class="min-w-0 flex-1 break-all">
            {{ operation.kind === 'meeting_upload' ? $t('externalAccess.meetingUpload') : operation.kind === 'protocol' ? $t('externalResearch.protocolReview') : operation.kind === 'analysis' ? $t('externalResearch.writeAnalysis') : operation.kind === 'import' ? $t('externalAccess.importRecords') : $t('externalAccess.reviseRecords') }}
            <span class="ml-2">{{ states[operation.state] || operation.state }}</span>
            <div class="text-xs color-text-secondary">
              {{ operation.id }}
            </div>
          </div>
          <n-button :disabled="loading" @click="inspect(operation.id)">
            {{ $t("externalAccess.review") }}
          </n-button>
        </div>
      </section>
      <section v-if="props.projectId" class="space-y-3" data-testid="external-project-reports">
        <div class="flex flex-wrap items-center justify-between gap-3">
          <h3 class="text-base font-semibold">
            {{ $t("externalResearch.analyses") }}
          </h3>
          <n-input v-if="dashboard.analyses?.length" v-model:value="reportSearch" class="max-w-80" clearable :placeholder="$t('externalOnboarding.searchReports')" :aria-label="$t('externalOnboarding.searchReports')" />
        </div>
        <p class="text-sm color-text-secondary">
          {{ $t("externalResearch.privateResults") }}
        </p>
        <n-empty v-if="!failed && !loading && !visibleAnalyses.length" class="py-6" :description="$t(reportSearch ? 'externalOnboarding.noMatches' : 'externalOnboarding.emptyReports')" />
        <div v-for="run in visibleAnalyses" :key="run.id" :data-testid="`external-report-${run.id}`" class="flex flex-wrap items-center justify-between gap-3 border rounded p-4">
          <div class="min-w-0 flex-1 break-words">
            <p class="font-medium">
              {{ run.title }}
            </p>
            <p class="mt-1 text-sm color-text-secondary">
              {{ new Date(run.created_at).toLocaleString() }}
            </p>
          </div>
          <n-button :disabled="loading" @click="inspectAnalysis(run.id)">
            {{ $t("externalResearch.openResult") }}
          </n-button>
        </div>
        <n-button v-if="dashboard.analysis_next_offset != null" :loading="loading" @click="loadMore">
          {{ $t("externalOnboarding.loadMore") }}
        </n-button>
      </section>
      <section v-if="!props.projectId || managementOpen" data-testid="external-connection-management" class="border-t pt-4 space-y-4">
        <n-collapse v-if="!props.projectId" @update:expanded-names="refreshClients">
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
              <span v-if="grant.project_coverage === 'accessible'">{{ $t("accountSettings.ongoingProjects") }} · </span>
              <span v-else-if="grant.project_coverage === 'selected'">{{ $t("accountSettings.fixedCount", { count: grant.selected_project_ids?.length || 0 }) }} · </span>
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

        <n-collapse>
          <n-collapse-item :title="$t('externalAccess.audit')" name="audit">
            <div v-for="event in dashboard.audit" :key="event.id" class="flex flex-wrap justify-between gap-2 border-b py-2 text-sm">
              <span>{{ auditLabels[event.event] || $t('externalAccess.toolCalled') }}</span><span>{{ new Date(event.created_at).toLocaleString() }}</span>
            </div>
          </n-collapse-item>
        </n-collapse>
      </section>
    </div>
    <n-modal v-if="props.projectId" v-model:show="setupOpen" preset="card" :title="$t('externalResearch.connectProject')" class="max-h-[85vh] max-w-[calc(100vw-32px)] w-200 overflow-auto" :mask-closable="false">
      <external-connection-form :key="connectionKey" :project-id="props.projectId" :projects="dashboard.projects" :failed="failed" @created="refresh" />
    </n-modal>
    <n-modal :show="Boolean(current)" data-testid="external-operation-dialog" preset="card" :title="$t('externalAccess.review')" class="max-h-[85vh] max-w-[calc(100vw-32px)] w-200 overflow-auto" @update:show="value => { if (!value) { current = null; clearQuery('operation_id') } }">
      <div v-if="current" class="min-w-0 space-y-4">
        <n-alert type="warning">
          {{ $t("externalAccess.reviewHint") }}
        </n-alert>
        <p>{{ current.tool_name }} · {{ states[current.state] || current.state }}</p>
        <dl v-if="current.summary" class="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 break-words">
          <dt>{{ $t('externalAccess.destination') }}</dt><dd class="min-w-0">
            <template v-if="current.kind === 'meeting_upload'">
              <a :href="current.summary.meeting_url" target="_blank" rel="noopener noreferrer" class="text-primary underline">{{ current.summary.title }}</a>
              · v{{ current.summary.expected_version }} · {{ current.summary.filename }}
            </template>
            <template v-else>{{ current.summary.project_name }} / {{ current.summary.protocol_name }}</template>
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
        <section v-if="current.kind === 'meeting_upload'" class="space-y-2">
          <p>{{ $t(current.summary?.audience === 'participants' ? 'externalAccess.meetingParticipants' : current.summary?.audience === 'selected' ? 'externalAccess.meetingSelected' : 'externalAccess.meetingProject') }}</p>
          <pre v-if="current.payload" class="max-h-80 overflow-auto whitespace-pre-wrap break-words">{{ current.payload.content }}</pre>
        </section>
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
    <n-modal :show="Boolean(analysis)" preset="card" :title="$t('externalResearch.openResult')" class="max-h-[85vh] max-w-[calc(100vw-32px)] w-240 overflow-auto" @update:show="value => { if (!value) { analysis = null; clearQuery('analysis_id') } }">
      <div v-if="analysis" class="space-y-4" data-testid="external-analysis-report">
        <n-alert type="info">
          {{ $t("externalResearch.externalExecution") }}
        </n-alert>
        <h2 class="break-words text-xl font-semibold">
          {{ analysis.result.title }}
        </h2>
        <p class="text-sm color-text-secondary">
          {{ new Date(analysis.created_at).toLocaleString() }} · {{ $t("externalResearch.privateResults") }}
        </p>
        <p>{{ analysis.question }}</p>
        <n-alert v-if="analysis.result.reproducibility === 'incomplete'" type="warning">
          {{ $t("externalResearch.incomplete") }}
        </n-alert>
        <div class="max-h-120 overflow-auto whitespace-pre-wrap break-words text-base leading-relaxed" data-testid="external-report-body">
          {{ analysis.result.report }}
        </div>
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
