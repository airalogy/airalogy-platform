<template>
  <n-card
    :bordered="false"
    class="m-auto h-fit max-w-620px min-w-0 w-full"
    :content-style="{ padding: '24px' }"
    size="huge"
  >
    <div class="mb-6">
      <h1 class="m-0 text-2xl font-semibold">
        {{ $t("page.instance.setupTitle") }}
      </h1>
      <p class="mb-0 mt-2 text-sm text-gray-500 leading-6">
        {{ $t("page.instance.setupDescription") }}
      </p>
    </div>

    <n-form ref="formRef" :model="model" :rules="rules" size="large">
      <fieldset
        v-if="instanceStore.status.bootstrap_token_required"
        class="mb-6 min-w-0 border border-gray-200 rounded-xl px-4 pb-1 pt-3"
      >
        <legend class="px-2 text-base font-semibold">
          {{ $t("page.instance.deploymentVerification") }}
        </legend>
        <n-form-item path="setupToken" :label="$t('page.instance.setupCode')">
          <div class="min-w-0 w-full">
            <n-input
              v-model:value="model.setupToken"
              type="password"
              show-password-on="click"
              autocomplete="off"
              :placeholder="$t('page.instance.setupCodePlaceholder')"
              :input-props="{ 'aria-label': $t('page.instance.setupCode'), 'aria-describedby': 'setup-code-hint' }"
            />
            <p id="setup-code-hint" class="mb-0 mt-2 text-sm text-gray-500 leading-6">
              {{ $t("page.instance.setupCodeHint") }}
            </p>
          </div>
        </n-form-item>
      </fieldset>
      <fieldset
        v-if="instanceStore.status.deployment_mode === 'single_organization'"
        class="mb-6 min-w-0 border border-gray-200 rounded-xl px-4 pb-1 pt-3"
      >
        <legend class="px-2 text-base font-semibold">
          {{ $t("page.organization.setupSection") }}
        </legend>
        <n-form-item path="organizationName" :label="$t('page.organization.name')" :show-label="true">
          <n-input v-model:value="model.organizationName" :maxlength="64" data-testid="setup-organization-name" />
        </n-form-item>
        <n-form-item
          v-if="organizationUid"
          :label="$t('page.organization.uid')"
          :show-label="true"
        >
          <div class="min-w-0 w-full">
            <n-input
              :value="organizationUid"
              readonly
              data-testid="setup-organization-uid"
              :aria-label="$t('page.organization.uid')"
              aria-describedby="setup-organization-uid-hint"
            />
            <p id="setup-organization-uid-hint" class="mb-0 mt-2 text-sm text-gray-500 leading-6">
              {{ $t("page.organization.setupUidHint") }}
            </p>
          </div>
        </n-form-item>
        <n-form-item path="organizationType" :label="$t('page.organization.type')" :show-label="true">
          <n-select v-model:value="model.organizationType" :options="organizationTypes" />
        </n-form-item>
      </fieldset>
      <fieldset class="mb-6 min-w-0 border border-gray-200 rounded-xl px-4 pb-1 pt-3">
        <legend class="px-2 text-base font-semibold">
          {{ $t("page.instance.firstProject") }}
        </legend>
        <n-form-item path="projectName" :label="$t('page.instance.firstProjectName')">
          <div class="min-w-0 w-full">
            <n-input
              v-model:value="model.projectName"
              :maxlength="64"
              :placeholder="$t('page.instance.defaultProjectName')"
              data-testid="setup-project-name"
              :input-props="{ 'aria-label': $t('page.instance.firstProjectName'), 'aria-describedby': 'setup-project-hint' }"
            />
            <p id="setup-project-hint" class="mb-0 mt-2 text-sm text-gray-500 leading-6">
              {{ $t("page.instance.firstProjectHint", { name: $t("page.instance.defaultProjectName") }) }}
            </p>
          </div>
        </n-form-item>
      </fieldset>
      <fieldset class="mb-6 min-w-0 border border-gray-200 rounded-xl px-4 pb-1 pt-3">
        <legend class="px-2 text-base font-semibold">
          {{ $t("page.instance.administratorAccount") }}
        </legend>
        <p class="mb-4 mt-0 text-sm text-gray-500 leading-6">
          {{ $t("page.instance.administratorAccountHint") }}
        </p>
        <n-form-item path="name" :label="$t('page.instance.administratorName')">
          <n-input v-model:value="model.name" :placeholder="$t('page.instance.administratorNamePlaceholder')" autocomplete="name" />
        </n-form-item>
        <n-form-item path="username" :label="$t('page.instance.personalUsername')">
          <div class="min-w-0 w-full">
            <n-input
              v-model:value="model.username"
              :placeholder="$t('page.instance.personalUsernamePlaceholder')"
              autocomplete="username"
              aria-describedby="setup-username-hint"
            />
            <p id="setup-username-hint" class="mb-0 mt-2 text-sm text-gray-500 leading-6">
              {{ $t("page.instance.personalUsernameHint") }}
            </p>
          </div>
        </n-form-item>
        <n-form-item path="email" :label="$t('page.instance.loginEmail')">
          <n-input v-model:value="model.email" :placeholder="$t('page.instance.email')" autocomplete="email" />
        </n-form-item>
        <n-form-item path="password" :label="$t('page.instance.loginPassword')">
          <n-input
            v-model:value="model.password"
            type="password"
            show-password-on="click"
            :placeholder="$t('page.instance.password')"
            autocomplete="new-password"
          />
        </n-form-item>
        <n-form-item path="confirmPassword" :label="$t('page.instance.confirmPassword')">
          <n-input
            v-model:value="model.confirmPassword"
            type="password"
            show-password-on="click"
            :placeholder="$t('page.instance.confirmPassword')"
            autocomplete="new-password"
            @keyup.enter="handleSubmit"
          />
        </n-form-item>
      </fieldset>
      <n-button type="primary" size="large" block :loading="submitting" @click="handleSubmit">
        {{ $t("page.instance.completeSetup") }}
      </n-button>
    </n-form>
  </n-card>
