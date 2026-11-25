<template>
  <section class="-mx-8">
    <header class="min-h-[70px] w-full flex flex-1 flex-row flex-wrap items-center gap-3 px-8 py-2">
      <n-button quaternary class="mr-6 -ml-2" @click="handleRedirect">
        <template #icon>
          <n-icon size="28">
            <icon-tabler-arrow-left />
          </n-icon>
        </template>
      </n-button>
      <h3 v-if="route.query.target && workflowInfo?.data" class="mr-auto w-fit text-5 font-500">
        <div v-if="isReadonly" class="-mb-1">
          {{ $t("page.protocol.addRecord.viewWorkflowRecord") }}
          <n-tag type="warning">
            {{ $t("common.readOnly") }}
          </n-tag>
        </div>
        <div v-else class="-mb-1">
          {{ $t("page.protocol.addRecord.addToWorkflow") }}
        </div>
        <n-tooltip trigger="hover">
          {{ workflowInfo.data.title }}
          <template #trigger>
            <div class="flex items-center">
              <span class="mr-2">{{ $t("common.id") }}:</span>
              <n-tag type="primary">
                {{ workflowInfo.data.id }}
              </n-tag>
            </div>
          </template>
        </n-tooltip>
      </h3>
      <div v-else class="mr-auto w-fit">
        <div class="flex items-center gap-2">
          <h3 class="text-5 font-500">
            {{ $t("page.protocol.addRecord.title") }}
          </h3>
          <n-tag v-if="displayProtocolVersion" type="success" size="small">
            v{{ displayProtocolVersion }}
          </n-tag>
        </div>
        <protocol-title-section :protocol-info="protocolInfo" :title="protocolInfo?.name" :is-protocol-link="true" :show-icon="false" size="tiny" />
      </div>

      <learning-link v-if="!isReadonly" :lesson="instanceStore.aiEnabled ? 'aira-record' : 'first-record'">
        {{ $t(instanceStore.aiEnabled ? "page.learning.aira" : "page.learning.watch") }}
      </learning-link>
      <!-- <choose-rrec-modal :rrec="rrecRef" :show="showRrec" /> -->
      <n-button v-if="isReadonly" type="warning" @click="handleCloseWindow">
        {{ $t("common.close") }}
      </n-button>
      <template v-else>
        <div v-if="formRef?.requiredCompletion" class="min-w-36 w-44">
          <div class="mb-1 flex items-center justify-between text-xs text-gray-500">
            <span>{{ $t("page.protocol.addRecord.requiredProgress") }}</span>
            <span>
              {{ formRef.requiredCompletion.filled }}/{{ formRef.requiredCompletion.total }}
            </span>
          </div>
          <n-progress
            type="line"
            :percentage="formRef.requiredCompletion.percent"
            :height="5"
            :show-indicator="false"
            :status="formRef.requiredCompletion.percent === 100 ? 'success' : 'default'"
          />
        </div>
        <n-tag v-if="autosaveState.saveFailed" size="small" type="error" round role="alert">
          {{ $t("page.protocol.addRecord.draftSaveFailed") }}
        </n-tag>
        <n-tag v-else-if="autosaveState.hasPendingChanges" size="small" type="warning" round>
          {{ $t("page.protocol.addRecord.draftSaving") }}
        </n-tag>
        <n-tag v-else-if="autosaveState.lastSavedAt" size="small" type="success" round>
          {{ $t("page.protocol.addRecord.draftSavedOnDevice") }} ·
          <n-time :time="autosaveState.lastSavedAt" type="relative" />
        </n-tag>
        <n-tag v-else size="small" round>
          {{ $t("page.protocol.addRecord.draftAutosaveReady") }}
        </n-tag>
        <n-input
          v-if="route.query.record"
          v-model:value="correctionReason"
          class="mr-3 w-72"
          size="medium"
          :placeholder="$t('page.protocol.addRecord.correctionReason')"
        />
        <restore-draft-modal
          v-if="protocolId && formRef?.fieldModel" v-model:data="recordData" :field-model="formRef.fieldModel"
          :protocol-id="protocolId"
          :protocol="protocol"
          :draft-id="draftId" :scope="draftScope"
          :saved-at="autosaveState.lastSavedAt"
          @restore:draft="handleManualRestore"
        />
        <n-button data-testid="record-save-draft" size="medium" secondary :disabled="loading || submissionLoading" @click="handleManualSave">
          {{ $t("page.protocol.draft.saveButton") }}
        </n-button>
        <n-button
          size="medium" type="primary" :disabled="reviewPending || loading || submissionLoading || isReadonly || (!!route.query.record && !correctionReason.trim())" :loading="submissionLoading" class="mr-4 px-4"
          @click="handleConfirm"
        >
          {{ $t("common.submit") }}
        </n-button>
      </template>
    </header>
    <n-divider class="!mb-4 !mt-0" />
    <n-alert v-if="submissionErrors.length" type="error" role="alert" class="mx-8 mb-4" data-testid="record-submission-errors" :title="$t('page.protocol.addRecord.notSubmitted')">
      <p>{{ $t("page.protocol.addRecord.fixAndRetry") }}</p>
      <ul class="mt-2 space-y-1">
        <li v-for="(issue, index) in submissionErrors" :key="index">
          <button v-if="issue.field" type="button" class="text-left underline" @click="formRef?.focusFirstInvalidField(issue.field)">
            {{ issue.message }}
          </button>
          <span v-else>{{ issue.message }}</span>
        </li>
      </ul>
    </n-alert>
    <n-alert v-if="researchWorkItem" type="info" class="mx-8 mb-4">
      <template #header>
        {{ $t("page.protocol.addRecord.researchWorkTitle") }} · {{ researchWorkItem.task.title }}
      </template>
      {{ researchWorkItem.instructions || researchWorkItem.task.goal }}
    </n-alert>
    <n-spin
      :show="loading" class="w-full px-4 md:h-[calc(100vh-165px)] md:pl-8 md:pr-0"
      :content-class="`w-full overflow-visible md:h-full ${protocol ? '' : ' flex-center flex-col'}`"
    >
      <protocol-add-record-form
        v-if="protocol && protocolInfo && protocolId" :key="formGeneration" ref="formRef" v-model:collapsed="isCollapsed" :protocol="protocol"
        :protocol-id="protocolId"
        :readonly="isReadonly"
        :recorder-version="displayProtocolVersion"
        :recorder-record-id="typeof route.query.record === 'string' ? route.query.record : undefined"
        :simulated-fields="simulatedFields"
        :record-data="recordData"
        @set-simulated="setSimulated"
        @review-pending="reviewPending = $event"
        @quiz-change="(field, value) => { (recordData.quiz ??= {})[field] = value }"
        @update:field="handleUpdateField"
        @update:split-size="handleUpdateSize"
      >
        <!-- <template #prefix>
          <div class="mb-2 ml-2 w-fit w-full rounded px-4 text-[1.125rem] text-white leading-10">
            <n-collapse v-model:expanded-names="expandedNames" display-directive="show" arrow-placement="right">
              <n-collapse-item title="Previous Records" name="metadata">
                <record-comment v-model="metadata" @confirm="handleCollapseMetadata" />
              </n-collapse-item>
            </n-collapse>
          </div>
        </template> -->
      </protocol-add-record-form>
      <n-upload
        v-else-if="!loading" :headers="{ 'auth-token': authStore.token }" :action="uploadAction" class="w-fit"
        directory-dnd :show-file-list="false" @finish="handleFinish" @error="handleUploadFailed"
      >
        <div class="mr-5 text-5">
          {{ $t("page.protocol.addRecord.noProtocol") }}
        </div>
        <n-button class="mr-5">
          {{ $t("page.protocol.addRecord.uploadPackage") }}
          <template #icon>
            <upload-icon />
          </template>
        </n-button>
      </n-upload>
    </n-spin>
  </section>
