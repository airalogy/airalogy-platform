<script setup lang="ts">
import type { ExternalDashboard } from "@/service/api/external-access"
import type { ProjectTarget } from "@/views/external-access/components/project-coverage"
import { useRouterPush } from "@/composables/useRouterPush"
import { consentExternalOAuth, getExternalDashboard, readExternalOAuthRequest } from "@/service/api/external-access"
import { useAuthStore } from "@/store/modules/auth"
import ExternalGuideLink from "@/views/external-access/components/external-guide-link.vue"
import GrantDuration from "@/views/external-access/components/grant-duration.vue"
import { canRegisterAndLink, contractReceiptScopes, coveredProjects, eligibleScope, projectTarget, scopeLabel } from "@/views/external-access/components/project-coverage"
import ProjectCoveragePicker from "@/views/external-access/components/project-coverage-picker.vue"
import { $t } from "@airalogy/shared/locales"

const route = useRoute()
const auth = useAuthStore()
const { routerPushByKey } = useRouterPush()
const info = ref<Awaited<ReturnType<typeof readExternalOAuthRequest>>>()
const organizationMode = ref(false)
const dashboard = ref<ExternalDashboard>()
const projectId = ref<string | null>(null)
const target = ref<ProjectTarget>({ mode: "single", organization: null, ids: [] })
const destinations = computed(() => coveredProjects(target.value, projectId.value, dashboard.value?.projects || []))
const hasTarget = computed(() => organizationMode.value ? Boolean(projectId.value) : destinations.value.length > 0)
const hasOrganizationScopes = computed(() => info.value?.scopes.some(s => s.startsWith("projects:")))
const hasProjectScopes = computed(() => info.value?.scopes.some(s => !s.startsWith("projects:")))
const projects = computed(() => (organizationMode.value ? dashboard.value?.organizations?.filter(o => o.can_register !== false) || [] : dashboard.value?.projects || []).filter(p => p.enabled).map(p => ({ value: p.id, label: p.name })))
const requestedScopes = computed(() => info.value?.scopes.filter(s => s.startsWith("projects:") === organizationMode.value) || [])
const approvedScopes = ref<string[]>([])
const reviewed = ref(false)
function eligible(scope: string) {
  return organizationMode.value || eligibleScope(scope, destinations.value, target.value.mode === "accessible")
}
const showContractPreset = computed(() => !organizationMode.value && requestedScopes.value.some(s => contractReceiptScopes.includes(s)))
const sameTargetGrants = computed(() => {
  if (!hasTarget.value || !showContractPreset.value)
    return []
  const selected = projectTarget(target.value, projectId.value)
  return (info.value?.prior_grants || []).filter((grant) => {
    const ids = grant.selected_project_ids || []
    const targetIds = selected.selected_project_ids || []
    return (grant.project_id ?? undefined) === selected.project_id
      && (grant.organization_id ?? undefined) === selected.organization_id
      && (grant.project_coverage ?? undefined) === selected.project_coverage
      && ids.length === targetIds.length && ids.every(id => targetIds.includes(id))
  })
})
const sourceId = ref<string | null>(null)
const newGrant = "new"
const original = computed(() => sameTargetGrants.value.find(g => g.id === sourceId.value))
const sourceOptions = computed(() => [
  ...sameTargetGrants.value.map(g => ({ value: g.id, label: `#${g.id.slice(0, 8)} · ${g.scopes.map(scopeLabel).join(" · ")}` })),
  { value: newGrant, label: $t("externalAccess.startFresh") },
])
watch(sameTargetGrants, (grants) => {
  sourceId.value = grants.length === 1 ? grants[0].id : grants.length ? null : newGrant
}, { immediate: true })
const baseline = computed(() => original.value?.scopes || [])
const additions = computed(() => contractReceiptScopes.filter(s => !baseline.value.includes(s)))
const presetScopes = computed(() => [...new Set([...baseline.value, ...contractReceiptScopes])])
const missingClientScopes = computed(() => presetScopes.value.filter(s => !requestedScopes.value.includes(s)))
const missingAccountScopes = computed(() => presetScopes.value.filter(s => !eligible(s)))
const canSelectContractPreset = computed(() => hasTarget.value && sourceId.value !== null && !missingClientScopes.value.length && !missingAccountScopes.value.length && canRegisterAndLink(destinations.value, target.value.mode === "accessible"))
watch(projects, (items) => {
  projectId.value = items.length === 1 ? items[0].value : null
})
const sourceReady = computed(() => !showContractPreset.value || (sourceId.value !== null && baseline.value.every(s => approvedScopes.value.includes(s))))
function setScopes(scopes: string[]) {
  approvedScopes.value = [...new Set([...baseline.value.filter(s => requestedScopes.value.includes(s) && eligible(s)), ...scopes])]
}
function applyPreset() {
  if (!canSelectContractPreset.value)
    return
  approvedScopes.value = presetScopes.value
}
watch([requestedScopes, projectId, target, sourceId], () => {
  approvedScopes.value = sameTargetGrants.value.length && sourceId.value !== newGrant
    ? baseline.value.filter(s => requestedScopes.value.includes(s) && eligible(s))
    : requestedScopes.value.filter(s => eligible(s) && !["contracts:read", "contracts:create", "cash:link"].includes(s))
  reviewed.value = false
})
watch(approvedScopes, () => {
  reviewed.value = false
})
const days = ref<number | null>(1)
watch(days, () => {
  reviewed.value = false
})
const busy = ref(false)
const failed = ref(false)
const fields = ["response_type", "client_id", "redirect_uri", "state", "scope", "resource", "code_challenge", "code_challenge_method"]
const params = computed(() => Object.fromEntries(fields.map(key => [key, typeof route.query[key] === "string" ? route.query[key] : ""])))
async function load() {
  if (!auth.token) {
    void routerPushByKey("login", { query: { redirect: route.fullPath } })
    return
  }
  busy.value = true
  failed.value = false
  try {
    info.value = await readExternalOAuthRequest(params.value)
    dashboard.value = await getExternalDashboard()
    organizationMode.value = Boolean(hasOrganizationScopes.value && !hasProjectScopes.value)
  }
  catch { failed.value = true }
  finally { busy.value = false }
}
async function decide(approve: boolean) {
  if (!info.value || (approve && (!sourceReady.value || !reviewed.value || !hasTarget.value || !days.value)))
    return
  busy.value = true
  try {
    const result = await consentExternalOAuth({ ...params.value, approve, prior_grant_id: approve ? original.value?.id : undefined, approved_scopes: approve ? approvedScopes.value : undefined, ...(organizationMode.value ? { organization_id: projectId.value } : projectTarget(target.value, projectId.value)), expires_in_days: days.value })
    // Server has validated this exact registered callback. Never redirect to a raw query value.
    window.location.assign(result.redirect_to)
  }
  catch { failed.value = true }
  finally { busy.value = false }
}
onMounted(load)
</script>