</template>

<script setup lang="ts">
import { createOrganizationNameValidator, createPasswordValidator, useFormRules, useNaiveForm } from "@/composables/useForm"
import { useOrganizationTranslation } from "@/composables/useOrganizationTranslation"
import { type OrganizationType, postInstanceBootstrap } from "@/service/api/instance"
import { useAuthStore } from "@/store/modules/auth"
import { useInstanceStore } from "@/store/modules/instance"
import { useClosableMessage, useLoading } from "@airalogy/composables"
import { reactive } from "vue"

const { t: $t } = useOrganizationTranslation()

const authStore = useAuthStore()
const instanceStore = useInstanceStore()
const message = useClosableMessage()
const { formRef, validate } = useNaiveForm()
const { loading: submitting, startLoading, endLoading } = useLoading()
const { formRules: { user }, defaultRequiredRule } = useFormRules()
const passwordRules = createPasswordValidator()
const organizationUid = instanceStore.status.default_organization_uid

const organizationTypes = computed(() => (["company", "institution", "laboratory", "other"] as const)
  .map(value => ({ value, label: $t(`page.organization.types.${value}`) })))
const model = reactive({
  projectName: "",
  organizationName: instanceStore.status.default_organization_name || "",
  organizationType: (instanceStore.status.default_organization_type || "company") as OrganizationType,
  setupToken: "",
  name: "",
  username: "",
  email: "",
  password: "",
  confirmPassword: "",
})

const rules = {
  projectName: [{
    validator: (_rule: unknown, value: string) => {
      const length = [...value.trim()].length
      return length === 0 || (length >= 3 && length <= 64)
    },
    get message() { return $t("page.instance.firstProjectNameLength") },
    trigger: ["blur", "change"],
  }],
  organizationName: instanceStore.status.deployment_mode === "single_organization"
    ? createOrganizationNameValidator(() => $t("page.organization.name"))
    : [],
  setupToken: instanceStore.status.bootstrap_token_required ? [defaultRequiredRule] : [],
  name: [defaultRequiredRule],
  username: [
    ...user.username,
    {
      validator: (_rule: unknown, value: string) => !organizationUid || value !== organizationUid,
      get message() { return $t("page.instance.personalUsernameDistinct") },
      trigger: ["blur", "change"],
    },
  ],
  email: user.email,
  password: passwordRules,
  confirmPassword: [
    ...passwordRules,
    {
      validator: () => model.password === model.confirmPassword,
      get message() { return $t("form.confirmPwd.invalid") },
      trigger: ["blur", "change"],
    },
  ],
}

async function handleSubmit() {
  await validate()
  startLoading()
  try {
    const { data, error } = await postInstanceBootstrap({
      ...model,
      projectName: model.projectName.trim() || $t("page.instance.defaultProjectName"),
      organizationUid: instanceStore.status.deployment_mode === "single_organization" ? organizationUid : undefined,
      organizationName: instanceStore.status.deployment_mode === "single_organization" ? model.organizationName.trim() : undefined,
      organizationType: instanceStore.status.deployment_mode === "single_organization" ? model.organizationType : undefined,
    })
    if (!data || error) {
      return
    }
    await instanceStore.load()
    await authStore.login("email", {
      email: model.email,
      password: model.password,
    })
  }
  catch (error) {
    message.error((error as Error).message || $t("page.instance.setupFailed"))
  }
  finally {
    endLoading()
  }
}
</script>