</template>

<script setup lang="ts">
import type { IRecordData, IRecordDataKey } from "@airalogy/aimd-core/types"
import type { ProtocolModels } from "@airalogy/shared/types"
import type { ValidateError } from "async-validator"
import type { OnError } from "naive-ui/es/upload/src/interface"
import type { ShallowRef } from "vue"

import type { ExtractResult, FieldRecord } from "./modules/protocol/helpers/parseFieldStructure"
import type { IRecordDataItem } from "./types"
import LearningLink from "@/components/learning/learning-link.vue"
import { useBoolean, useGlobalBeforeUnload, useLoading, useShowModal } from "@/composables"

import { useRouterPush } from "@/composables/useRouterPush"
import { getProtocolRecordReport, postNewResearchRecord, postValidateRecord, putUpdateResearchRecord, transformFields } from "@/service/api/project-protocols"
import { fetchResearchWorkItem, type ResearchWorkItemDetail, submitResearchWorkItem } from "@/service/api/research-tasks"
import { baseURL } from "@/service/request"

import { useAuthStore } from "@/store/modules/auth"
import { useInstanceStore } from "@/store/modules/instance"
import { useRouteStore } from "@/store/modules/route"
import { useProtocolWorkflowStore } from "@/store/modules/workflow"
import { type DraftScope, hasRecordDraftContent, recordDraftQuery } from "@/utils/recordDrafts"
import { useBeforeUnload, useClosableMessage } from "@airalogy/composables"
import { formatValidateErrors, type PydanticError } from "@airalogy/shared/utils/errorFormatter.js"
import { get as _get, set as _set } from "lodash-es"
import { type UploadOnFinish, useDialog } from "naive-ui"
import { NButton } from "naive-ui/es/button"
import { nanoid } from "nanoid"
import { useI18n } from "vue-i18n"
import { useProvideProtocolInfoStore } from "./hooks/useProtocolInfoStore"
import { useDraftManagement } from "./modules/protocol/composables/useDraftManagement"
import { RecordCalculationError } from "./modules/protocol/helpers/recordCalculationError"
import ProtocolAddRecordForm from "./modules/protocol/protocol-add-record-form.vue"
import { assignFieldValue, extractAssetId, processFieldValue } from "./utils"

defineOptions({ name: "AddProtocolRecord" })

const emits = defineEmits<IEmits>()

interface IEmits {
  (
    e: "modal:new-record",
    val: {
      labId: string
      labName: string
      id: string
      name: string
    },
  ): void
  (e: "modal:close"): void
  (e: "modal:open"): void
}
const dialog = useDialog()
const { t } = useI18n()
const { isShown, showModal, hideModal } = useShowModal()

