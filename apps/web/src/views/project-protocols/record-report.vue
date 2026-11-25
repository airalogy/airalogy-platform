<template>
  <resource-access-state v-if="failure" :failure="failure" @retry="retry" />
  <n-spin v-else-if="loading" class="mx-auto my-12" />
  <section v-else-if="record" class="-mx-8">
    <header class="min-h-[70px] w-full flex flex-1 flex-row flex-wrap items-center gap-y-3 px-8 py-2">
      <n-button quaternary class="mr-4 -ml-2" @click="handleRedirect">
        <template #icon>
          <n-icon size="28">
            <icon-tabler-arrow-left />
          </n-icon>
        </template>
      </n-button>
      <div class="mr-auto max-w-full min-w-0 w-fit">
        <div class="flex flex-wrap items-center gap-2">
          <h3 class="text-5 font-500">
            {{ $t("page.protocol.recordReport.title") }}
          </h3>

          <template v-if="user">
            <span>{{ $t("common.by") }}</span>
            <n-avatar
              :src="user.avatar_url || '/images/avatar_default.svg'"
              :size="32"
              color="transparent"
              object-fit="cover"
              class="vertical-middle"
            />
            <global-member-item
              :item="user"
              :is-compact="false"
              type="project"
              class="!min-w-fit"
            />
          </template>
          <n-time :time="recordInfoData?.time ? dayjs(recordInfoData?.time).toDate() : undefined" class="text-text-secondary" />
          <n-tag type="warning" size="small">
            {{ $t("common.readOnly") }}
          </n-tag>

          <n-popover
            v-if="protocolInfo && recordInfoData"
            trigger="hover"
            placement="bottom-start"
            :show-arrow="false"
            raw
            class="max-w-lg rounded-lg bg-white p-2 shadow-lg"
          >
            <template #trigger>
              <n-button
                size="tiny"
                quaternary
                class="opacity-70 hover:opacity-100"
              >
                <template #icon>
                  <n-icon size="16">
                    <icon-tabler-info-circle />
                  </n-icon>
                </template>
                {{ $t("common.info") }}
              </n-button>
            </template>

            <div class="w-96">
              <protocol-info-card
                v-if="protocolInfo"
                :protocol-info="protocolInfo"
                :title="$t('page.protocol.recordReport.protocolDetails')"
                class="border-0"
              />

              <!-- Record Information -->
              <record-info-card
                :record-info="recordInfoData"
                class="mt-2 border-0"
              />
            </div>
          </n-popover>
        </div>
        <protocol-title-section :protocol-info="protocolInfo" :title="protocolInfo?.name" :is-protocol-link="true" :show-icon="false" size="tiny" />
      </div>

      <aira-action-button v-if="aira?.context.value && isRevisionReady" class="mr-2" data-testid="record-analyze" :aria-expanded="aira.expanded.value" @click="formRef?.analyzeReport($event.currentTarget)">
        {{ $t("page.airaActions.analyze") }}
      </aira-action-button>
      <n-button v-if="recordData" type="primary" class="mr-4" @click="handleExportPdf()">
        {{ $t("page.protocol.recordReport.exportPdf") }}
      </n-button>
      <n-button type="warning" class="mr-4" :disabled="!isRevisionReady" @click="handleModify()">
        {{ $t("page.protocol.addRecord.reviseAction") }}
      </n-button>
      <n-tooltip v-if="canDeleteByRole" :disabled="!deleteBlockedReason">
        <template #trigger>
          <span class="inline-flex">
            <n-button
              type="error"
              :disabled="deleting || !!deleteBlockedReason"
              :class="{ 'opacity-50 cursor-not-allowed': !!deleteBlockedReason }"
              @click="handleDeleteClick"
            >
              {{ $t("common.delete") }}
            </n-button>
          </span>
        </template>
        {{ deleteBlockedReason }}
      </n-tooltip>
    </header>
    <div
      v-if="record && protocolInfo"
      class="flex flex-wrap items-center gap-2 px-8 pb-3"
    >
      <n-tag size="small" :bordered="false">
        {{ $t("page.protocol.schemaGovernance.recordRevision", { version: record.record_version }) }}
      </n-tag>
      <n-tag
        v-if="record.metadata.revision_kind"
        size="small"
        :type="record.metadata.revision_kind === 'schema_migration' ? 'warning' : 'default'"
        :bordered="false"
      >
        {{ record.metadata.revision_kind }}
      </n-tag>
      <record-schema-governance
        :protocol-id="String(protocolInfo.id)"
        :record-id="record.record_id"
        :source-version="record.metadata.protocol_version"
        :allow-migration="authStore.isLogin"
        @migrated="handleSchemaMigrated"
      />
    </div>
    <protocol-rating-entry v-if="record && protocolInfo" :protocol-id="protocolInfo.id" :version="record.metadata.protocol_version" :record-id="String(record.record_id)" class="mb-3 px-8" />
    <n-divider class="!mt-0" />
    <n-spin
      :show="loading" class="w-full px-4 md:h-[calc(100vh-165px)] md:pl-8 md:pr-0"
      :content-class="`w-full overflow-visible md:h-full ${protocol ? '' : ' flex-center flex-col'}`"
    >
      <protocol-add-record-form
        v-if="protocol && protocolInfo && protocolId"
        ref="formRef"
        v-model:collapsed="isCollapsed"
        :protocol="protocol"
        :protocol-id="protocolId"
        :key="JSON.stringify([authStore.userInfo.id, protocolId, record?.record_id, record?.record_version, record?.metadata.protocol_version])"
        :readonly="true"
        :recorder-record-id="record?.record_id"
        :record-revision="record?.record_version"
        :recorder-version="record?.metadata.protocol_version"
        :simulated-fields="simulatedFields"
        :record-data="recordData"
        :saved-record-data="record?.data"
        @update:field="handleUpdateField"
        @update:split-size="handleUpdateSize"
      />
    </n-spin>

    <!-- Preview Modal -->
    <n-modal
      v-model:show="showPreviewModal"
      preset="card"
      class="max-w-6xl w-full"
      content-class="overflow-hidden block"
      :closable="true"
      :mask-closable="false"
      @close="handleCancelPreview"
      @after-leave="handleAfterLeave"
    >
      <template #header>
        <div class="flex items-center gap-2">
          <span>{{ $t("page.protocol.recordReport.exportTitle") }}</span>
          <n-input
            v-if="isEditingFilename"
            ref="filenameInputRef"
            v-model:value="previewFilename"
            class="flex-1"
            :placeholder="$t('page.protocol.recordReport.filenamePlaceholder')"
            @keyup.enter="handleFinishEditFilename"
            @keyup.esc="handleCancelEditFilename"
            @blur="handleFinishEditFilename"
          />

          <n-tag v-else type="primary" size="large">
            {{ previewFilename }}
          </n-tag>
        </div>
      </template>
      <template #header-extra>
        <tooltip-button
          :tooltip="isEditingFilename ? $t('page.protocol.recordReport.saveFilename') : $t('page.protocol.recordReport.editFilename')"
          quaternary
          size="small"
          :disabled="isGenerating"
          @click="handleToggleEditFilename"
        >
          <template #icon>
            <n-icon>
              <icon-tabler-edit v-if="!isEditingFilename" />
              <icon-tabler-check v-else />
            </n-icon>
          </template>
        </tooltip-button>
      </template>
      <pdf-viewer :pdf-url="previewPdfUrl" content-class="h-[70vh]" scroll-to-load :loading="isGenerating" :description="isGenerating ? $t('page.protocol.recordReport.generatingPdf') : ''" :error="error" @retry-load="handleExportPdf" />
      <template #footer>
        <div class="flex justify-end gap-3">
          <n-button @click="handleCancelPreview">
            {{ $t("common.cancel") }}
          </n-button>
          <n-button
            type="primary"
            :loading="isGenerating"
            :disabled="isGenerating || !previewPdfBlob"
            @click="handleConfirmExport"
          >
            <template #icon>
              <n-icon>
                <icon-tabler-download />
              </n-icon>
            </template>
            {{ isGenerating ? $t("page.protocol.recordReport.generating") : $t("page.protocol.recordReport.exportPdf") }}
          </n-button>
        </div>
      </template>
    </n-modal>

    <!-- Delete Confirmation Modal -->
    <delete-confirmation-modal
      :show="showDeleteModal"
      :entity-name="$t('common.record')"
      :item-name="recordInfoData?.id || $t('common.record')"
      :delete-confirmation-text="deleteConfirmationText"
      :is-delete-confirmation-valid="isDeleteConfirmationValid"
      :deleting="deleting"
      :extra-warning="deleteAdminWarning || undefined"
      @update:delete-confirmation-text="deleteConfirmationText = $event"
      @confirm="confirmDelete"
      @cancel="cancelDelete"
    />
  </section>
