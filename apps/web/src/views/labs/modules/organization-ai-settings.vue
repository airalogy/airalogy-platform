<template>
  <settings-card :title="t('page.organization.ai.title')" :description="t('page.organization.ai.description')" data-testid="organization-ai-settings">
    <p v-if="loading" role="status">{{ t("page.organization.ai.loading") }}</p>
    <div v-else-if="!catalog">
      <p role="alert">{{ t("page.organization.ai.loadError") }}</p>
      <n-button @click="load">{{ t("page.organization.ai.reload") }}</n-button>
    </div>
    <n-form v-else class="min-w-0 max-w-2xl" :disabled="Boolean(busy)" @submit.prevent="save">
      <n-alert v-if="catalog.instance_blocked" type="warning" class="mb-3">{{ t("page.organization.ai.blocked") }}</n-alert>
      <p v-if="catalog.inherited" class="mb-3">{{ t("page.organization.ai.inherited") }}</p>
      <n-form-item :label="t('page.organization.ai.enable')">
        <n-switch v-model:value="enabled" :disabled="catalog.instance_blocked || Boolean(busy)" :aria-label="t('page.organization.ai.enable')" />
      </n-form-item>
      <n-form-item v-if="options.length" :label="t('page.organization.ai.defaultModel')">
        <n-select v-model:value="defaultOption" data-testid="ai-default-model" :options="options" />
      </n-form-item>
      <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h3 class="m-0 text-base">{{ t("page.organization.ai.services") }}</h3>
        <n-button size="small" :disabled="services.length >= 32" @click="addService">{{ t("page.organization.ai.addService") }}</n-button>
      </div>
      <div v-if="services.length" class="mb-4 flex flex-wrap gap-2" role="group" :aria-label="t('page.organization.ai.services')">
        <n-button v-for="service in services" :key="service.id" size="small" :type="service.id === activeId ? 'primary' : 'default'" :aria-pressed="service.id === activeId" @click="activeId = service.id">
          {{ service.name || t("page.organization.ai.serviceName") }}
        </n-button>
      </div>
      <div v-if="active" class="mb-4 min-w-0 border rounded-lg p-4">
        <n-form-item :label="t('page.organization.ai.serviceName')">
          <n-input v-model:value="active.name" :maxlength="100" data-testid="ai-service-name" />
        </n-form-item>
        <n-form-item :label="t('page.organization.ai.provider')">
          <n-select :value="active.provider" :options="providers" data-testid="ai-provider" @update:value="setProvider" />
        </n-form-item>
        <n-form-item :label="t('page.organization.ai.endpoint')" :feedback="t('page.organization.ai.endpointHint')">
          <n-select v-model:value="active.base_url" filterable :options="catalog.allowed_base_urls.map(value => ({ value, label: value }))" />
        </n-form-item>
        <n-form-item label="API Key">
          <n-input v-model:value="active.key" type="password" :input-props="{ autocomplete: 'new-password', spellcheck: false }" :placeholder="retainsKey(active) ? t('page.organization.ai.keepKey') : t('page.organization.ai.enterKey')" />
        </n-form-item>
        <n-checkbox v-if="active.has_key && !active.key" v-model:checked="active.clear_key" class="mb-3">{{ t("page.organization.ai.remove") }}</n-checkbox>
        <n-form-item :label="t('page.organization.ai.modelIds')" :feedback="t('page.organization.ai.modelsHint')">
          <n-input v-model:value="active.modelText" type="textarea" :autosize="{ minRows: 2, maxRows: 8 }" data-testid="ai-model-ids" :input-props="{ spellcheck: false }" />
        </n-form-item>
        <n-form-item :label="t('page.organization.ai.testModel')">
          <n-select v-model:value="probeModel" :options="activeModels.map(value => ({ label: value, value }))" />
        </n-form-item>
        <div class="flex flex-wrap gap-2">
          <n-button :loading="busy === 'test'" :disabled="!canTest || Boolean(busy)" @click="test">{{ t("page.organization.ai.test") }}</n-button>
          <n-button quaternary type="error" @click="removeService">{{ t("page.organization.ai.removeService") }}</n-button>
        </div>
      </div>
      <n-button type="primary" attr-type="submit" :loading="busy === 'save'" :disabled="!canSave || Boolean(busy)">{{ t("page.organization.ai.save") }}</n-button>
      <n-button v-if="conflict" @click="load">{{ t("page.organization.ai.reload") }}</n-button>
      <p v-if="feedback" role="status" aria-live="polite" class="mt-3">{{ feedback }}</p>
    </n-form>
  </settings-card>