const route = useRoute()
const router = useRouter()

const workflowStore = useProtocolWorkflowStore()
const workflowInfo = computed(() => workflowStore.getWorkflow(route.query.chain as string))

const { removeCacheRoutes } = useRouteStore()
const { routerPushByKey } = useRouterPush()

function handleUpdateShow(show: boolean) {
  if (show) {
    showModal()
    return
  }

  dialog.warning({
    title: t("common.discardTitle"),
    content: t("common.discardWarning"),
    positiveText: t("common.discardConfirm"),
    negativeText: t("common.discardCancel"),
    transformOrigin: "center",
    onPositiveClick: () => {
      hideModal()
      emits("modal:close")
    },
  })
}

function handleCancel() {
  hideModal()
}

const protocol = ref<ProtocolModels.ProtocolInfo | null>(null)
const editingProtocolVersion = ref<string | null>(null)
const correctionReason = ref("")
const reviewPending = ref(false)

const formRef = ref<{
  validate: () => any
  requiredCompletion: { filled: number, total: number, percent: number }
  focusFirstInvalidField: (field?: string) => Promise<void>
  toggle: () => void
  fieldRecord: ShallowRef<ExtractResult | null>
  fieldModel: FieldRecord
  restoreFieldRecord: (data?: Partial<IRecordData>) => void
} | null>(null)

const instanceStore = useInstanceStore()
const instanceId = nanoid()
provide("protocol-workflow-channel", { id: instanceId })

const message = useClosableMessage()
const { post, channel } = useBroadcastChannel({ name: `workflow-${route.query.chain || nanoid()}` })

const authStore = useAuthStore()

const { endLoading, loading, startLoading } = useLoading()
const { fetchProtocolInfoByUid, protocolInfo, protocolUid, protocolId } = useProvideProtocolInfoStore(null)
const displayProtocolVersion = computed(() =>
  editingProtocolVersion.value
  || (protocol.value as ProtocolModels.ProjectProtocolInfo | null)?.metadata?.version
  || protocolInfo.value?.latest_version
  || "",
)

const uploadAction = computed(() => {
  return protocolUid.value ? `${baseURL}/protocols` : ""
})

const recordData = ref<Partial<IRecordData>>({})
const researchWorkItem = ref<ResearchWorkItemDetail | null>(null)
const { bool: isReadonly, setTrue: setReadonly } = useBoolean()

const draftId = ref("")
const formGeneration = ref(0)
const draftScope = ref<DraftScope>({ version: "", query: {} })
const draftReady = ref(false)
let initializingDraft = false
let draftOwner: string | number | undefined
const simulatedSources = ref<Record<string, unknown>>({})
const valueOfField = (name: string) => processFieldValue(recordData.value.research_variable?.[name])
const simulatedFields = computed(() => Object.keys(simulatedSources.value).filter(
  field => Object.is(simulatedSources.value[field], valueOfField(field)),
))
function setSimulated(field: string, simulated: boolean) {
  if (simulated)
    simulatedSources.value[field] = valueOfField(field)
  else
    delete simulatedSources.value[field]
}
const { saveDraft, deleteDraft, getDraft } = useDraftManagement(
  protocol,
  recordData,
  () => draftId.value || undefined,
  () => draftScope.value,
)

const AUTOSAVE_DEBOUNCE_MS = 4000
const AUTOSAVE_INTERVAL_MS = 60_000

const autosaveState = reactive({
  lastSignature: "",
  hasPendingChanges: false,
  lastSavedAt: 0,
  saveFailed: false,
})

const globalBeforeUnloadRegistry = useGlobalBeforeUnload()
const { unregister } = globalBeforeUnloadRegistry
const { cleanup } = useBeforeUnload(() => autosaveState.hasPendingChanges, {
  id: route.fullPath,
})

type AutosaveReason = "debounce" | "interval" | "visibility" | "unload" | "manual"

function canAutosave() {
  return draftReady.value && draftOwner === authStore.userInfo.id && Boolean(protocolId.value) && !isReadonly.value
}

function getDraftSignature(data: Partial<IRecordData> = recordData.value) {
  try {
    return JSON.stringify([toRaw(data ?? {}), simulatedFields.value])
  }
  catch (error) {
    console.warn("Failed to serialize draft data:", error)
    return ""
  }
}

const triggerAutosave = useDebounceFn(() => flushAutosave("debounce"), AUTOSAVE_DEBOUNCE_MS)
function cancelAutosave() {
  const handler = triggerAutosave as typeof triggerAutosave & { cancel?: () => void }
  if (typeof handler.cancel === "function") {
    handler.cancel()
  }
}

function resetAutosaveBaseline(data: Partial<IRecordData> = recordData.value) {
  autosaveState.lastSignature = getDraftSignature(data)
  autosaveState.hasPendingChanges = false
  autosaveState.saveFailed = false
  cancelAutosave()
}

function markAutosavePending() {
  if (!canAutosave()) {
    return
  }
  autosaveState.hasPendingChanges = true
  triggerAutosave()
}