</template>

<script setup lang="ts">
import type { IRecordData, IRecordDataKey } from "@airalogy/aimd-core/types"
import type { ProtocolModels } from "@airalogy/shared/types"
import type { ITimelineItem } from "./types"
import AiraActionButton from "@/components/common/aira-action-button.vue"
import ResourceAccessState from "@/components/common/resource-access-state.vue"
import ProtocolRatingEntry from "@/components/protocol/protocol-rating-entry.vue"
import { useBoolean, useProjectPermissions } from "@/composables"
import { useResourcePage } from "@/composables/useResourcePage"
import { useRouterPush } from "@/composables/useRouterPush"
import { useSeoMeta } from "@/composables/useSeoMeta"
import { useWorkspaceAira } from "@/composables/useWorkspaceAira"
import { deleteResearchRecord, fetchProtocolRecords, getProtocolInfoByUid, getProtocolRecordReport } from "@/service/api/project-protocols"
import { getProjectInfoById } from "@/service/api/projects"
import { fetchUserInfo } from "@/service/api/users"
import { useRouteStore } from "@/store/modules/route"
import { getRecordDeleteGraceDays } from "@/utils/env"
import { buildSeoUrl } from "@/utils/seo"
import { PdfPreview as PdfViewer } from "@airalogy/components"
import { useClosableMessage, useHtmlToPdf } from "@airalogy/composables"
import { downloadAsUrl, formatDate } from "@airalogy/shared/utils"
import IconTablerCheck from "~icons/tabler/check"
import IconTablerEdit from "~icons/tabler/edit"
import dayjs from "dayjs"
import { get as _get, set as _set } from "lodash-es"
import { nanoid } from "nanoid"
import { useI18n } from "vue-i18n"
import { useDeleteConfirmation } from "../../components/common/settings"
import { useAuthStore } from "../../store/modules/auth"
import { useOrProvideProjectInfoStore } from "./hooks/useProjectInfoStore"
import { useProvideProtocolInfoStore } from "./hooks/useProtocolInfoStore"
import ProtocolAddRecordForm from "./modules/protocol/protocol-add-record-form.vue"
import RecordSchemaGovernance from "./modules/protocol/record-schema-governance.vue"
import { createProtocolRecordData } from "./utils"

