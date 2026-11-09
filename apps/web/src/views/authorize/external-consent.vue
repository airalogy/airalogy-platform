<script setup lang="ts">
import { useRouterPush } from "@/composables/useRouterPush"
import { consentExternalOAuth, getExternalDashboard, readExternalOAuthRequest } from "@/service/api/external-access"
import { useAuthStore } from "@/store/modules/auth"
import { $t } from "@airalogy/shared/locales"

const route = useRoute()
const auth = useAuthStore()
const { routerPushByKey } = useRouterPush()
const info = ref<{ client_name: string, redirect_uri: string, resource: string, scopes: string[] }>()
const projects = ref<Array<{ value: string, label: string }>>([])
const projectId = ref<string | null>(null)
const days = ref(1)
const reviewed = ref(false)
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
    const dashboard = await getExternalDashboard()
    projects.value = dashboard.projects.filter(p => p.enabled).map(p => ({ value: p.id, label: p.name }))
    if (projects.value.length === 1)
      projectId.value = projects.value[0].value
  }
  catch { failed.value = true }
  finally { busy.value = false }
}
async function decide(approve: boolean) {
  if (!info.value || (approve && (!reviewed.value || !projectId.value)))
    return
  busy.value = true
  try {
    const result = await consentExternalOAuth({ ...params.value, approve, project_id: projectId.value || "00000000-0000-0000-0000-000000000000", expires_in_days: days.value })
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
        <n-form-item :label="$t('externalAccess.project')">
          <n-select v-model:value="projectId" :options="projects" />
        </n-form-item>
        <n-form-item :label="$t('externalResearch.oauthDays')">
          <n-input-number v-model:value="days" :min="1" :max="7" />
        </n-form-item>
        <h3>{{ $t("externalAccess.scopes") }}</h3>
        <ul class="list-disc list-inside">
          <li v-for="scope in info.scopes" :key="scope">
            {{ scope }}
          </li>
        </ul>
        <n-checkbox v-model:checked="reviewed">
          {{ $t("externalAccess.reviewed") }}
        </n-checkbox>
        <div class="flex flex-wrap justify-end gap-3">
          <n-button :disabled="busy" @click="decide(false)">
            {{ $t("externalAccess.reject") }}
          </n-button>
          <n-button type="primary" :disabled="!reviewed || !projectId" :loading="busy" @click="decide(true)">
            {{ $t("externalAccess.approve") }}
          </n-button>
        </div>
      </div>
    </n-card>
  </main>
</template>