</template>

<script setup lang="ts">
import { SettingsCard } from "@/components/common/settings"
import { useOrganizationTranslation } from "@/composables/useOrganizationTranslation"
import { request } from "@/service/request"
import { useInstanceStore } from "@/store/modules/instance"
import { isAxiosError } from "axios"

type Provider = "qwen" | "openai"
interface Service { id: string, name: string, provider: Provider, base_url: string, models: string[], has_key: boolean }
interface Catalog { services: Service[], default_service_id: string | null, model: string | null, enabled: boolean, revision: number, inherited: boolean, instance_blocked: boolean, allowed_base_urls: string[] }
interface Draft extends Service { modelText: string, key: string, clear_key: boolean }

const props = defineProps<{ labId: string, uid: string }>()
const { t } = useOrganizationTranslation()
const store = useInstanceStore()
const path = computed(() => `/organizations/${props.labId}/ai-settings/catalog`)
const catalog = ref<Catalog>()
const services = ref<Draft[]>([])
const enabled = ref(false)
const activeId = ref("")
const active = computed(() => services.value.find(s => s.id === activeId.value))
const defaultOption = ref<string | null>(null)
const probeModel = ref<string | null>(null)
const loading = ref(true)
const busy = ref<"test" | "save" | null>(null)
const conflict = ref(false)
const feedback = ref("")
const baseline = ref("")
const providers = [{ value: "qwen", label: "DashScope" }, { value: "openai", label: "OpenAI Compatible" }]
const defaults = { qwen: ["DashScope", "https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen3.8-flash"], openai: ["OpenAI", "https://api.openai.com/v1", "gpt-4.1"] }
const parsedModels = (s: Draft) => s.modelText.split(/\r?\n/).map(value => value.trim()).filter(Boolean)
const activeModels = computed(() => active.value ? parsedModels(active.value) : [])
const options = computed(() => services.value.flatMap(s => parsedModels(s).map(model => ({ label: `${s.name} · ${model}`, value: `${s.id}|${model}` }))))
const signature = computed(() => JSON.stringify([enabled.value, defaultOption.value, services.value]))
const canSave = computed(() => {
  const names = services.value.map(s => s.name.trim().toLowerCase())
  const selected = services.value.find(s => defaultOption.value?.startsWith(`${s.id}|`))
  return !conflict.value && signature.value !== baseline.value && services.value.every(valid)
    && new Set(names).size === names.length && (!services.value.length || Boolean(selected))
    && (!enabled.value || (selected && hasKey(selected)))
})
const canTest = computed(() => active.value && valid(active.value) && hasKey(active.value) && probeModel.value && !catalog.value?.instance_blocked && !conflict.value)
function retainsKey(service: Draft) {
  const old = catalog.value?.services.find(s => s.id === service.id)
  return Boolean(old?.has_key && !service.clear_key && old.base_url === service.base_url && old.provider === service.provider)
}
function hasKey(service: Draft) {
  return Boolean(service.key.trim() || retainsKey(service))
}
function valid(service: Draft) {
  const models = parsedModels(service)
  return service.name.trim() && models.length > 0 && models.length <= 64 && new Set(models).size === models.length
    && models.every(id => /^[A-Z0-9][\w./:@+-]{0,199}$/i.test(id))
    && (!service.has_key || hasKey(service) || service.clear_key)
}
function addService() {
  const provider = services.value.some(s => s.provider === "qwen") ? "openai" : "qwen"
  const [baseName, base_url, modelText] = defaults[provider]
  let name = baseName
  for (let i = 2; services.value.some(s => s.name === name); i++) {
    name = `${baseName} ${i}`
  }
  const id = crypto.randomUUID()
  services.value.push({ id, name, provider, base_url, modelText, models: [], key: "", has_key: false, clear_key: false })
  activeId.value = id
}
function setProvider(value: Provider) {
  const s = active.value
  if (!s || value === s.provider)
    return
  const [oldName, oldURL, oldModel] = defaults[s.provider]
  const [name, url, model] = defaults[value]
  if (s.name === oldName)
    s.name = name
  if (s.base_url === oldURL)
    s.base_url = url
  if (s.modelText === oldModel)
    s.modelText = model
  s.key = ""
  s.provider = value
}
function removeService() {
  services.value = services.value.filter(s => s.id !== activeId.value)
  activeId.value = services.value[0]?.id ?? ""
  if (!services.value.length)
    enabled.value = false
}
watch(activeModels, (list) => {
  if (!list.includes(probeModel.value ?? ""))
    probeModel.value = list[0] ?? null
}, { flush: "sync" })
watch(options, (list) => {
  if (!list.some(o => o.value === defaultOption.value))
    defaultOption.value = list[0]?.value ?? null
}, { flush: "sync" })
watch([signature, activeId, probeModel], () => {
  feedback.value = ""
}, { flush: "sync" })
function apply(data: Catalog) {
  catalog.value = data
  services.value = data.services.map(s => ({ ...s, key: "", clear_key: false, modelText: s.models.join("\n") }))
  enabled.value = data.enabled
  defaultOption.value = data.default_service_id ? `${data.default_service_id}|${data.model}` : null
  if (!active.value)
    activeId.value = data.default_service_id ?? services.value[0]?.id ?? ""
  conflict.value = false
  baseline.value = signature.value
}
async function load() {
  const url = path.value
  loading.value = true
  feedback.value = ""
  const { data } = await request<Catalog>({ url, metadata: { showError: false } })
  if (url !== path.value)
    return
  if (data)
    apply(data)
  else catalog.value = undefined
  loading.value = false
}
function body(s: Draft) {
  return { id: s.id, name: s.name.trim(), provider: s.provider, base_url: s.base_url, models: parsedModels(s), ...(s.key.trim() ? { api_key: s.key.trim() } : { clear_key: s.clear_key }) }
}
function handleError(error: unknown) {
  conflict.value = isAxiosError(error) && error.response?.status === 409
  feedback.value = t(conflict.value ? "page.organization.ai.conflict" : "page.organization.ai.failed")
}
const outcomes = ["ok", "authentication_failed", "permission_denied", "model_unavailable", "rate_limited", "unreachable", "provider_error", "invalid_response"] as const
async function test() {
  if (!active.value || !canTest.value || busy.value)
    return
  busy.value = "test"
  const { data, error } = await request<{ status: string }>({ url: `${path.value}/test`, method: "POST", data: { service: body(active.value), model: probeModel.value, expected_revision: catalog.value?.revision }, metadata: { showError: false } })
  const status = outcomes.find(value => value === data?.status)
  if (status)
    feedback.value = t(`page.organization.ai.${status}`)
  else handleError(error)
  busy.value = null
}
async function save() {
  if (!canSave.value || busy.value)
    return
  busy.value = "save"
  const [id, model] = defaultOption.value?.split("|") ?? []
  const { data, error } = await request<Catalog>({ url: path.value, method: "PUT", metadata: { showError: false }, data: { services: services.value.map(body), enabled: enabled.value, default_service_id: id ?? null, model: model ?? null, expected_revision: catalog.value?.revision } })
  if (data) {
    apply(data)
    feedback.value = t("page.organization.ai.saved")
    if (store.isSingleLab)
      await store.load()
    await store.loadOrganizationAI(props.uid)
  }
  else {
    handleError(error)
  }
  busy.value = null
}
watch(path, load, { immediate: true })
</script>