defineOptions({ name: "RecordReport" })

const emits = defineEmits<IEmits>()

interface IEmits {
  (e: "modal:close"): void
  (e: "modal:open"): void
}

const route = useRoute()
const router = useRouter()

const aira = useWorkspaceAira()
const authStore = useAuthStore()

const { removeCacheRoutes } = useRouteStore()

const protocol = ref<ProtocolModels.ProtocolInfo | null>(null)
const record = ref<ProtocolModels.RecordInfo | null>(null)
const error = ref<string>("")
interface RecordReportFormRef {
  analyzeReport: (trigger: HTMLElement) => void
  validate: () => any
  toggle: () => void
  preparedData: () => {
    template: string
  }
  preparedReport: () => string
  previewRef: HTMLDivElement | null
  restoreFieldRecord?: (data?: Partial<IRecordData>) => void | Promise<void>
}

const formRef = ref<RecordReportFormRef | null>(null)

const instanceId = nanoid()
provide("protocol-workflow-channel", { id: instanceId })

const message = useClosableMessage()
const { t } = useI18n()
const { protocolInfo, protocolId } = useProvideProtocolInfoStore(null)

const simulatedFields = ref<string[]>([])
const recordData = ref<Partial<IRecordData>>({} as IRecordData)
const { projectInfo } = useOrProvideProjectInfoStore(null)
const { canDeleteOthersRecords, canDeleteOwnRecords } = useProjectPermissions(projectInfo)

const deleteGraceDays = computed(() => getRecordDeleteGraceDays())
const latestRecordNumber = ref<number | null>(null)