function flushAutosave(reason: AutosaveReason, force = false) {
  if (!protocolId.value || !canAutosave()) {
    return
  }

  if (!autosaveState.hasPendingChanges && reason !== "manual") {
    return
  }

  if (reason !== "manual" && !hasRecordDraftContent(recordData.value) && !getDraft(protocolId.value)) {
    resetAutosaveBaseline()
    return
  }

  const signature = getDraftSignature()
  if (!signature || (signature === autosaveState.lastSignature && !force)) {
    autosaveState.hasPendingChanges = false
    return
  }

  const saved = saveDraft(protocolId.value, recordData.value, { silent: true, simulatedFields: simulatedFields.value })
  if (!saved) {
    autosaveState.saveFailed = true
    autosaveState.hasPendingChanges = true
    return false
  }
  autosaveState.saveFailed = false
  autosaveState.lastSignature = signature
  autosaveState.hasPendingChanges = false
  autosaveState.lastSavedAt = Date.now()
  return true
}

function handleManualSave() {
  if (flushAutosave("manual", true)) {
    message.success(t("page.protocol.addRecord.draftSavedConfirmation"))
  }
  else {
    message.error(t("page.protocol.addRecord.draftSaveFailed"))
  }
}

function clearDraftAfterSubmit() {
  if (!protocolId.value) {
    return
  }
  deleteDraft(protocolId.value)
  resetAutosaveBaseline(recordData.value)
  message.success(t("page.protocol.draft.cleared"))
}

watch([recordData, simulatedFields], () => {
  markAutosavePending()
}, { deep: true })

watch(isReadonly, (val) => {
  if (val) {
    autosaveState.hasPendingChanges = false
    cancelAutosave()
  }
})

const autosaveIntervalId = ref<number | null>(null)

useEventListener(document, "visibilitychange", () => {
  if (document.visibilityState === "hidden") {
    flushAutosave("visibility", true)
  }
})

useEventListener(window, "beforeunload", () => {
  flushAutosave("unload", true)
})

function handleUpdateField(payload: {
  scope: IRecordDataKey
  prop: string
  value: IRecordDataItem
  info?: any
}) {
  const { scope, prop, value, info } = payload

  assignFieldValue(recordData, scope, prop, value, info)
}

const handleUploadFailed: OnError = (options) => {
  // TODO: emit event
  const { event } = options
  const { response, statusText, status } = event?.target as XMLHttpRequest

  if (response.error) {
    message.error(response.error)
  }
  else {
    message.error(t("page.protocol.addRecord.uploadError", { status, statusText }), {
      closable: true,
      duration: 0,
    })
  }
}

const handleFinish: UploadOnFinish = (options) => {
  message.success(t("page.protocol.addRecord.uploadSuccess"))
  // TODO: emit event

  const { event } = options
  const { response } = event?.target as XMLHttpRequest

  try {
    const { data } = JSON.parse(response) as { data: ProtocolModels.ProtocolInfo }
    protocol.value = data
  }
  catch (e) {
    message.error(t("page.protocol.addRecord.uploadFailed"))
  }
}

interface ResourceCommitSummary {
  field: string
  role: string
  label: string
  quantity?: string
  unit?: string
  container?: string
  booking?: string
  reservation?: string
}

function resourceCommitSummary(
  values: Record<string, any>,
): ResourceCommitSummary[] {
  const fields = (protocol.value?.fields || {}) as Record<string, any>
  const templates = fields.templates && typeof fields.templates === "object"
    ? fields.templates
    : fields
  const definitions = templates.var_definitions
    || templates.vars
    || templates.var
    || []
  const summaries: ResourceCommitSummary[] = []
  for (const definition of definitions) {
    const type = String(definition?.type || definition?.type_annotation || "")
    if (!type.includes("ResourceRef"))
      continue
    const field = String(definition?.id || definition?.name || "")
    const value = values[field]
    if (!field || !value || typeof value !== "object")
      continue
    const kwargs = definition?.kwargs && typeof definition.kwargs === "object"
      ? definition.kwargs
      : {}
    const role = String(kwargs.resource_role || "reference")
    if (!["input", "output", "equipment"].includes(role))
      continue
    const quantityField = kwargs.quantity_field
      ? String(kwargs.quantity_field).replace(/^var\./, "")
      : ""
    const quantity = quantityField ? values[quantityField] : value.quantity
    summaries.push({
      field,
      role,
      label: String(value.label || value.snapshot?.name || value.id),
      quantity: quantity === null || quantity === undefined
        ? undefined
        : String(quantity),
      unit: value.unit ? String(value.unit) : undefined,
      container: value.container_id ? String(value.container_id) : undefined,
      booking: value.booking_id ? String(value.booking_id) : undefined,
      reservation: value.reservation_id
        ? String(value.snapshot?.research_reservation?.label || value.reservation_id)
        : undefined,
    })
  }
  return summaries
}

