<template>
  <settings-card :title="t('page.organization.ai.title')" :description="t('page.organization.ai.description')" data-testid="organization-ai-settings">
    <p v-if="loading" role="status">
      {{ t("page.organization.ai.loading") }}
    </p>
    <div v-else-if="!settings">
      <p role="alert">
        {{ t("page.organization.ai.loadError") }}
      </p>
      <n-button @click="load">
        {{ t("page.organization.ai.reload") }}
      </n-button>
    </div>
    <n-form v-else size="medium" class="max-w-xl" :disabled="Boolean(busy)" @submit.prevent="save">
      <n-alert v-if="settings.instance_blocked" class="mb-4" type="warning">
        {{ t("page.organization.ai.blocked") }}
      </n-alert>
      <n-form-item :label="t('page.organization.ai.enable')">
        <n-switch v-model:value="enabled" :disabled="settings.instance_blocked || Boolean(busy)" :aria-label="t('page.organization.ai.enable')" />
      </n-form-item>
      <p v-if="settings.inherited" class="mb-3 text-sm text-gray-500">
        {{ t("page.organization.ai.inherited") }}
      </p>
      <n-form-item :label="t('page.organization.ai.model')">
        <n-select v-model:value="model" :options="settings.models.map(value => ({ label: value, value }))" />
      </n-form-item>
      <n-form-item label="API Key">
        <n-input v-model:value="key" type="password" :input-props="{ autocomplete: 'new-password', spellcheck: false }" :placeholder="savedKey ? t('page.organization.ai.keepKey') : t('page.organization.ai.enterKey')" />
      </n-form-item>
      <n-checkbox v-if="settings.has_key && !enabled" v-model:checked="clearKey" class="mb-3" @update:checked="key = ''">
        {{ t("page.organization.ai.remove") }}
      </n-checkbox>
      <div class="flex flex-wrap items-center gap-2">
        <n-button :loading="busy === 'test'" :disabled="Boolean(busy) || !canTest" @click="test">
          {{ t("page.organization.ai.test") }}
        </n-button>
        <n-button attr-type="submit" type="primary" :loading="busy === 'save'" :disabled="Boolean(busy) || !canSave">
          {{ t("page.organization.ai.save") }}
        </n-button>
        <n-button v-if="conflict" @click="load">
          {{ t("page.organization.ai.reload") }}
        </n-button>
      </div>
      <p v-if="feedback" role="status" aria-live="polite" class="mt-3 text-sm">
        {{ feedback }}
      </p>
    </n-form>
  </settings-card>
</template>

<script setup lang="ts">
import { SettingsCard } from "@/components/common/settings"
import { useOrganizationTranslation } from "@/composables/useOrganizationTranslation"
import { request } from "@/service/request"
import { useInstanceStore } from "@/store/modules/instance"
import { isAxiosError } from "axios"

interface Settings {
  model: string
  models: string[]
  enabled: boolean
  has_key: boolean
  inherited: boolean
  revision: number
  instance_blocked: boolean
}

const props = defineProps<{ labId: string, uid: string }>()
const { t } = useOrganizationTranslation()
const store = useInstanceStore()
const settings = ref<Settings | null>(null)
const loading = ref(true)
const busy = ref<"test" | "save" | null>(null)
const key = ref("")
const clearKey = ref(false)
const enabled = ref(false)
const model = ref("")
const feedback = ref("")
const conflict = ref(false)
const path = computed(() => `/organizations/${props.labId}/ai-settings`)
const savedKey = computed(() => settings.value?.has_key && settings.value.model.startsWith("qwen") === model.value.startsWith("qwen"))
const hasKey = computed(() => Boolean(key.value.trim() || (savedKey.value && !clearKey.value)))
const canTest = computed(() => hasKey.value && !settings.value?.instance_blocked && !clearKey.value)
const canSave = computed(() => !conflict.value && (!enabled.value || hasKey.value) && (!settings.value?.has_key || hasKey.value || clearKey.value)
  && (model.value !== settings.value?.model || enabled.value !== settings.value?.enabled || key.value.trim() || clearKey.value))

function apply(data: Settings) {
  settings.value = data
  enabled.value = data.enabled
  model.value = data.model
  clearKey.value = false
  key.value = ""
  conflict.value = false
}
async function load() {
  loading.value = true
  feedback.value = ""
  const { data } = await request<Settings>({ url: path.value, metadata: { showError: false } })
  if (data)
    apply(data)
  else
    settings.value = null
  loading.value = false
}
function handleError(error: unknown) {
  conflict.value = isAxiosError(error) && error.response?.status === 409
  feedback.value = conflict.value ? t("page.organization.ai.conflict") : t("page.organization.ai.failed")
}
function body() {
  return { model: model.value, expected_revision: settings.value?.revision, ...(key.value.trim() ? { api_key: key.value.trim() } : {}) }
}
const outcomes = ["ok", "authentication_failed", "permission_denied", "model_unavailable", "rate_limited", "unreachable"] as const
async function test() {
  busy.value = "test"
  const { data, error } = await request<{ status: string }>({ url: `${path.value}/test`, method: "POST", data: body(), metadata: { showError: false } })
  if (data) {
    const result = outcomes.find(value => value === data.status)
    feedback.value = result ? t(`page.organization.ai.${result}`) : t("page.organization.ai.failed")
  }
  else {
    handleError(error)
  }
  busy.value = null
}
async function save() {
  if (!canSave.value || busy.value)
    return
  busy.value = "save"
  const { data, error } = await request<Settings>({ url: path.value, method: "PUT", data: { ...body(), enabled: enabled.value, clear_key: clearKey.value }, metadata: { showError: false } })
  if (data) {
    apply(data)
    feedback.value = t("page.organization.ai.saved")
    if (store.isSingleLab)
      await store.load()
    else
      await store.loadOrganizationAI(props.uid)
  }
  else {
    handleError(error)
  }
  busy.value = null
}

watch([key, model, enabled, clearKey], () => {
  feedback.value = ""
}, { flush: "sync" })
watch(enabled, (value) => {
  if (value)
    clearKey.value = false
})
watch(key, (value) => {
  if (value)
    clearKey.value = false
})
onMounted(load)
</script>