const canDeleteByRole = computed(() => {
  if (canDeleteOthersRecords.value) {
    return true
  }
  if (canDeleteOwnRecords.value && record.value?.metadata?.record_current_version_submission_user_id === authStore.userInfo.id) {
    return true
  }

  return false
})

const hasNewerRecord = computed(() => {
  const currentNumber = record.value?.metadata?.record_num
  if (currentNumber == null || latestRecordNumber.value == null) {
    return false
  }
  return currentNumber < latestRecordNumber.value
})

const isDeleteGraceExpired = computed(() => {
  if (canDeleteOthersRecords.value) {
    return false
  }
  const createdAt = record.value?.metadata?.record_current_version_submission_time
  if (!createdAt) {
    return false
  }
  return dayjs().isAfter(dayjs(createdAt).add(deleteGraceDays.value, "day"))
})

const deleteBlockedReason = computed(() => {
  if (!canDeleteByRole.value) {
    return ""
  }
  if (isDeleteGraceExpired.value) {
    return t("page.protocol.records.deleteBlockedExpired", { days: deleteGraceDays.value })
  }
  if (latestRecordNumber.value == null) {
    return t("page.protocol.records.deleteBlockedLoading")
  }
  if (hasNewerRecord.value) {
    return t("page.protocol.records.deleteBlockedLatest")
  }
  return ""
})

const deleteAdminWarning = computed(() => {
  if (!canDeleteOthersRecords.value) {
    return ""
  }
  return t("page.protocol.records.deleteAdminWarning", { days: deleteGraceDays.value })
})
// Preview modal state
const showPreviewModal = ref(false)
const previewPdfBlob = ref<Blob | null>(null)
const previewFilename = ref("")
const isEditingFilename = ref(false)
const originalFilename = ref("")
const filenameInputRef = ref<any>(null)
const previewPdfUrl = computed(() => {
  if (!previewPdfBlob.value) {
    return ""
  }
  return URL.createObjectURL(previewPdfBlob.value)
})

const recordInfoData = computed(() => {
  if (!record.value) {
    return null
  }

  const { airalogy_record_id, metadata, data, record_id } = record.value
  const { protocol_id, record_current_version_submission_user_id } = metadata

  const convertedData = createProtocolRecordData(data)

  const timelineItem: Omit<ITimelineItem, "order"> = {
    id: airalogy_record_id,
    recordId: record_id,
    operator: record_current_version_submission_user_id,
    operatorId: record_current_version_submission_user_id,
    operatorUsername: record_current_version_submission_user_id,
    field: convertedData,
    protocolId: protocol_id,
    record: record.value,
    time: metadata.record_current_version_submission_time,
  }

  return timelineItem
})

const recordReportSeo = computed(() => {
  if (!protocolInfo.value) {
    return null
  }

  const protocolName = protocolInfo.value.name || protocolInfo.value.uid || "Protocol"
  const recordNumber = record.value?.metadata?.record_num
  const pageTitle = recordNumber
    ? `Record ${recordNumber} of ${protocolName} | Airalogy`
    : `${protocolName} Record Report | Airalogy`
  const description = recordNumber
    ? `Read public record ${recordNumber} for ${protocolName} on Airalogy.`
    : `Read a public record report for ${protocolName} on Airalogy.`

  return {
    title: pageTitle,
    description,
    canonical: route.path,
    robots: "noindex,follow",
    ogType: "article" as const,
    image: "/images/research_placeholder.png",
    modifiedTime: record.value?.metadata?.record_current_version_submission_time || protocolInfo.value.updated_at || null,
    jsonLd: {
      "@context": "https://schema.org",
      "@type": "CreativeWork",
      "name": pageTitle,
      description,
      "url": buildSeoUrl(route.path),
      "isPartOf": {
        "@type": "WebSite",
        "name": "Airalogy",
        "url": buildSeoUrl("/"),
      },
    },
  }
})

useSeoMeta(recordReportSeo)

function handleAfterLeave() {
  if (previewPdfUrl.value) {
    URL.revokeObjectURL(previewPdfUrl.value)
  }
  previewPdfBlob.value = null
  previewFilename.value = ""
  isEditingFilename.value = false
  originalFilename.value = ""
}

// Filename editing functions
function handleToggleEditFilename() {
  if (isEditingFilename.value) {
    handleFinishEditFilename()
  }
  else {
    originalFilename.value = previewFilename.value
    isEditingFilename.value = true
    nextTick(() => {
      filenameInputRef.value?.focus()
    })
  }
}