function confirmRecordSubmission(
  values: Record<string, any>,
  isRevision: boolean,
  examples: string[],
): Promise<boolean> {
  const summaries = resourceCommitSummary(values)
  return new Promise((resolve) => {
    let settled = false
    const settle = (value: boolean) => {
      if (!settled) {
        settled = true
        resolve(value)
      }
    }
    dialog.warning({
      title: t(isRevision
        ? "page.protocol.addRecord.confirmRevisionTitle"
        : "page.protocol.addRecord.confirmSubmitTitle"),
      content: () => h(
        "div",
        { class: "space-y-2" },
        [
          h("div", { class: "rounded border bg-gray-50 p-3 text-sm" }, [
            h("strong", t("page.protocol.addRecord.saveDestination")),
            h("div", `${protocolInfo.value?.lab.name || ""} / ${protocolInfo.value?.project.name || ""} / ${protocolInfo.value?.name || ""}`),
            h("div", `v${displayProtocolVersion.value}`),
            formRef.value?.requiredCompletion
              ? h("div", t("page.protocol.addRecord.requiredProgressSummary", {
                filled: formRef.value.requiredCompletion.filled,
                total: formRef.value.requiredCompletion.total,
              }))
              : null,
          ]),
          ...(examples.length
            ? [
                h("div", { "class": "rounded border p-3", "data-testid": "review-simulated-fields" }, [
                  h("strong", t("page.recorderAira.reviewSimulated")),
                  h("ul", examples.map(key => h("li", `${key}: ${String(values[key])}`))),
                ]),
              ]
            : []),
          ...(summaries.length
            ? [
                h("p", { class: "font-medium" }, t("page.protocol.addRecord.resourceCommitTitle")),
                h("p", t("page.protocol.addRecord.resourceCommitDescription")),
                ...summaries.map(item =>
                  h("div", { class: "rounded border p-2 text-sm" }, [
                    h("strong", `${item.field} · ${item.role}`),
                    h("div", item.label),
                    item.quantity
                      ? h("div", `${item.quantity} ${item.unit || ""}`.trim())
                      : null,
                    item.container
                      ? h("div", `${t("page.protocol.addRecord.resourceContainer")}: ${item.container}`)
                      : null,
                    item.booking
                      ? h("div", `${t("page.protocol.addRecord.resourceBooking")}: ${item.booking}`)
                      : null,
                    item.reservation
                      ? h("div", `${t("page.protocol.addRecord.resourceReservation")}: ${item.reservation}`)
                      : null,
                  ]),
                ),
              ]
            : []),
        ],
      ),
      positiveText: t(isRevision
        ? "page.protocol.addRecord.confirmRevisionAction"
        : "page.protocol.addRecord.confirmSubmitAction"),
      negativeText: t("common.cancel"),
      onPositiveClick: () => settle(true),
      onNegativeClick: () => settle(false),
      onClose: () => settle(false),
    })
  })
}

const submissionLoading = ref(false)
const submissionErrors = ref<{ field?: string, message: string }[]>([])

async function showSubmissionErrors(error: unknown) {
  if (error instanceof RecordCalculationError) {
    submissionErrors.value = [{ field: error.field, message: error.message }]
    await formRef.value?.focusFirstInvalidField(error.field)
    return
  }
  const detail = (error as { response?: { data?: { detail?: unknown } } } | null)?.response?.data?.detail
  const candidates = Array.isArray(error) ? error : Array.isArray(detail) ? detail : (detail as { errors?: unknown } | null)?.errors
  const fieldErrors = Array.isArray(candidates) ? candidates.filter(item => Array.isArray(item?.loc)) : []
  if (fieldErrors.length) {
    const schema = protocolInfo.value?.json_schema?.research_variable as { properties?: Record<string, { title?: string }> } | undefined
    submissionErrors.value = (fieldErrors as PydanticError[]).map((item) => {
      const field = String(item.loc[0] || "")
      const label = schema?.properties?.[field]?.title || field
      const nested = item.loc.slice(1).join(" / ")
      return { field: "fieldKey" in item && typeof item.fieldKey === "string" ? item.fieldKey : field, message: `${label}${nested ? ` (${nested})` : ""}: ${item.msg}` }
    })
  }
  else {
    // Network and server failures must leave a persistent, actionable message,
    // not only a toast that disappears while the researcher checks their data.
    submissionErrors.value = [{ message: t("page.protocol.addRecord.retrySubmission") }]
  }
  await formRef.value?.focusFirstInvalidField(submissionErrors.value[0]?.field)
}

