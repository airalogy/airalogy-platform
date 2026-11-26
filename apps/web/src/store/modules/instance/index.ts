import { SetupStoreId } from "@/enum"
import { fetchInstanceStatus, type InstanceStatus } from "@/service/api/instance"
import { request } from "@/service/request"
import { organizationUid } from "@/service/request/organization"
import { defineStore } from "pinia"

function fallbackStatus(): InstanceStatus {
  const mode = import.meta.env.VITE_DEPLOYMENT_MODE ?? "community"
  const singleLab = mode === "single_lab" || mode === "single_organization"
  return {
    deployment_mode: mode,
    single_lab: singleLab,
    initialized: !singleLab,
    signup_mode: singleLab ? "invite_only" : "open",
    bootstrap_token_required: false,
    site_url: window.location.origin,
    lab_structure_mode: singleLab ? "structured" : "flat",
    documentation_profile: singleLab ? "customer_managed" : "community",
    documentation_url: "/docs/",
    support_url: "",
    ai_enabled: false,
    sms_login_enabled: false,
    sms_signup_required: false,
    enabled_chat_models: [],
    lab: null,
  }
}

export const useInstanceStore = defineStore(SetupStoreId.INSTANCE, () => {
  const status = ref<InstanceStatus>(fallbackStatus())
  const loaded = ref(false)
  const loadError = ref<unknown>(null)

  const isSingleOrganization = computed(() => status.value.single_organization ?? status.value.single_lab)
  const isSingleLab = isSingleOrganization // Legacy consumers share the capability.
  const organization = computed(() => status.value.organization ?? status.value.lab)
  const usesOrganizationVocabulary = computed(() => isSingleOrganization.value
    && (organization.value?.organization_type ?? status.value.default_organization_type
      ?? (status.value.deployment_mode === "single_organization" ? "company" : "laboratory")) !== "laboratory")
  const initialized = computed(() => status.value.initialized)
  const signupMode = computed(() => status.value.signup_mode)
  const lab = organization
  const isStructuredLab = computed(() => status.value.lab_structure_mode === "structured")
  const documentationProfile = computed(() => status.value.documentation_profile)
  const documentationUrl = computed(() => status.value.documentation_url)
  const supportUrl = computed(() => status.value.support_url)
  type Capabilities = Pick<InstanceStatus, "ai_enabled" | "enabled_chat_models" | "chat_model_names" | "organization_models">
  const scoped = ref<Capabilities | null>(null)
  let sequence = 0
  let capabilitiesPending: Promise<void> | undefined
  function loadOrganizationAI(uid: string) {
    const id = ++sequence
    organizationUid.value = uid
    scoped.value = uid ? { ai_enabled: false, enabled_chat_models: [] } : null
    if (!uid) {
      capabilitiesPending = undefined
      return
    }
    capabilitiesPending = request<Capabilities>({
      url: `/organizations/uid/${encodeURIComponent(uid)}/ai-capabilities`,
      metadata: { showError: false },
    }).then(({ data }) => {
      if (id === sequence && data)
        scoped.value = data
    })
    return capabilitiesPending
  }
  const aiEnabled = computed(() => scoped.value?.ai_enabled ?? status.value.ai_enabled)
  const smsLoginEnabled = computed(() => status.value.sms_login_enabled === true)
  const smsSignupRequired = computed(() => status.value.sms_signup_required === true)
  const enabledChatModels = computed(() => scoped.value?.enabled_chat_models ?? status.value.enabled_chat_models ?? [])
  const chatModelNames = computed(() => (scoped.value ?? status.value).chat_model_names ?? {})

  async function load() {
    loaded.value = false
    try {
      const { data, error } = await fetchInstanceStatus()
      if (data) {
        status.value = data
        loadError.value = typeof data.sms_signup_required === "boolean"
          ? null
          : new Error("Instance signup capability is unavailable")
      }
      else if (error) {
        loadError.value = error
        status.value.sms_login_enabled = false
        status.value.sms_signup_required = false
      }
    }
    catch (error) {
      loadError.value = error
      status.value.sms_login_enabled = false
      status.value.sms_signup_required = false
    }
    finally {
      loaded.value = true
    }
  }

  return {
    status,
    loaded,
    loadError,
    isSingleLab,
    isSingleOrganization,
    organization,
    usesOrganizationVocabulary,
    initialized,
    signupMode,
    lab,
    isStructuredLab,
    documentationProfile,
    documentationUrl,
    supportUrl,
    aiEnabled,
    smsLoginEnabled,
    smsSignupRequired,
    enabledChatModels,
    organizationModels: computed(() => scoped.value?.organization_models ?? []),
    chatModelNames,
    loadOrganizationAI,
    whenOrganizationAIReady: () => capabilitiesPending,
    load,
  }
})