function handleFinishEditFilename() {
  isEditingFilename.value = false
  // Ensure .pdf extension
  if (previewFilename.value && !previewFilename.value.toLowerCase().endsWith(".pdf")) {
    previewFilename.value += ".pdf"
  }
}

function handleCancelEditFilename() {
  previewFilename.value = originalFilename.value
  isEditingFilename.value = false
}

function handleUpdateField(payload: {
  scope: IRecordDataKey
  prop: string
  value: string | number | boolean
  info?: any
}) {
  const { scope, prop, value } = payload

  _set(recordData.value, [scope, prop], value)
}

const { bool: isCollapsed, toggle: toggleCollapsed, setFalse: expand } = useBoolean(false)
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

const { routerPushByKey } = useRouterPush()
function handleRedirect() {
  const { lab, project, uid } = protocolInfo.value || {}
  if (lab && project && uid) {
    void routerPushByKey("protocol-detail", {
      params: { labUid: lab.uid, projectUid: project.uid, protocolUid: uid },
    })
  }
  else {
    router.back()
  }
}
const {
  showDeleteModal,
  deleteConfirmationText,
  deleting,
  isDeleteConfirmationValid,
  handleDelete: openDeleteModal,
  cancelDelete,
  confirmDelete,
} = useDeleteConfirmation(handleDeleteRecord, "Record", handleDeleteSuccess)

function handleDeleteClick() {
  if (deleting.value) {
    return
  }
  if (deleteBlockedReason.value) {
    message.warning(deleteBlockedReason.value)
    return
  }
  openDeleteModal()
}

async function handleDeleteSuccess() {
  const { lab, project } = protocolInfo.value || {}
  if (lab && project) {
    routerPushByKey("project-protocols", {
      params: {
        labUid: lab.uid,
        projectUid: project.uid,
      },
    })
  }
}

async function handleDeleteRecord() {
  const { id: protocolId } = protocolInfo.value || {}
  const { record_id: recordId, record_version: recordVersion } = record.value || {}
  if (!protocolId || !recordId || !recordVersion) {
    return { data: null, error: new Error("Wrong params") }
  }

  const { data, error } = await deleteResearchRecord(protocolId, recordId, recordVersion)
  return { data, error }
}

async function readRecordPage(signal: AbortSignal) {
  const { recordId, recordVersion, protocolUid, labUid, projectUid, protocolVersion } = route.params as Record<string, string>
  const readProtocol = async (version: string) => {
    const { data, error } = await getProtocolInfoByUid({ labUid, projectUid, protocolUid, version }, false, signal)
    if (!data)
      throw error
    return data
  }
  const info = await readProtocol(protocolVersion)
  const recordRes = await getProtocolRecordReport({ recordId, protocolId: info.id, version: recordVersion }, signal)
  const protocolData = info.metadata?.version === recordRes.metadata.protocol_version
    ? info
    : await readProtocol(recordRes.metadata.protocol_version)
  const convertedData = createProtocolRecordData(recordRes.data)
  const variableData = convertedData.research_variable

  const schema = protocolData?.json_schema
  if (schema) {
    for (const key in variableData) {
      const targetSchema = _get(schema, ["research_variable", key, "properties"])
      if (targetSchema) {
        _set(convertedData, ["research_variable", key, "properties"], targetSchema)
      }
    }
  }
  return { info: protocolData, recordRes, convertedData }
}

async function loadRecordControls(info: ProtocolModels.ProjectProtocolInfo) {
  const openedRecord = record.value
  const [project, latest] = await Promise.allSettled([
    getProjectInfoById(info.project_id),
    fetchProtocolRecords(info.id, { page: 1, pageSize: 1 }),
  ])
  if (record.value !== openedRecord)
    return
  if (project.status === "fulfilled")
    projectInfo.value = project.value
  if (latest.status === "fulfilled")
    latestRecordNumber.value = latest.value.data?.records?.[0]?.metadata?.record_num ?? null
}

const { exportToPdf, isGenerating } = useHtmlToPdf()