async function handleConfirm() {
  if (!formRef.value || isReadonly.value || reviewPending.value) {
    return
  }
  submissionLoading.value = true
  submissionErrors.value = []

  try {
    await formRef.value.validate()

    if (!protocolId.value) {
      return
    }
    const { research_check, research_result, research_step, research_variable: researchVariable } = recordData.value

    const payload = extractAssetId(toRaw(researchVariable)) || {}

    const examples = [...simulatedFields.value]
    const { data: result, error: validateError } = await postValidateRecord(
      protocolId.value,
      payload,
      editingProtocolVersion.value || undefined,
    )

    if (validateError) {
      await showSubmissionErrors(validateError)
      return
    }

    if (!result) {
      return
    }

    const { research_variable = {} } = result
    // const preparedReport = formRef.value?.preparedReport()
    const { record } = route.query
    if (!(await confirmRecordSubmission(research_variable, Boolean(record), examples))) {
      return
    }

    const { data, error } = await (record
      ? putUpdateResearchRecord(protocolId.value, record as string, {
        quiz: recordData.value.quiz,
        simulated_fields: examples,
        research_variable: research_variable as any,
        research_check: research_check as any,
        research_result: research_result as any,
        research_step: research_step as any,
        report: "",
        revision_reason: correctionReason.value.trim(),
      })
      : postNewResearchRecord(protocolId.value, {
        quiz: recordData.value.quiz,
        simulated_fields: examples,
        research_variable: research_variable as any,
        research_check: research_check as any,
        research_result: research_result as any,
        research_step: research_step as any,
        report: "",
      }))

    if (data) {
      draftReady.value = false
      clearDraftAfterSubmit()
      if (researchWorkItem.value) {
        const completedWork = await submitResearchWorkItem(researchWorkItem.value.id, {
          expected_revision: researchWorkItem.value.revision,
          record_id: String(data.id),
          record_version: Number(data.version),
        })
        researchWorkItem.value = completedWork
        cleanup()
        unregister(route.fullPath)
        hideModal()
        dialog.success({
          title: t("page.protocol.addRecord.researchWorkCompletedTitle"),
          content: t("page.protocol.addRecord.researchWorkCompletedContent"),
          positiveText: t("page.protocol.addRecord.returnToResearchTask"),
          closable: false,
          maskClosable: false,
          onPositiveClick: () => router.push({
            name: "research-task-detail",
            params: { taskId: completedWork.task.id },
          }),
        })
        return
      }
      const { chain, target } = route.query
      const targetId = target as string
      const chainInfo = workflowStore.getWorkflow(chain as string)
      if (chainInfo && targetId) {
        const { data: chainInfoData, model, flowNodes } = chainInfo

        const uid = protocolInfo.value?.uid
        const airalogyProtocolId = protocolInfo.value?.airalogy_id
        if (uid || airalogyProtocolId) {
          const targetNode = flowNodes.find(({ airalogy_protocol_id }) =>
            airalogy_protocol_id === uid || airalogy_protocol_id === airalogyProtocolId,
          )

          if (targetNode) {
            targetNode.status = "done"
          }
        }

        post({ action: "showIntermediate", data, source: target, id: instanceId })
        setReadonly()
        dialog.success({
          title: t("page.protocol.addRecord.workflowContinueTitle"),
          content: t("page.protocol.addRecord.workflowContinueContent"),
          negativeText: t("page.protocol.addRecord.workflowStay"),
          positiveText: t("common.close"),
          onPositiveClick(e) {
            if (window.opener) {
              window.opener.focus()
              window.close()
            }
          },
        })
      }
      else if (protocolInfo.value) {
        const { lab, project, uid } = protocolInfo.value
        const startAnother = await confirmRecordNextStep(Boolean(record))
        if (startAnother) {
          simulatedSources.value = {}
          recordData.value = {}
          Object.keys(formRef.value.fieldModel).forEach((key) => {
            delete (formRef.value!.fieldModel as Record<string, unknown>)[key]
          })
          await formRef.value.restoreFieldRecord({})
          correctionReason.value = ""
          editingProtocolVersion.value = null
          autosaveState.lastSavedAt = 0
          resetAutosaveBaseline(recordData.value)
          const query: typeof route.query = { ...route.query, newRecord: "true" }
          delete query.record
          delete query.recordVersion
          delete query.draft
          await router.replace({ path: route.path, query })
        }
        else {
          cleanup()
          unregister(route.fullPath)
          await routerPushByKey("protocol-record-report", {
            params: { protocolUid: uid, labUid: lab.uid, projectUid: project.uid, protocolVersion: data.protocol_version, recordId: data.id, recordVersion: String(data.version) },
          })
        }
      }
      hideModal()
    }
    else if (error) {
      await showSubmissionErrors(error)
    }
  }
  catch (e) {
    await showSubmissionErrors(e)
    if (e instanceof Error) {
      message.error(e.message, {
        closable: true,
        duration: 8000,
      })
      return
    }

    if (Array.isArray(e) && e.some(issue => Array.isArray(issue?.loc)))
      return
    const errors = formatValidateErrors(e as ValidateError[])

    message.error(errors.join("\n"), {
      closable: true,
      duration: 8000,
    })
  }
  finally {
    submissionLoading.value = false
  }
}

function confirmRecordNextStep(isRevision: boolean): Promise<boolean> {
  return new Promise((resolve) => {
    let settled = false
    const settle = (value: boolean) => {
      if (!settled) {
        settled = true
        resolve(value)
      }
    }
    dialog.success({
      title: t(isRevision
        ? "page.protocol.addRecord.revisionSuccessTitle"
        : "page.protocol.addRecord.createSuccess"),
      content: t("page.protocol.addRecord.successNextStep"),
      positiveText: t("page.protocol.addRecord.viewSavedRecord"),
      negativeText: isRevision ? undefined : t("page.protocol.addRecord.addAnotherAction"),
      onPositiveClick: () => settle(false),
      onNegativeClick: () => settle(true),
      onClose: () => settle(false),
    })
  })
}

const isCollapsed = ref(false)
function handleToggle() {
  const toggle = formRef.value?.toggle
  if (typeof toggle === "function") {
    toggle()
  }
}

const splitSize = ref<string | null>("35%")
function handleUpdateSize(value: string | number) {
  const percent = Number(value)
  if (Number.isNaN(percent)) {
    return
  }

  void nextTick(() => {
    if (isCollapsed.value) {
      splitSize.value = "0%"
    }
    else {
      splitSize.value = `${percent * 100}%`
    }
  })
}

