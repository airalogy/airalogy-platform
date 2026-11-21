<script setup lang="ts">
import type { ExternalDashboard } from "@/service/api/external-access"
import type { ProjectTarget } from "@/views/external-access/components/project-coverage"
import { useRouterPush } from "@/composables/useRouterPush"
import { consentExternalOAuth, getExternalDashboard, readExternalOAuthRequest } from "@/service/api/external-access"
import { useAuthStore } from "@/store/modules/auth"
import ExternalGuideLink from "@/views/external-access/components/external-guide-link.vue"
import GrantDuration from "@/views/external-access/components/grant-duration.vue"
import { coveredProjects, eligibleScope, projectTarget, scopeLabel } from "@/views/external-access/components/project-coverage"
import ProjectCoveragePicker from "@/views/external-access/components/project-coverage-picker.vue"
import { $t } from "@airalogy/shared/locales"

const route = useRoute()
const auth = useAuthStore()
const { routerPushByKey } = useRouterPush()
const info = ref<{ client_name: string, redirect_uri: string, resource: string, scopes: string[] }>()
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
watch(projects, (items) => {
  projectId.value = items.length === 1 ? items[0].value : null
})
watch([requestedScopes, projectId, target], () => {
  approvedScopes.value = requestedScopes.value.filter(s => eligible(s) && !["contracts:read", "contracts:create", "cash:link"].includes(s))
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
  if (!info.value || (approve && (!reviewed.value || !hasTarget.value || !days.value)))
    return
  busy.value = true
  try {
    const result = await consentExternalOAuth({ ...params.value, approve, approved_scopes: approve ? approvedScopes.value : undefined, ...(organizationMode.value ? { organization_id: projectId.value } : projectTarget(target.value, projectId.value)), expires_in_days: days.value })
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
        <h3>{{ $t("externalAccess.scopes") }}</h3>
        <n-checkbox-group v-model:value="approvedScopes" class="flex flex-wrap gap-3">
          <n-checkbox v-for="scope in requestedScopes" :key="scope" :value="scope" :disabled="!eligible(scope)">
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
          <n-button type="primary" :disabled="!reviewed || !hasTarget || !days || !approvedScopes.length" :loading="busy" @click="decide(true)">
            {{ $t("externalAccess.approve") }}
          </n-button>
        </div>
      </div>
    </n-card>
  </main>
</template>