async function handleExportPdf(retry = 1) {
  if (!formRef.value) {
    message.error(t("page.protocol.recordReport.formRefMissing"))
    return
  }

  const content = unrefElement(formRef.value.previewRef)

  if (!content) {
    message.error(t("page.protocol.recordReport.noContent"))
    return
  }

  await nextTick()
  const { lab, project, name } = protocolInfo.value || {}
  const { operatorUsername, time } = recordInfoData.value || {}
  const formattedTime = time ? formatDate(time, "date-time") : ""
  // Generate filename based on protocol info
  const filename = `${[
    lab?.name,
    project?.name,
    name,
    operatorUsername,
    formattedTime,
  ].filter(Boolean).join("-")}.pdf`

  try {
    // Show modal first
    previewFilename.value = filename
    showPreviewModal.value = true

    const pdfBlob = await exportToPdf(content, {
      filename,
      margin: [10, 10],
      html2canvas: {
        // scale: 2,
        useCORS: true,
        scrollY: 0,
      },
      jsPDF: {
        format: "a4",
        orientation: "portrait",
      },
    }, true)

    if (pdfBlob) {
      // Store PDF data for modal
      previewPdfBlob.value = pdfBlob
      error.value = ""
    }
  }
  catch (err) {
    if (retry) {
      await handleExportPdf(retry - 1)
    }
    else {
      const errMsg = t("page.protocol.recordReport.previewFailed", {
        message: err instanceof Error ? err.message : t("common.unknownError"),
      })

      message.error(errMsg)
      error.value = errMsg
    }
  }
}

function handleConfirmExport() {
  if (!previewPdfBlob.value) {
    message.error(t("page.protocol.recordReport.noPdf"))
    return
  }

  try {
    // Create download link for the already-generated PDF
    downloadAsUrl(previewPdfUrl.value, previewFilename.value)

    message.success(t("page.protocol.recordReport.exportSuccess"))
    handleCancelPreview()
  }
  catch (error) {
    message.error(t("page.protocol.recordReport.exportFailed", {
      message: error instanceof Error ? error.message : t("common.unknownError"),
    }))
  }
}

function handleCancelPreview() {
  showPreviewModal.value = false
}

const user = asyncComputed(async () => {
  if (!record.value) {
    return null
  }

  const username = record.value.metadata.record_current_version_submission_user_id
  if (!username) {
    return null
  }

  const res = await fetchUserInfo({ username }, false)
  if (res) {
    return res.data
  }

  return null
})

async function handleSchemaMigrated(migrated: {
  version: number
  protocol_version: string
}) {
  await router.replace({
    name: "protocol-record-report",
    params: {
      ...route.params,
      protocolVersion: migrated.protocol_version,
      recordVersion: String(migrated.version),
    },
  })
}

const { failure, loading, retry } = useResourcePage(
  () => route.path,
  readRecordPage,
  (result) => {
    protocolInfo.value = result?.info ?? null
    record.value = result?.recordRes ?? null
    protocol.value = result?.info ?? null
    recordData.value = result ? { ...result.convertedData, quiz: result.recordRes.data.quiz || {} } as Partial<IRecordData> : {}
    simulatedFields.value = result?.recordRes.data.simulated_fields || []
    projectInfo.value = null
    latestRecordNumber.value = null
    if (result)
      void loadRecordControls(result.info)
  },
)

const isRevisionReady = computed(() => !loading.value && !!protocolInfo.value && !!record.value && !!protocol.value)

function handleModify() {
  if (!isRevisionReady.value) {
    return
  }

  const { recordId, protocolUid, labUid, projectUid, protocolVersion } = route.params as {
    recordId: string
    protocolUid: string
    labUid: string
    projectUid: string
    protocolVersion: string
  }
  routerPushByKey("add-protocol-record", {
    params: {
      protocolUid,
      labUid,
      projectUid,
      protocolVersion,
    },
    query: {
      record: recordId,
      recordVersion: String(record.value?.record_version || 1),
    },
  })
}

// Watch for recordData changes and restore table data
watch([recordData, () => formRef.value], async ([data, form]) => {
  const restoreFieldRecord = form?.restoreFieldRecord
  if (data && Object.keys(data).length > 0 && restoreFieldRecord) {
    await nextTick()
    await restoreFieldRecord(data)
  }
}, { immediate: true })

onActivated(() => {
  removeCacheRoutes("RecordReport" as any)
})
onDeactivated(() => {
  handleAfterLeave()
})
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