const rrecRef = computed(() => {
  if (!protocolInfo.value)
    return null
  const { properties } = (protocolInfo.value.json_schema?.research_variable
    || {}) as Record<string, any>

  if (!properties) {
    return null
  }

  const { rrec } = properties as {
    rrec?: { default: { rrec_airalogy_id: string, metadata: string } }
  }

  return rrec?.default ?? null
})
const { bool: showRrec, setTrue: showRrecInfo, setFalse: hideRrecInfo } = useBoolean()
function handleShowRrec() {
  showRrecInfo()
}

function handleRedirect() {
  if (researchWorkItem.value) {
    void router.push({
      name: "research-task-detail",
      params: { taskId: researchWorkItem.value.task.id },
    })
    return
  }
  const { lab, project, uid } = protocolInfo.value || {}
  if (lab?.uid && project?.uid && uid) {
    void routerPushByKey("protocol-detail", {
      params: { labUid: lab.uid, projectUid: project.uid, protocolUid: uid },
    })
  }
  else {
    router.back()
  }
}

function handleCloseWindow() {
  dialog.warning({
    title: t("page.protocol.addRecord.closeWindowTitle"),
    content: t("page.protocol.addRecord.closeWindowContent"),
    positiveText: t("common.confirm"),
    negativeText: t("common.cancel"),
    onPositiveClick() {
      window.close()
    },
  })
}

onMounted(async () => {
  if (protocol.value) {
    return
  }

  startLoading()
  const { labUid, projectUid, protocolUid } = route.params as {
    labUid: string
    projectUid: string
    protocolUid: string
  }

  const workItemId = typeof route.query.researchWorkItem === "string"
    ? route.query.researchWorkItem
    : ""
  if (workItemId) {
    researchWorkItem.value = await fetchResearchWorkItem(workItemId)
    const workProtocol = researchWorkItem.value.action.protocol
    if (!workProtocol || workProtocol.uid !== protocolUid) {
      endLoading()
      message.error(t("page.protocol.addRecord.researchWorkProtocolMismatch"))
      await router.push({
        name: "research-task-detail",
        params: { taskId: researchWorkItem.value.task.id },
      })
      return
    }
    editingProtocolVersion.value = workProtocol.version
  }

  // Always fetch the latest version without cache
  // Set memoize to false to ensure we get fresh data from backend
  const info = await fetchProtocolInfoByUid({
    labUid,
    projectUid,
    protocolUid,
    version: researchWorkItem.value?.action.protocol?.version,
  }, true, false)

  if (info) {
    await nextTick(() => {
      const { record: recordId } = route.query
      if (recordId) {
        fetchRecord()
      }
      else {
        protocol.value = (info as ProtocolModels.ProtocolInfo) || null
      }
    })
  }
  endLoading()
})

onMounted(() => {
  resetAutosaveBaseline(recordData.value)
  autosaveIntervalId.value = window.setInterval(() => {
    flushAutosave("interval")
  }, AUTOSAVE_INTERVAL_MS)
})

onBeforeUnmount(() => {
  flushAutosave("unload", true)
  if (autosaveIntervalId.value) {
    window.clearInterval(autosaveIntervalId.value)
    autosaveIntervalId.value = null
  }
})

onActivated(() => {
  removeCacheRoutes("AddResearchRecord" as any)
})

// const editorStore = useEditorStore()
// const { setFallbackResults, setMinisearch } = editorStore

// watch(protocolInfo, (val) => {
//   if (val) {
//     setFallbackResults("fields", [{
//       id: "fields",
//       title: "Fields",
//       description: "Fields",
//     }])

//     const minisearch = new MiniSearch({
//       fields: ["title", "description"],
//       storeFields: ["id", "title", "description"],
//     })

//     setMinisearch("fields", minisearch)

//     minisearch.addAll([{
//       id: "fields",
//       title: "Fields",
//       description: "Fields",
//       providerTitle: "fields",
//     }])
//   }
// }, { immediate: true })
const submenuBus = useEventBus<"request:protocol/getFields" | "response:protocol/getFields" | "refreshSubmenuItems", { provider: Chat.ContextProviderName } | ExtractResult>("submenu-eventbus")

submenuBus.on((event) => {
  if (event === "request:protocol/getFields") {
    if (formRef.value?.fieldRecord) {
      submenuBus.emit("response:protocol/getFields", formRef.value.fieldRecord)
    }
  }
})

watch(() => formRef.value?.fieldRecord, (val) => {
  if (val) {
    submenuBus.emit("refreshSubmenuItems", { provider: "protocol" })
  }
})

const { error, warning } = useClosableMessage()
async function handleRestoreDraft(data: Partial<IRecordData>, sources: string[] = []) {
  const { restoreFieldRecord } = formRef.value || {}
  if (!restoreFieldRecord) {
    warning(t("page.protocol.addRecord.noDraftFound"))
    return
  }

  try {
    restoreFieldRecord(data)
    recordData.value = data
    simulatedSources.value = Object.fromEntries(sources.map(field => [field, valueOfField(field)]))
    resetAutosaveBaseline(recordData.value)

    // await nextTick()
    // if (validate) {
    //   await validate()
    // }
  }
  catch (e) {
    if (e instanceof Error) {
      error(e.message)
    }
    if (Array.isArray(e)) {
      if (Array.isArray(e) && e.some(issue => Array.isArray(issue?.loc)))
        return
      const errors = formatValidateErrors(e as ValidateError[])

      message.error(errors.join("\n"))
    }
  }
}

