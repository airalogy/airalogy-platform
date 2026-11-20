<template>
  <n-button :aria-label="$t('page.instance.inviteMember')" :title="$t('page.instance.inviteMember')" @click="showModal">
    <template #icon>
      <icon-local-user-plus />
    </template>
    <span v-if="!isMobile">{{ $t("page.instance.inviteMember") }}</span>
  </n-button>
  <n-modal
    :show="isShown"
    preset="card"
    :title="$t('page.instance.inviteMember')"
    class="max-w-[calc(100vw-32px)] w-150"
    :mask-closable="false"
    :closable="!loading"
    :close-on-esc="!loading"
    @update:show="setModalStatus"
  >
    <n-tabs v-model:value="tab" type="line" size="small">
      <n-tab-pane name="create" :tab="$t('page.instance.createInvite')">
        <template v-if="!inviteUrl">
          <p class="mb-5 mt-0 text-sm text-gray-500">
            {{ $t("page.instance.privateInviteHint") }}
          </p>
          <n-form ref="formRef" :model="model" :rules="rules" label-placement="top">
            <n-form-item :label="$t('common.labAliasLabel')" path="displayName">
              <n-input ref="displayNameInput" v-model:value="model.displayName" :placeholder="$t('common.labAliasPlaceholder')" :maxlength="255" :disabled="loading" />
            </n-form-item>
            <n-form-item :label="$t('page.instance.labRole')" path="labRole">
              <n-select v-model:value="model.labRole" :options="labRoleOptions" :disabled="loading" />
            </n-form-item>
            <n-form-item :label="$t('page.instance.projectRole')" path="projectRole">
              <n-select v-model:value="model.projectRole" :options="projectRoleOptions" :disabled="loading" />
            </n-form-item>
            <n-checkbox v-if="!privileged" v-model:checked="bindEmail" :disabled="loading">
              {{ $t("page.instance.bindInviteEmail") }}
            </n-checkbox>
            <n-form-item v-if="emailRequired" :label="$t('page.instance.email')" path="email">
              <n-input v-model:value="model.email" type="text" :disabled="loading" />
              <template v-if="privileged" #feedback>
                {{ $t("page.instance.privilegedInviteEmail") }}
              </template>
            </n-form-item>
            <details class="mt-3 text-sm">
              <summary class="w-fit cursor-pointer">{{ $t("page.instance.inviteNote") }}</summary>
              <n-input v-model:value="model.note" class="mt-2" :input-props="{ 'aria-label': $t('page.instance.inviteNote') }" :maxlength="120" :disabled="loading" />
            </details>
          </n-form>
        </template>
        <div v-else class="space-y-2">
          <div class="break-words text-sm font-medium">
            {{ $t("page.instance.inviteLink") }}
            <span> · {{ model.displayName }}</span>
          </div>
          <dl class="grid grid-cols-[auto_minmax(0,1fr)] m-0 gap-x-3 gap-y-1 text-sm">
            <template v-if="emailRequired">
              <dt>{{ $t("page.instance.email") }}</dt>
              <dd class="m-0 break-words">
                {{ model.email }}
              </dd>
            </template>
            <dt>{{ $t("page.instance.labRole") }}</dt>
            <dd class="m-0">
              {{ labRoleOptions.find(option => option.value === model.labRole)?.label }}
            </dd>
            <dt>{{ $t("page.instance.projectRole") }}</dt>
            <dd class="m-0">
              {{ projectRoleOptions.find(option => option.value === model.projectRole)?.label }}
            </dd>
          </dl>
          <div class="flex flex-col gap-2 sm:flex-row">
            <n-input :value="inviteUrl" readonly type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" />
            <n-button class="self-end sm:self-auto" type="primary" @click="copyInviteUrl">
              {{ $t("page.instance.copyInviteLink") }}
            </n-button>
          </div>
          <p v-if="expiresAt" class="mb-0 mt-2 text-xs text-gray-500">
            {{ $t("page.instance.linkExpiresAt", { time: formatExpiry(expiresAt) }) }}
          </p>
        </div>
      </n-tab-pane>
      <n-tab-pane name="history" :tab="$t('page.instance.inviteHistory')" display-directive="if">
        <invitation-history @revoked="clearRevokedLink" />
      </n-tab-pane>
    </n-tabs>

    <template #footer>
      <div class="flex justify-end gap-3">
        <n-button :disabled="loading" @click="hideModal">
          {{ inviteUrl ? $t("common.close") : $t("common.cancel") }}
        </n-button>
        <n-button v-if="tab === 'create' && !inviteUrl" type="primary" :loading="loading" @click="handleCreate">
          {{ $t("page.instance.createInvite") }}
        </n-button>
        <n-button v-else-if="tab === 'create'" @click="inviteNext">
          {{ $t("page.instance.inviteNext") }}
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import type { InputInst } from "naive-ui"
import { useBasicLayout, useLoading, useShowModal } from "@/composables"
import { useFormRules, useNaiveForm } from "@/composables/useForm"
import { useOrganizationTranslation } from "@/composables/useOrganizationTranslation"
import { LabRole, ProjectRole } from "@/enum"
import { postInvitation } from "@/service/api/instance"
import { useInstanceStore } from "@/store/modules/instance"
import { copyToClip } from "@airalogy/shared"
import { reactive } from "vue"
import InvitationHistory from "./invitation-history.vue"