<template>
  <main class="mx-auto max-w-2xl min-h-screen p-4 sm:p-8">
    <n-card :title="$t('externalResearch.oauthConsent')">
      <template #header-extra>
        <external-guide-link />
      </template>
      <n-alert v-if="failed" type="error">
        {{ $t("externalAccess.failed") }}
      </n-alert>
      <div v-if="info" class="space-y-4">
        <h2 class="text-lg font-semibold">
          {{ info.client_name }}
        </h2>
        <p class="break-all">
          {{ info.redirect_uri }}
        </p>
        <p class="break-all">
          {{ info.resource }}
        </p>
        <p>{{ auth.userInfo.name || auth.userInfo.username }}</p>
        <n-alert type="warning">
          {{ $t("externalResearch.oauthWarning") }}
        </n-alert>
        <n-radio-group v-if="hasProjectScopes && hasOrganizationScopes" v-model:value="organizationMode" :aria-label="$t('externalAccess.target')">
          <n-radio-button :value="false">
            {{ $t("externalAccess.project") }}
          </n-radio-button>
          <n-radio-button :value="true">
            {{ $t("externalAccess.organizationProjects") }}
          </n-radio-button>
        </n-radio-group>
        <n-form-item :label="$t(organizationMode ? 'externalAccess.organization' : 'externalAccess.project')">
          <n-select v-if="organizationMode" v-model:value="projectId" :options="projects" />
          <project-coverage-picker v-else v-model="target" :projects="dashboard?.projects || []" :organizations="dashboard?.organizations">
            <n-select v-model:value="projectId" data-testid="oauth-project" :options="projects" :aria-label="$t('externalAccess.project')" />
          </project-coverage-picker>
        </n-form-item>
        <n-form-item :label="$t('externalResearch.oauthDays')">
          <grant-duration v-model="days" :max="7" />
        </n-form-item>
        <div class="flex flex-wrap items-center gap-3">
          <h3>{{ $t("externalAccess.scopes") }}</h3>
          <n-button text type="primary" :disabled="!hasTarget" @click="setScopes(requestedScopes.filter(eligible))">
            {{ $t("accountSettings.allScopes") }}
          </n-button>
          <n-button text :disabled="!approvedScopes.some(s => !baseline.includes(s))" @click="setScopes([])">
            {{ $t("accountSettings.clear") }}
          </n-button>
        </div>
        <div v-if="showContractPreset" class="space-y-1">
          <n-form-item v-if="sameTargetGrants.length" :label="$t('externalAccess.originalConnection')">
            <n-select v-model:value="sourceId" data-testid="oauth-source" :options="sourceOptions" :placeholder="$t('externalAccess.chooseConnection')" />
          </n-form-item>
          <template v-if="original">
            <p>{{ $t("externalAccess.keepScopes", { scopes: baseline.map(scopeLabel).join(" · ") }) }}</p>
            <p v-if="additions.length">
              {{ $t("externalAccess.addScopes", { scopes: additions.map(scopeLabel).join(" · ") }) }}
            </p>
          </template>
          <n-button data-testid="oauth-contract-receipt" :disabled="!canSelectContractPreset" @click="applyPreset">
            {{ $t("externalAccess.contractReceiptPreset") }}
          </n-button>
          <p v-if="missingClientScopes.length" class="break-words text-sm" role="status">
            {{ $t("externalAccess.clientMissingScopes", { scopes: missingClientScopes.map(scopeLabel).join(" · ") }) }}
          </p>
          <p v-else-if="hasTarget && missingAccountScopes.length" class="break-words text-sm" role="status">
            {{ $t("externalAccess.accountMissingScopes", { scopes: missingAccountScopes.map(scopeLabel).join(" · ") }) }}
          </p>
          <p v-else-if="hasTarget && sourceId !== null && !canSelectContractPreset" class="text-sm" role="status">
            {{ $t("externalAccess.contractReceiptProjectRequired") }}
          </p>
        </div>
        <n-checkbox-group :value="approvedScopes" class="flex flex-wrap gap-3" @update:value="values => setScopes(values.map(String))">
          <n-checkbox v-for="scope in requestedScopes" :key="scope" :value="scope" :disabled="!eligible(scope) || baseline.includes(scope)">
            {{ scopeLabel(scope) }}
          </n-checkbox>
        </n-checkbox-group>
        <p v-if="approvedScopes.includes('collaboration:write')" class="text-sm text-gray-600">
          {{ $t("externalAccess.collaborationWriteHint") }}
        </p>
        <n-checkbox v-model:checked="reviewed">
          {{ $t("externalAccess.authorizationReviewed") }}
        </n-checkbox>
        <div class="flex flex-wrap justify-end gap-3">
          <n-button :disabled="busy" @click="decide(false)">
            {{ $t("externalAccess.reject") }}
          </n-button>
          <n-button type="primary" :disabled="!reviewed || !hasTarget || !days || !approvedScopes.length || !sourceReady" :loading="busy" @click="decide(true)">
            {{ $t("externalAccess.approve") }}
          </n-button>
        </div>
      </div>
    </n-card>
  </main>
</template>