async function handleManualRestore(data: Partial<IRecordData>, fields: string[], merge: boolean, removed: boolean) {
  const retained = merge ? { ...simulatedSources.value } : {}
  await handleRestoreDraft(data, fields)
  simulatedSources.value = { ...retained, ...simulatedSources.value }
  if (!removed)
    flushAutosave("manual", true)
}

// The URL identifies a draft on this browser. A plain entry continues the
// latest compatible draft; an explicit New Record allocates a separate one.
watch(
  [() => route.query.draft, () => route.query.newRecord, protocolId, () => formRef.value?.fieldRecord, loading, () => authStore.userInfo.id],
  async ([requested, fresh, id, form, busy, userId]) => {
    if (initializingDraft || !["add-protocol-record", "add-protocol-record-from-workflow"].includes(String(route.name))
      || !id || !form || busy || !userId || isReadonly.value || !displayProtocolVersion.value) {
      return
    }
    if (draftId.value && requested === draftId.value && draftOwner === userId && !fresh)
      return
    initializingDraft = true
    try {
      flushAutosave("unload", true)
      draftOwner = userId
      draftReady.value = false
      draftScope.value = { version: displayProtocolVersion.value, query: recordDraftQuery(route.query) }
      const previousId = draftId.value
      const saved = fresh === "true" ? null : getDraft<Partial<IRecordData>>(id, typeof requested === "string" ? requested : null)
      draftId.value = saved?.draftId || nanoid()
      if (previousId && previousId !== draftId.value)
        formGeneration.value += 1
      if (saved) {
        await handleRestoreDraft(extractAssetId(saved.data) || {}, saved.simulatedFields)
        autosaveState.lastSavedAt = saved.timestamp
      }
      else if (previousId) {
        await handleRestoreDraft({})
        autosaveState.lastSavedAt = 0
      }
      else if (researchWorkItem.value) {
        const initial = researchWorkItem.value.action.protocol_run?.initial_values || {}
        if (Object.keys(initial).length) {
          await handleRestoreDraft({ research_variable: initial } as Partial<IRecordData>)
          message.success(t("page.protocol.addRecord.researchWorkValuesApplied"))
        }
      }
      const query: typeof route.query = { ...route.query, draft: draftId.value }
      delete query.newRecord
      delete query.resumeDraft
      // Set the URL before allowing autosave so reload always selects this entry.
      if (requested !== draftId.value || fresh || route.query.resumeDraft)
        await router.replace({ path: route.path, query })
      resetAutosaveBaseline()
      draftReady.value = true
    }
    finally {
      initializingDraft = false
    }
  },
  { flush: "post" },
)

async function fetchRecord() {
  const { record: recordId, recordVersion } = route.query
  if (!recordId || !protocolInfo.value) {
    return
  }

  try {
    startLoading()

    const { id: protocolId } = protocolInfo.value

    const recordRes = await getProtocolRecordReport({
      recordId: recordId as string,
      protocolId,
      version: String(recordVersion || "1"),
    })

    const { labUid, projectUid, protocolUid } = route.params as {
      labUid: string
      projectUid: string
      protocolUid: string
    }
    const sourceVersion = recordRes.metadata.protocol_version
    const versionedInfo = protocolInfo.value.metadata?.version === sourceVersion
      ? protocolInfo.value
      : await fetchProtocolInfoByUid(
        { labUid, projectUid, protocolUid, version: sourceVersion },
        true,
        false,
      )
    const protocolData = versionedInfo
      ? transformFields(versionedInfo as ProtocolModels.ProjectProtocolInfo)
      : null

    const { check, step, var: varData } = recordRes.data

    const convertedData = { quiz: recordRes.data.quiz || {}, research_check: check, research_step: step, research_variable: varData } as Partial<IRecordData>

    const schema = protocolData?.json_schema
    if (schema) {
      for (const key in varData) {
        const targetSchema = _get(schema, ["research_variable", key, "properties"])
        if (targetSchema) {
          _set(convertedData, ["research_variable", key, "properties"], targetSchema)
        }
      }
    }

    protocol.value = protocolData
    editingProtocolVersion.value = sourceVersion
    recordData.value = convertedData
    simulatedSources.value = Object.fromEntries((recordRes.data.simulated_fields || []).map(key => [key, valueOfField(key)]))
    resetAutosaveBaseline(recordData.value)
  }
  catch (e) {
    if (e instanceof Error) {
      message.error(e.message)
    }
  }
  finally {
    endLoading()
  }
}

const metadata = ref({ rrec: [], comment: "" })
const expandedNames = ref<string[]>([])
function handleCollapseMetadata() {
  expandedNames.value = []
}
</script>

<style scoped lang="sass">
@use "@styles/sass/list.sass" as *

:deep(.n-form-item)
  position: relative

:deep(.n-drawer-header__main)
  flex: 1
:deep(.n-drawer-body-content-wrapper)
  padding: 0!important
</style>