const props = defineProps<Props>()

const { t: $t } = useOrganizationTranslation()

interface Props {
  currentRole: LabRole
}

const instanceStore = useInstanceStore()
const { isMobile } = useBasicLayout()
const { isShown, showModal, hideModal, setModalStatus } = useShowModal()
const { loading, startLoading, endLoading } = useLoading()
const { formRef, validate } = useNaiveForm()
const { formRules: { user }, defaultRequiredRule } = useFormRules()
const tab = ref("create")
const displayNameInput = ref<InputInst | null>(null)
const bindEmail = ref(false)
const inviteId = ref("")
const inviteUrl = ref("")
const expiresAt = ref("")
const model = reactive({
  email: "",
  displayName: "",
  note: "",
  labRole: LabRole.MEMBER,
  projectRole: instanceStore.status.default_invitation_project_role ?? ProjectRole.RECORDER,
})

const privileged = computed(() => model.labRole === LabRole.MANAGER || model.projectRole === ProjectRole.MANAGER)
const emailRequired = computed(() => privileged.value || bindEmail.value)
const rules = computed(() => ({
  displayName: [{ required: true, whitespace: true, message: $t("common.labAliasPlaceholder"), trigger: ["input", "blur"] }],
  email: emailRequired.value ? user.email : [],
  labRole: [defaultRequiredRule],
  projectRole: [defaultRequiredRule],
}))
const labRoleOptions = computed(() => [
  ...(props.currentRole === LabRole.OWNER
    ? [{ label: $t("role.manager"), value: LabRole.MANAGER }]
    : []),
  { label: $t("role.member"), value: LabRole.MEMBER },
])
const projectRoleOptions = computed(() => [
  { label: $t("role.manager"), value: ProjectRole.MANAGER },
  { label: $t("role.collaborator"), value: ProjectRole.COLLABORATOR },
  { label: $t("role.recorder"), value: ProjectRole.RECORDER },
])

async function handleCreate() {
  if (loading.value || inviteUrl.value)
    return
  startLoading()
  try {
    model.displayName = model.displayName.trim()
    try {
      await validate()
    }
    catch {
      return
    }
    const { data } = await postInvitation({ ...model, email: emailRequired.value ? model.email.trim() : undefined })
    if (data) {
      inviteId.value = data.id
      inviteUrl.value = data.url
      expiresAt.value = data.expires_at
    }
  }
  finally {
    endLoading()
  }
}

function clearRevokedLink(id: string) {
  if (id === inviteId.value) {
    inviteUrl.value = ""
    expiresAt.value = ""
    inviteId.value = ""
  }
}

async function copyInviteUrl() {
  await copyToClip(inviteUrl.value)
  window.$message?.success($t("page.instance.linkCopied"))
}

function resetInvitation() {
  bindEmail.value = false
  model.displayName = ""
  model.note = ""
  model.email = ""
  model.labRole = LabRole.MEMBER
  model.projectRole = instanceStore.status.default_invitation_project_role ?? ProjectRole.RECORDER
  inviteId.value = ""
  inviteUrl.value = ""
  expiresAt.value = ""
}

async function inviteNext() {
  resetInvitation()
  await nextTick()
  displayNameInput.value?.focus()
}

watch(isShown, (shown) => {
  if (!shown) {
    tab.value = "create"
    resetInvitation()
  }
})

function formatExpiry(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value))
}
</script>
