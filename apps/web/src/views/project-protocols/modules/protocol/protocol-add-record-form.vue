<template>
  <add-record-layout
    v-if="fieldRecordDefault"
    v-model:collapsed="isCollapsed"
    v-model:split-size="splitSize"
    v-model:selected-tab="selectedTab"
    :dom-mounted="domMounted"
    :default-spilt-size="props.defaultSpiltSize"
    responsive :single-fields-tab="!hasWorkflowScope"
  >
    <template #tabs>
      <n-tab-pane
        name="form-fields" class="relative" :tab="$t('common.fields')"
        display-directive="show"
        :style="{ paddingLeft: isCollapsed ? '32px' : undefined }"
      >
        <template #tab>
          <field-form-icon
            :selected="selectedTab === 'form-fields'" data-tab="form-fields"
            @click="handleCollapse"
          />
        </template>
        <div v-if="hostedContent || props.readonly" v-show="!isCollapsed" class="record-fields-form px-4">
          <aimd-recorder
            layout="field-panel" :field-display="props.readonly ? reportPresentation : recordingFieldDisplay" :content="props.readonly ? templateRef : hostedContent" :readonly="props.readonly"
            :panel-variables="drawerVariables" :model-value="props.readonly ? savedPanelData : nativeRecord"
            :current-user-name="authStore.userInfo.name" :locale="locale" :show-search="false"
            :field-meta="nativeMeta" :validation-schema="nativeSchema" :field-state="props.readonly ? undefined : nativeState"
            :resource-resolvers="resourceResolvers" :field-adapters="props.readonly ? undefined : panelAdapters"
            :wrap-field="props.readonly ? undefined : wrapDrawerField"
            :upload-file="props.readonly ? undefined : uploadNativeFile" :resolve-file-info="resolveNativeFile"
            @input.capture="!props.readonly && markInput($event)" @change.capture="!props.readonly && markInput($event)"
            @navigate-field="focusNativeField" @mousedown.capture="keepResourceSearchFocus"
            @field-change="handleNativeField" @assigner-request="handleNativeAssigner"
            @assigner-cancel="({ fieldKey }) => handleAssignerCancel({ prop: fieldKey })"
          />
        </div>
        <n-collapse v-if="props.readonly && legacyPanelGroups.length"
                    v-model:expanded-names="expandedNamesRef" display-directive="show"
                    class="px-4"
                    :class="{ hidden: isCollapsed }"
        >
          <n-form
            ref="formRef" class="record-fields-form h-full pb-3" :rules="validationRules" :model="fieldModel"
            @input.capture="markInput" @change.capture="markInput"
          >
            <n-collapse-item v-for="{ scopeName, idx } in legacyPanelGroups" :key="scopeName" :name="scopeName">
              <template #header>
                <span class="text-4 font-500 capitalize">
                  {{ fieldRecordDefault.field[scopeName]?.__SCOPE__?.title || scopeKeyRecord[scopeName] }}
                </span>
              </template>
              <template #header-extra>
                <n-tag :color="getTagColor(scopeName)">
                  <n-ellipsis>
                    {{ scopeKeyRecord[scopeName] }}
                  </n-ellipsis>
                </n-tag>
              </template>
              <template v-for="(prop, index) in fieldPropList[idx]" :key="prop">
                <protocol-add-record-form-item
                  v-bind="createFormItemProps(scopeName, prop)"
                  :data-recorder-field="scopeName === 'research_variable' ? prop : undefined"
                  :should-scroll="shouldScroll"
                  @field:change="handleFieldChange"
                />
                <n-divider v-if="index !== fieldPropList[idx].length - 1" class="!mb-4 !mt-0" />
              </template>
            </n-collapse-item>
          </n-form>
        </n-collapse>
      </n-tab-pane>
      <n-tab-pane
        v-if="hasWorkflowScope"
        name="workflow"
        class="relative"
        :tab="$t('page.protocol.workflow.workspaceTab')"
        display-directive="show"
        :style="{ paddingLeft: isCollapsed ? '32px' : undefined }"
      >
        <template #tab>
          <n-icon
            :size="24"
            class="mx-auto cursor-pointer rounded-lg p-2 transition-colors"
            :class="selectedTab === 'workflow' ? 'bg-primary/10 text-primary' : 'text-gray-500 hover:bg-gray-100'"
            data-tab="workflow"
            @click="handleCollapse"
          >
            <icon-tabler-git-branch />
          </n-icon>
        </template>

        <div class="px-4" :class="{ hidden: isCollapsed }">
          <div class="mb-2 h-10 w-fit rounded bg-[#2B2B38] px-4 text-[1.125rem] text-white leading-10">
            {{ $t("page.protocol.workflow.workspaceTab") }}
          </div>
          <n-text depth="3">
            {{ $t("page.protocol.workflow.workspaceTabDescription") }}
          </n-text>
        </div>
      </n-tab-pane>
    </template>
    <template #content>
      <context-aira-panel handles-field-selection v-if="authStore.isLogin && instanceStore.aiEnabled" :key="JSON.stringify([protocolId, recorderVersion, recorderRecordId, recordRevision, props.readonly])"
                          :title="protocol?.name" :version="recordRevision && recorderVersion ? $t('page.airaActions.version', { version: recorderVersion, revision: recordRevision }) : recorderVersion">
        <chat-component ref="assistantChat" v-model:role="role" v-model:could-change-role="couldChangeRole" hide-collapse in-side-panel
                        class="relative min-h-0 w-full flex-1" :protocol-id="props.protocolId"
                        source="protocol" enable-tool-action :airalogy-id="reportScope || airalogyId" :report-scope="reportScope" :resolve-file="getCachedAttachment" />
      </context-aira-panel>
      <slot name="prefix" />
      <n-alert v-if="receipt || pending.size || edits.size || showPreviewLink" class="mb-3 break-words" :type="pending.size ? 'warning' : 'info'" data-testid="recorder-receipt">
        <div class="whitespace-pre-line" aria-live="polite">{{ receipt }}</div>
        <div v-if="showPreviewLink" aria-live="polite">{{ $t("page.recorderAira.previewOnly") }}</div>
        <router-link v-if="showPreviewLink && editorPreviewRoute" :to="editorPreviewRoute" target="_blank" rel="noopener noreferrer" class="text-primary underline" data-testid="open-example-preview">
          {{ $t("page.recorderAira.openPreview") }}
        </router-link>
        <details v-if="pending.size || edits.size">
          <summary class="cursor-pointer">
            {{ pending.size ? $t("page.recorderAira.replace") : $t("page.recorderAira.filled") }}
            ({{ pending.size || edits.size }})
          </summary>
          <ul class="my-2 list-none p-0">
            <li v-for="[field, change] in (pending.size ? pending : edits)" :key="field" class="flex flex-wrap items-center gap-x-2">
              <span class="font-medium">{{ field }}</span>
              <recorder-field-review :change="change" :pending="pending.has(field)" :busy="busy" @accept="accept" @dismiss="dismiss" @undo="undo" />
            </li>
          </ul>
        </details>
        <template v-if="pending.size">
          <p>{{ $t("page.recorderAira.previewHint") }}</p>
          <div class="flex flex-wrap gap-2">
            <n-button size="small" :disabled="busy" @click="dismiss()">{{ $t("page.recorderAira.exit") }}</n-button>
            <n-button size="small" type="primary" data-testid="accept-remaining" :disabled="busy" @click="accept()">
              {{ $t("page.recorderAira.adopt") }}
            </n-button>
          </div>
        </template>
        <n-button v-else-if="edits.size" size="small" :disabled="busy" @click="undo()">{{ $t("page.recorderAira.undo") }}</n-button>
      </n-alert>
      <n-alert v-if="simulatedFields?.length" type="warning" class="mb-3" data-testid="simulated-fields" :title="$t('page.recorderAira.simulatedOrigin')">
        {{ simulatedFields.join(", ") }}
      </n-alert>
      <workflow-workspace
        v-if="selectedTab === 'workflow' && hasWorkflowScope"
        :workflow-id="workflowId"
        :readonly="props.readonly"
      />
      <n-form
        v-else-if="fieldRecordDefault"
        class="platform-aimd-form-preview"
        @input.capture="markInput"
        @change.capture="markInput"
        :rules="props.readonly ? undefined : validationRules"
        :model="previewValue"
      >
        <record-report-presentation v-if="props.readonly" v-model="reportPresentation" />
        <record-report-presentation v-else v-model="recordingFieldDisplay" for-recording />
        <aimd-markdown-preview v-if="props.readonly"
                               ref="previewRef" :content="templateRef" mode="report" :readonly-record-data="readonlyRecordData" :record-presentation="reportPresentation" :render-options="{ locale }"
                               class="record-inline-content" :mermaid-component="MermaidBlock" :resolve-url="resolvePreviewFile"
                               body-class="markdown-body" @render:result="handlePreviewRendered"
        />
        <div v-else ref="recorderRoot" v-protocol-preview-assets="resolvePreviewFile" @drop.capture="captureTableDrop">
          <aimd-recorder
            ref="nativeRecorder" class="record-inline-content" :field-display="recordingFieldDisplay" :content="hostedContent" :model-value="nativeRecord"
            :locale="locale" :current-user-name="authStore.userInfo.name"
            :validation-schema="nativeSchema" :field-meta="nativeMeta" :field-state="nativeState"
            :field-adapters="hostAdapters" :wrap-field="wrapNativeField" :resource-resolvers="resourceResolvers"
            :upload-file="uploadNativeFile" :resolve-file-info="resolveNativeFile"
            @fields-change="handleNativeFields" @update:model-value="handleNativeSnapshot"
            @table-add-row="({ tableName }) => writeNativeTable(tableName)"
            @table-remove-row="({ tableName }) => writeNativeTable(tableName)"
            @mousedown.capture="keepResourceSearchFocus" @field-change="handleNativeField" @assigner-request="handleNativeAssigner"
            @assigner-cancel="({ fieldKey }) => handleAssignerCancel({ prop: fieldKey })"
          />
        </div>
        <protocol-bubble-menu v-if="instanceStore.aiEnabled && (recorderRoot || previewRef?.rootElement)"
                              :container-ref="(recorderRoot || previewRef?.rootElement)!" />
      </n-form>
    </template>
  </add-record-layout>
  <!-- <asset-aimd v-if="domMounted && props.protocol" :uuid="props.protocol.id" /> -->

  <!-- Assigner Progress Modal -->
  <assigner-progress-modal
    :state="assignerProgressModalState"
    @close="handleAssignerProgressClose"
    @toggle-detail="handleToggleDetail"
  />
</template>

<script setup lang="ts">
import type { IEmits as AIMDEmits, IAIMDWrapperProps } from "@/components/custom/aimd/types/aimd-types"
import type { AimdTemplateEnv, IRecordData, IRecordDataKey, ScopeFieldKey } from "@airalogy/aimd-core/types"
import type { AimdFieldMeta, AimdFileResolveContext, AimdProtocolRecordData, AimdRecorderFieldAdapters, AimdResourceResolverMap, FieldEventPayload } from "@airalogy/aimd-recorder"
import type { ContextItemWithId } from "@airalogy/components/chat/providers/types"
import type { CurrentRecorderRecordFieldSummary } from "@airalogy/components/chat/providers/useChatProvider"

import type { ResolveContextItemPayload } from "@airalogy/components/chat/utils/resolveInput"
import type { AddToChatPayload, BubbleMenuEventName, BubbleMenuEventPayload } from "@airalogy/composables/useBubbleMenu"

import type { ProtocolModels } from "@airalogy/shared"
import type { FormValidate } from "naive-ui/es/form/src/interface"
import type { TagColor } from "naive-ui/es/tag/src/common-props"

import type { VNode } from "vue"
import type { IFieldChangePayload } from "./types/types"
import ChatComponent from "@/components/chat/index.vue"
import ContextAiraPanel from "@/components/common/context-aira-panel.vue"
import AddRecordLayout from "@/components/custom/add-record-layout.vue"
import AIMDItem from "@/components/custom/aimd/components/aimd-item.vue"
import { useAIMDProvide } from "@/components/custom/aimd/composables/useAIMDHelpers"
import { platformResourceResolverKey } from "@/components/custom/aimd/resourceResolver"
import { useNaiveForm } from "@/composables"
import { useWorkspaceAira } from "@/composables/useWorkspaceAira"
import { getCachedAttachment, postAddAttachments } from "@/service/api/attachments"
import { getReferenceAssets } from "@/service/api/project-protocols"
import {
  fetchResource,
  fetchResourceAvailability,
  fetchResourceTypes,
  prepareResourceOutput,
  searchResourceRefs,
} from "@/service/api/resources"
import { useAuthStore } from "@/store/modules/auth"

import { useInstanceStore } from "@/store/modules/instance"
import { themeSettings } from "@/theme/settings"
import { protocolFileEventOwnerKey, syncPreviewFileEvent } from "@/utils/aimd-file-events"
import { aimdFileReference } from "@/utils/aimd-files"
import { vProtocolPreviewAssets } from "@/utils/protocolPreviewAssets"
import { hostedRecorderContent } from "@/utils/recorderMarkdown"
import { resolveProtocolFile as resolveProtocolFileUtil } from "@/utils/resolveProtocolFile"
import { bubbleMenuEventKey, fieldEventKey } from "@/utils/template/eventKey"
import { getAimdFieldTitle, getAimdFileKindFromType } from "@airalogy/aimd-core"
import { toTemplateEnv } from "@airalogy/aimd-core/utils"
import { AimdRecorder } from "@airalogy/aimd-recorder"
import { parseAndExtract } from "@airalogy/aimd-renderer"
import { AimdMarkdownPreview } from "@airalogy/aimd-renderer/vue"
import { useChatProvider } from "@airalogy/components/chat/providers/useChatProvider"
import MermaidBlock from "@airalogy/components/markdown-editor/modules/mermaid/mermaid-block.vue"
import ProtocolBubbleMenu from "@airalogy/components/protocol-bubble-menu.vue"
import { useClosableMessage } from "@airalogy/composables"
import { $t } from "@airalogy/shared/locales"
import { scopeKeyRecord, scopeNameRecord } from "@airalogy/shared/utils/schema"
import { useEventBus } from "@vueuse/core"
import IconMessagePlus from "~icons/tabler/message-plus"
import Big from "big.js"
import { cloneDeepWith as _cloneDeepWith, get as _get, isEqual } from "lodash-es"
import { nanoid } from "nanoid"
import { useI18n } from "vue-i18n"
import { useProtocolInfoStore } from "../../hooks/useProtocolInfoStore"
import { processFieldValue } from "../../utils"
import RecordReportPresentation from "../record-report-presentation.vue"
import { useRecordingFieldDisplay, useRecordReportPresentation } from "../useRecordReportPresentation"
import AssignerProgressModal from "./components/AssignerProgressModal.vue"
import RecorderFieldReview from "./components/recorder-field-review.vue"
import WorkflowWorkspace from "./components/workflow-workspace.vue"
import { useAimdRecordValidation } from "./composables/useAimdRecordValidation"

import { useAssignerManagement } from "./composables/useAssignerManagement"
import { getAssignerProgress } from "./composables/useAssignerProgress"
import { useFieldEventBus } from "./composables/useFieldEventBus"
import { useFieldManagement } from "./composables/useFieldManagement"
import { useFieldParser } from "./composables/useFieldParser"
import { useFieldState } from "./composables/useFieldState"
import { useRecorderConversation } from "./composables/useRecorderConversation"
import { useTableManagement } from "./composables/useTableManagement"
import { RecordCalculationError } from "./helpers/recordCalculationError"
import ProtocolAddRecordFormItem, { type IProps as IFormItemProps } from "./protocol-add-record-form-item.vue"

defineOptions({ name: "ProtocolAddRecordForm" })

const props = withDefaults(defineProps<IProps>(), {
  protocol: null,
  defaultSpiltSize: 0.35,
  collapsed: false,
})
const emit = defineEmits<Emits>()
interface IProps {
  protocol?: ProtocolModels.ProtocolInfo | null
  protocolId: string
  recorderVersion?: string
  simulatedFields?: string[]
  recorderRecordId?: string
  recordRevision?: number
  defaultSpiltSize?: number
  readonly?: boolean
  recordData?: Partial<IRecordData>
  savedRecordData?: ProtocolModels.RecordInfo["data"]
  collapsed?: boolean
}

const aira = useWorkspaceAira()!
const authStore = useAuthStore()
const instanceStore = useInstanceStore()

// Assigner progress modal
const { state: assignerProgressState, hide: hideAssignerProgress, toggleDetailMode } = getAssignerProgress()
const assignerProgressModalState = computed(() => assignerProgressState as any)
function handleAssignerProgressClose() {
  hideAssignerProgress()
}
function handleToggleDetail() {
  toggleDetailMode()
}

interface Emits {
  (e: "setSimulated", field: string, value: boolean): void
  (e: "quizChange", field: string, value: unknown): void
  (e: "reviewPending", active: boolean): void
  (e: "update:field", payload: { scope: IRecordDataKey, prop: string, value: any, info?: any }): void
  (e: "update:splitSize", payload: string | number): void
  (e: "update:collapsed", payload: boolean): void
  (e: "update:type", payload: { scope: IRecordDataKey, prop: string, type: string }): void
}

// const { bool: isCollapsed, setTrue: collapse, setFalse: expand, toggle } = useBoolean(false)
const isCollapsed = useVModel(props, "collapsed")
const message = useClosableMessage()
const { locale } = useI18n()
const reportPresentation = useRecordReportPresentation()
const recordingFieldDisplay = useRecordingFieldDisplay()

const { airalogyId } = useProtocolInfoStore()!
const { currentRecorderRecordContext } = useChatProvider()

const resourceLabId = computed(() => String(props.protocol?.lab?.id || props.protocol?.lab_id || ""))
const resourceProjectId = computed(() => String(props.protocol?.project?.id || props.protocol?.project_id || ""))
const resourceTypeCache = shallowRef<Awaited<ReturnType<typeof fetchResourceTypes>>["items"]>([])
const inventoryReservations = ref<Record<
  string,
  Awaited<ReturnType<typeof fetchResourceAvailability>>["inventory_reservations"]
>>({})

watch([resourceLabId, resourceProjectId], () => {
  resourceTypeCache.value = []
  inventoryReservations.value = {}
})

async function ensureResourceTypes(labId: string) {
  if (resourceLabId.value === labId && resourceTypeCache.value.length > 0)
    return resourceTypeCache.value
  const { items } = await fetchResourceTypes(labId)
  if (resourceLabId.value === labId) {
    resourceTypeCache.value = items
  }
  return items
}

const resourceResolvers = computed<AimdResourceResolverMap | undefined>(() => {
  const labId = resourceLabId.value
  const projectId = resourceProjectId.value
  if (!labId)
    return undefined

  const resolver = {
    async search(query: string, context: any) {
      const response = await searchResourceRefs(labId, {
        q: query,
        resource_type: context.entity,
        role: context.role || "reference",
      })
      return response.items.map(item => ({
        ...item,
        source: "platform-resource-library",
      }))
    },
    async resolve(id: string) {
      const item = await fetchResource(labId, id)
      return {
        id: item.id,
        entity: "resource",
        source: "platform-resource-library",
        label: item.name,
        snapshot: { name: item.name, code: item.code, status: item.status },
      }
    },
    async getAvailability(resource: { id: string }, context: any) {
      const response = await fetchResourceAvailability(
        labId,
        resource.id,
        projectId || undefined,
      )
      if (resourceLabId.value === labId && resourceProjectId.value === projectId) {
        inventoryReservations.value = {
          ...inventoryReservations.value,
          [resource.id]: response.inventory_reservations || [],
        }
      }
      if (context.role === "equipment") {
        return {
          equipment_slots: response.equipment_bookings.map(item => ({
            id: item.id,
            starts_at: item.starts_at,
            ends_at: item.ends_at,
            label: item.label,
            available: item.available,
          })),
        }
      }
      const lots = new Map<string, { id: string, label: string, available: string, unit: string }>()
      let available = new Big(0)
      let unit = ""
      const containers = response.containers.map((raw: any) => {
        const balance = raw.balance || {}
        const lot = raw.lot
        if (balance.available !== undefined) {
          available = available.plus(String(balance.available))
          unit ||= String(balance.unit || raw.unit || "")
        }
        if (lot?.id && !lots.has(String(lot.id))) {
          lots.set(String(lot.id), {
            id: String(lot.id),
            label: String(lot.code || lot.id),
            available: "0",
            unit: String(balance.unit || raw.unit || ""),
          })
        }
        if (lot?.id && balance.available !== undefined) {
          const current = lots.get(String(lot.id))!
          current.available = new Big(current.available).plus(String(balance.available)).toString()
        }
        return {
          id: String(raw.id),
          lot_id: raw.lot_id ? String(raw.lot_id) : undefined,
          label: String(raw.code || raw.id),
          location: raw.location?.path,
          available: balance.available !== undefined ? String(balance.available) : undefined,
          unit: String(balance.unit || raw.unit || ""),
        }
      })
      return {
        available: available.toString(),
        unit,
        lots: [...lots.values()],
        containers,
      }
    },
    async prepareOutput(draft: any, context: any) {
      const types = await ensureResourceTypes(labId)
      const type = types.find(item =>
        item.code.toLowerCase() === String(context.entity || "").toLowerCase(),
      )
      if (!type)
        throw new Error(`Resource type ${context.entity || ""} is not registered`)
      const id = crypto.randomUUID()
      const name = String(draft.label || draft.snapshot?.name || context.fieldKey)
      const code = String(draft.snapshot?.code || `OUT-${id.slice(0, 8).toUpperCase()}`)
      const response = await prepareResourceOutput(labId, {
        id,
        resource_type_id: type.id,
        name,
        code,
        data: (draft.snapshot?.data && typeof draft.snapshot.data === "object") ? draft.snapshot.data : {},
      })
      const value = response.resource_ref as any
      return {
        id,
        value,
        payload: value.prepared_output,
      }
    },
  }
  return new Proxy({ resource: resolver } as AimdResourceResolverMap, {
    get(target, key) {
      return typeof key === "string" ? (target[key] || resolver) : undefined
    },
  })
})

// Resolve file paths for protocol assets
function resolveProtocolFile(src: string) {
  if (!props.protocolId)
    return null
  return resolveProtocolFileUtil(src, props.protocolId)
}

function resolvePreviewFile(src: string) {
  return resolveProtocolFile(src) || Promise.resolve(null)
}

const splitSize = ref(props.defaultSpiltSize)

watch(
  splitSize,
  (val) => {
    if (isCollapsed.value && val > 0) {
      isCollapsed.value = false
    }
    emit("update:splitSize", val)
  },
)

const selectedTab = ref<"form-fields" | "workflow" | undefined>(
  "form-fields",
)
const shouldScroll = ref(true) // The fields tab is the default entry point.
const stopWatch = watch(
  selectedTab,
  (val) => {
    if (val === "form-fields") {
      shouldScroll.value = true
      stopWatch()
    }
  },
)

watch(
  isCollapsed,
  (val) => {
    if (val || selectedTab.value) {
      return
    }

    selectedTab.value = "form-fields"
  },
)

function handleCollapse(e: MouseEvent) {
  const target = e.currentTarget as HTMLElement
  if (!target) {
    // NOPE
    return
  }

  const { tab } = target.dataset
  if (isCollapsed.value) {
    selectedTab.value = tab as "form-fields" | "workflow"

    splitSize.value = 0.35
    void nextTick(() => {
      isCollapsed.value = false
    })
  }
  else if (!tab || tab === selectedTab.value) {
    selectedTab.value = undefined

    splitSize.value = 0
    void nextTick(() => {
      isCollapsed.value = true
    })
  }
}

interface AimdMarkdownPreviewExpose {
  env: AimdTemplateEnv
  reload: () => Promise<void>
  rootElement: HTMLElement | null
}

const nativeRecorder = ref<InstanceType<typeof AimdRecorder>>()
const recorderRoot = ref<HTMLElement>()
const previewRef = ref<AimdMarkdownPreviewExpose>()
const lastParsedAimd = ref("")
const templateRef = ref<string>(props.protocol?.aimd || "")
const nativeEnv = computed(() => toTemplateEnv(parseAndExtract(templateRef.value)))
const { formRef } = useNaiveForm()

const role = ref<1 | 2>(1)
const couldChangeRole = ref<boolean>(false)

provide("chat-role", { role, couldChangeRole })

// Ref to store AIMD form item refs (will be assigned later after useAIMDProvide)
let aimdFormItemRefStore: Record<string, { value: any }> = {}

function restoreValidation() {
  // Restore validation for AIMD form items
  if (aimdFormItemRefStore && Object.keys(aimdFormItemRefStore).length > 0) {
    for (const key in aimdFormItemRefStore) {
      const formItem = aimdFormItemRefStore[key]?.value
      if (formItem && typeof formItem.restoreValidation === "function") {
        formItem.restoreValidation()
      }
    }
  }

  formRef.value?.restoreValidation()
}

const {
  // Models
  fieldModel,
  fieldRecordDefault,

  // Lists
  fieldPropList,
  scopeList,

  // Records
  refRecord,
  tableRecord,
  tableEmitterRecord,
  varScopeRecord,

  // Expanded Names
  expandedNamesRef,

  // Mounted State
  domMounted,
  setDomMounted,

  // Workflow Field
  workflowField,
  workflowId,

  // Restore Field Record
  restoreFieldRecord,
} = useFieldState(props, templateRef)

function recordScopeValues(scope: Record<string, { value?: unknown }> | undefined) {
  return Object.fromEntries(
    Object.entries(scope || {})
      .filter(([key]) => key !== "__SCOPE__")
      .map(([key, item]) => [key, item?.value]),
  )
}

const resourceRecord = computed(() => ({
  var: recordScopeValues((fieldModel as any).research_variable),
  step: recordScopeValues((fieldModel as any).research_step) as any,
  check: recordScopeValues((fieldModel as any).research_check) as any,
  quiz: recordScopeValues((fieldModel as any).quiz),
}))

provide(platformResourceResolverKey, {
  resolvers: resourceResolvers,
  record: resourceRecord,
  labId: resourceLabId,
  projectId: resourceProjectId,
  inventoryReservations,
})

const {
  rules: validationRules,
  isRequired: isRequiredField,
  validateRecord: validateAimdRecord,
} = useAimdRecordValidation({
  content: templateRef,
  fieldModel,
  locale,
  schema: () => props.protocol?.json_schema as Record<string, unknown> | undefined,
})

const nativeSections = { var: "research_variable", var_table: "research_variable", step: "research_step", check: "research_check", quiz: "quiz" } as const

// The execution queue asks for validation of specific dependencies. It must
// finish even on mobile, where the field drawer may never have been mounted.
async function handleAssignerValidate(...[callback, shouldApply]: Parameters<FormValidate>) {
  const errors = validateAimdRecord().issues.flatMap((issue) => {
    const [section, name] = issue.fieldKey.split(":")
    const field = `${nativeSections[section as keyof typeof nativeSections]}.${name}.value`
    return !shouldApply || shouldApply({ key: field }) ? [[{ field, message: issue.message }]] : []
  })
  const result = { warnings: undefined }
  callback?.(errors.length ? errors : undefined, result)
  return result
}

const requiredCompletion = computed(() => {
  let filled = 0
  let total = 0
  Object.entries(validationRules.value).forEach(([scope, fields]) => {
    Object.entries(fields).forEach(([field, rule]) => {
      if (!rule.value.required) {
        return
      }
      total += 1
      if (isRecorderValueFilled(_get(fieldModel, [scope, field, "value"]))) {
        filled += 1
      }
    })
  })
  return {
    filled,
    total,
    percent: total === 0 ? 100 : Math.round((filled / total) * 100),
  }
})

const RECORDER_CONTEXT_FIELD_LIMIT = 200
const RECORDER_CONTEXT_ARRAY_LIMIT = 50
const RECORDER_CONTEXT_OBJECT_KEY_LIMIT = 80
const RECORDER_CONTEXT_VALUE_DEPTH_LIMIT = 4
const RECORDER_CONTEXT_SKIP_KEYS = new Set([
  "ajv",
  "assigner",
  "assignerRecord",
  "assignedSet",
  "dependent",
  "dependentRecord",
  "disabled",
  "onUpdate",
  "raw",
  "rules",
])

function sanitizeRecorderValue(value: unknown, depth = 0): unknown {
  const rawValue = toRaw(value)

  if (rawValue === null || typeof rawValue === "undefined") {
    return rawValue
  }

  if (typeof rawValue === "string" || typeof rawValue === "number" || typeof rawValue === "boolean") {
    return rawValue
  }

  if (typeof rawValue === "bigint") {
    return rawValue.toString()
  }

  if (rawValue instanceof Big) {
    return rawValue.toString()
  }

  if (rawValue instanceof Date) {
    return rawValue.toISOString()
  }

  if (typeof File !== "undefined" && rawValue instanceof File) {
    return {
      name: rawValue.name,
      size: rawValue.size,
      type: rawValue.type,
    }
  }

  if (typeof Blob !== "undefined" && rawValue instanceof Blob) {
    return {
      size: rawValue.size,
      type: rawValue.type,
    }
  }

  if (depth >= RECORDER_CONTEXT_VALUE_DEPTH_LIMIT) {
    return "[Max depth reached]"
  }

  if (Array.isArray(rawValue)) {
    const items = rawValue
      .slice(0, RECORDER_CONTEXT_ARRAY_LIMIT)
      .map(item => sanitizeRecorderValue(item, depth + 1))

    if (rawValue.length > RECORDER_CONTEXT_ARRAY_LIMIT) {
      items.push(`[${rawValue.length - RECORDER_CONTEXT_ARRAY_LIMIT} more items omitted]`)
    }

    return items
  }

  if (typeof rawValue === "object") {
    const entries = Object.entries(rawValue as Record<string, unknown>)
      .filter(([key, item]) => !key.startsWith("_") && !RECORDER_CONTEXT_SKIP_KEYS.has(key) && typeof item !== "function")
    const result: Record<string, unknown> = {}

    entries.slice(0, RECORDER_CONTEXT_OBJECT_KEY_LIMIT).forEach(([key, item]) => {
      result[key] = sanitizeRecorderValue(item, depth + 1)
    })

    if (entries.length > RECORDER_CONTEXT_OBJECT_KEY_LIMIT) {
      result.__truncated_keys = entries.length - RECORDER_CONTEXT_OBJECT_KEY_LIMIT
    }

    return result
  }

  return String(rawValue)
}

function isRecorderValueFilled(value: unknown): boolean {
  const rawValue = toRaw(value)

  if (rawValue === null || typeof rawValue === "undefined") {
    return false
  }

  if (typeof rawValue === "string") {
    return rawValue.trim().length > 0
  }

  if (typeof rawValue === "number" || typeof rawValue === "boolean" || typeof rawValue === "bigint") {
    return true
  }

  if (rawValue instanceof Big || rawValue instanceof Date) {
    return true
  }

  if (Array.isArray(rawValue)) {
    return rawValue.some(item => isRecorderValueFilled(item))
  }

  if (typeof rawValue === "object") {
    return Object.entries(rawValue as Record<string, unknown>)
      .filter(([key, item]) => !key.startsWith("_") && !RECORDER_CONTEXT_SKIP_KEYS.has(key) && typeof item !== "function")
      .some(([, item]) => isRecorderValueFilled(item))
  }

  return true
}

function getRecorderFieldSummary() {
  const fieldSummary: CurrentRecorderRecordFieldSummary[] = []
  let filledCount = 0
  let emptyCount = 0
  let truncated = false

  scopeList.value.forEach((scopeName, scopeIndex) => {
    const propList = (fieldPropList.value[scopeIndex] || []) as Array<string | [string, string[]]>

    propList.forEach((prop) => {
      const propKey = Array.isArray(prop) ? prop[0] : prop
      if (!propKey || propKey === "__SCOPE__") {
        return
      }

      const item = _get(fieldModel, [scopeName, propKey]) || _get(fieldRecordDefault.value, ["field", scopeName, propKey])
      if (!item) {
        return
      }

      const value = _get(item, "value")
      const filled = isRecorderValueFilled(value)
      if (filled) {
        filledCount += 1
      }
      else {
        emptyCount += 1
      }

      if (fieldSummary.length >= RECORDER_CONTEXT_FIELD_LIMIT) {
        truncated = true
        return
      }

      fieldSummary.push({
        scope: scopeName,
        field_id: propKey,
        title: _get(item, "title") || _get(item, "label") || propKey,
        type: _get(item, "type"),
        filled,
        ...(filled ? { value: sanitizeRecorderValue(value) } : {}),
      })
    })
  })

  return {
    emptyCount,
    fieldSummary,
    filledCount,
    truncated,
  }
}

function syncCurrentRecorderRecordContext() {
  const { emptyCount, fieldSummary, filledCount, truncated } = getRecorderFieldSummary()
  const recordData = sanitizeRecorderValue(props.recordData || {}) as Record<string, unknown>
  const enabled = fieldSummary.length > 0 || isRecorderValueFilled(recordData)

  currentRecorderRecordContext.value = enabled
    ? {
        enabled: true,
        title: props.protocol?.name || props.protocol?.uid || "Current recorder record",
        protocol_id: props.protocolId,
        protocol_uid: props.protocol?.uid,
        protocol_name: props.protocol?.name,
        protocol_version: props.recorderVersion,
        record_id: props.recorderRecordId,
        record_revision: props.recordRevision,
        readonly: Boolean(props.readonly),
        filled_count: filledCount,
        empty_count: emptyCount,
        field_summary: fieldSummary,
        record_data: recordData,
        truncated,
      }
    : { enabled: false }
}

watch(
  [fieldModel, fieldRecordDefault, fieldPropList, scopeList, () => props.protocolId, () => props.protocol?.uid, () => props.protocol?.name, () => props.recordData, () => props.readonly, () => props.recorderVersion, () => props.recorderRecordId, () => props.recordRevision],
  syncCurrentRecorderRecordContext,
  { deep: true, immediate: true },
)

onBeforeUnmount(() => {
  currentRecorderRecordContext.value = { enabled: false }
})

provide("protocol-workflow", { workflowId })

// Platform-specific scopes still use their existing viewers.
const aimdPanelScopes = new Set(["research_variable", "research_step", "research_check", "var_table", "quiz"])
const legacyPanelGroups = computed(() => scopeList.value
  .map((scopeName, idx) => ({ scopeName, idx }))
  .filter(({ scopeName, idx }) => !aimdPanelScopes.has(scopeName) && fieldPropList.value[idx]?.length))
const hasWorkflowScope = computed(() => scopeList.value.includes("research_workflow"))

function openWorkflowWorkspace() {
  selectedTab.value = "workflow"
  if (isCollapsed.value) {
    splitSize.value = props.defaultSpiltSize
    isCollapsed.value = false
  }
}

provide("protocol-workflow-workspace", {
  open: openWorkflowWorkspace,
})

// Create a ref to store the updateField function to resolve circular dependency
const updateFieldRef = ref<((fieldModel: any, payload: any) => Promise<void>) | null>(null)

// Create a wrapper function that calls updateField when available
async function updateFieldWrapper(fieldModel: any, payload: any) {
  if (updateFieldRef.value) {
    await updateFieldRef.value(fieldModel, payload)
  }
}

function mergeDependents(
  ...lists: Array<Array<{ name: string, scope: IRecordDataKey }> | undefined>
): Array<{ name: string, scope: IRecordDataKey }> | undefined {
  const merged = lists
    .flatMap(list => list || [])
    .filter((item): item is { name: string, scope: IRecordDataKey } => Boolean(item?.name && item?.scope))

  if (merged.length === 0) {
    return undefined
  }

  const seen = new Set<string>()
  return merged.filter((item) => {
    const key = `${item.scope}.${item.name}`
    if (seen.has(key)) {
      return false
    }
    seen.add(key)
    return true
  })
}

const { handleAssigner, handleDependent, assignerLoadingRecord, assignerErrorRecord, handleAssignerCancel, assignerRequestRecord } = useAssignerManagement({
  protocolContent: () => props.protocol?.aimd || "",
  protocolLocale: () => locale.value,
  protocolSchema: () => ({ ...props.protocol?.json_schema }),
  protocolId: props.protocolId,
  emit,
  varScopeRecord,
  validate: handleAssignerValidate,
  restoreValidation,
  shouldTrigger: !props.readonly,
  updateField: updateFieldWrapper,
})

function createFormItemProps(scopeName: string, prop: string | [string, string[]]) {
  const propKey = Array.isArray(prop) ? prop[0] : prop
  const { readonly, protocolId } = props
  const item = _get(fieldModel, [scopeName, propKey])
  const ajv = _get(fieldRecordDefault.value, ["rules", scopeName, propKey, "ajv"])

  return {
    assignerLoadingRecord,
    assignerErrorRecord,
    assignerRequestRecord,
    protocolId,
    item,
    ajv,
    propInfo: propKey,
    scope: scopeName,
    varScopeRecord,
    tableRecord,
    readonly,
  } as unknown as IFormItemProps
}

const { updateField } = useFieldManagement({ fieldModel, emit })

// Set the updateField ref to the actual updateField function
updateFieldRef.value = updateField

// Create fieldEventBus for syncing left form changes to right AIMD preview
const localFieldEventBus = useEventBus<string>(fieldEventKey)
provide(protocolFileEventOwnerKey, true)

// The field drawer is lazy on mobile. Keep canonical file updates in this
// always-mounted form; field items only synchronize their local preview state.
localFieldEventBus.on((event, payload: IFieldChangePayload) => {
  if (!props.readonly)
    syncPreviewFileEvent(event, payload, fieldModel, handleFieldChange)
})

// Wrap handleFieldChange to emit preview-field-change event for queue-based processing
// This ensures field changes go through the debounced queue mechanism
async function handleFieldChange(payload: IFieldChangePayload) {
  // Get dependent and assigner info from fieldModel
  const { scope, prop, info } = payload
  const { group } = info || {}

  let assigner = payload.assigner
  let dependent = payload.dependent

  if (group) {
    // Table field - scope is "var_table", look under research_variable
    assigner = assigner
    || _get(fieldModel, ["research_variable", group, "assignerRecord", `${group}.${prop}`])
    || _get(fieldModel, ["research_variable", group, "assignerRecord", prop])
    dependent = mergeDependents(
      dependent,
      _get(fieldModel, ["research_variable", group, "dependentRecord", `${group}.${prop}`]),
      _get(fieldModel, ["research_variable", group, "dependentRecord", prop]),
      _get(fieldModel, ["research_variable", group, "dependent"]),
    )
  }
  else {
    // Regular field
    assigner = assigner || _get(fieldModel, [scope, prop, "assigner"])
    dependent = mergeDependents(
      dependent,
      _get(fieldModel, [scope, prop, "dependent"]),
    )
  }

  // Emit preview-field-change event to go through the queue mechanism
  localFieldEventBus.emit("preview-field-change", {
    ...payload,
    assigner,
    dependent,
  })

  // Also emit form-field-change event to sync left form changes to right AIMD preview
  localFieldEventBus.emit("form-field-change", payload)
}

const { setupFieldEventHandlers, hasPendingAssignments, applyLocalFieldChange } = useFieldEventBus(
  fieldModel,
  expandedNamesRef,
  handleAssigner,
  handleDependent,
  handleAssignerCancel,
  updateField,
  emit,
  varScopeRecord,
  props.protocol?.assigners,
)

const route = useRoute()
const editorPreviewRoute = computed(() => {
  const { labUid, projectUid, protocolUid } = route.params
  if (!labUid || !projectUid || !protocolUid || !props.recorderVersion)
    return undefined
  return { name: "protocol-editor", params: { labUid, projectUid, protocolUid, protocolVersion: props.recorderVersion } } as const
})

const { receipt, showPreviewLink, pending, edits, accept, dismiss, undo, busy, markInput, reset: resetReview } = useRecorderConversation({
  scope: () => JSON.stringify([props.protocolId, props.recorderVersion, props.recorderRecordId, props.readonly]),
  version: () => props.recorderVersion,
  recordId: () => props.recorderRecordId,
  editable: () => !props.readonly && instanceStore.aiEnabled,
  fields: () => Object.fromEntries(Object.entries(fieldModel.research_variable || {}).filter(([key]) => key !== "__SCOPE__")) as Record<string, { value?: unknown, assigner?: unknown }>,
  isSimulated: prop => Boolean(props.simulatedFields?.includes(prop)),
  setSimulated: (prop, value) => emit("setSimulated", prop, value),
  write: async (prop, value) => {
    const item = _get(fieldModel, ["research_variable", prop])
    let inputValue = value
    if (typeof value === "number" && ["number", "float", "integer"].includes(item.type))
      inputValue = { type: item.type, displayedValue: String(value), value }
    if (typeof value === "string" && ["datetime", "date", "time"].includes(item.type))
      inputValue = { value, formattedValue: value.replace("T", " ").replace(/Z$/, "") }
    await applyLocalFieldChange({ ...item, scope: "research_variable", prop, value: inputValue })
  },
})
watch(() => pending.value.size > 0 || busy.value, value => emit("reviewPending", value), { flush: "sync", immediate: true })
onScopeDispose(() => emit("reviewPending", false))

const previewValue = computed(() => props.readonly ? undefined : fieldModel as any)
const readonlyRecordData = computed(() => {
  if (!props.readonly)
    return undefined

  const data = (props.savedRecordData ?? props.recordData ?? {}) as Record<string, unknown>
  return {
    var: data.var ?? data.research_variable ?? {},
    step: data.step ?? data.research_step ?? {},
    check: data.check ?? data.research_check ?? {},
    quiz: data.quiz ?? {},
    var_table: data.var_table ?? {},
  }
})

const savedPanelData = computed(() => readonlyRecordData.value as Partial<AimdProtocolRecordData> | undefined)

const { handleTableRowUpdate } = useTableManagement()

const { handleParseField } = useFieldParser(
  fieldModel,
  props.protocol,
  scopeList,
  fieldPropList,
  refRecord,
  tableRecord as any,
  tableEmitterRecord,
)

// function handleMedia(sourceList: HTMLSourceElement[]) {
//   if (!props.protocol || !props.protocol.id) {
//     return
//   }

//   sourceList.forEach(async (source) => {
//     const src = source.getAttribute("src")
//     if (!src) {
//       return
//     }

//     try {
//       const res = await getStaticResearchAssets(props.protocol!.id, src)
//       if (res && res.data) {
//         const parent = source.parentElement

//         if (parent) {
//           source.src = res.data.url
//           // eslint-disable-next-line no-self-assign
//           parent.outerHTML = parent.outerHTML
//         }
//       }
//     }
//     catch (e) {
//       message.error((e as Error).message)
//     }
//   })
// }

// Initialize event handlers
setupFieldEventHandlers()

// Update template refs for table row updates
function handleTableRowActions(type: "add-row" | "remove-row", payload: any) {
  handleTableRowUpdate(type, payload, tableEmitterRecord, fieldModel)
}

async function wrappedValidate() {
  // Expand all collapsed sections to show validation errors
  expandedNamesRef.value = [...scopeList.value]
  await nextTick()

  if (hasPendingAssignments() || Object.values(assignerLoadingRecord.value).some(Boolean)) {
    throw new RecordCalculationError($t("page.protocol.calculationPending"))
  }
  const failedAssignment = Object.entries(assignerErrorRecord.value).find(([, error]) => Boolean(error))
  if (failedAssignment) {
    await focusFirstInvalidField(failedAssignment[0])
    throw new RecordCalculationError($t("page.protocol.calculationFailed"), failedAssignment[0])
  }

  const result = await nativeRecorder.value?.validate() ?? validateAimdRecord()
  if (!result.valid) {
    throw result.issues.map(issue => ({
      loc: [issue.fieldKey.split(":")[1] || issue.section],
      msg: issue.message,
      fieldKey: issue.fieldKey,
    }))
  }
}

async function focusFirstInvalidField(field?: string) {
  if (!props.readonly && nativeRecorder.value) {
    const key = field && (field.includes(":") ? field : `var:${field}`)
    if (key && await focusNativeField(key))
      return
    if (!key && nativeRecorder.value.focusFirstInvalidField())
      return
  }
  selectedTab.value = "form-fields"
  expandedNamesRef.value = [...scopeList.value]
  if (isCollapsed.value) {
    splitSize.value = props.defaultSpiltSize
    isCollapsed.value = false
  }
  await nextTick()
  const fieldTarget = field ? document.getElementById(`form-research_variable-${field}`) : null
  const target = fieldTarget || document.querySelector<HTMLElement>(
    ".record-fields-form .n-form-item--error, .record-fields-form [aria-invalid='true']",
  ) || document.querySelector<HTMLElement>(
    ".record-fields-form input, .record-fields-form textarea, .record-fields-form button, .record-fields-form [tabindex]",
  )
  target?.scrollIntoView({ behavior: "smooth", block: "center" })
  const focusTarget = target?.matches("input, textarea, button, [tabindex]")
    ? target
    : target?.querySelector<HTMLElement>("input, textarea, button, [tabindex]")
  focusTarget?.focus({ preventScroll: true })
}

const bubbleMenuEventBus = useEventBus<BubbleMenuEventName, BubbleMenuEventPayload>(bubbleMenuEventKey)

type ChatField = Pick<AddToChatPayload, "prop" | "scope" | "type">
function openRecorderChat(eventType: "sendToChat" | "addToChat", value: string | ChatField, trigger?: HTMLElement) {
  aira.open(trigger)

  void nextTick(() => {
    if (typeof value === "string") {
      bubbleMenuEventBus.emit(eventType, value)
    }
    else {
      const { prop, scope, type } = value
      const modelValue = _get(fieldModel, [scope, prop, "value"])
      let formattedValue = modelValue
      if (modelValue && typeof modelValue === "object") {
        if (modelValue.airalogy_file_id) {
          formattedValue = `"${modelValue.airalogy_file_id}"`
        }
        else if (modelValue.value != null) {
          formattedValue = modelValue.value
        }
        else {
          formattedValue = JSON.stringify(modelValue, null, 0)
        }
      }
      else if (typeof modelValue === "string") {
        formattedValue = `"${modelValue}"`
      }

      const formattedScope = scopeKeyRecord[scope as ScopeFieldKey] as IRecordDataKey
      const id = `${formattedScope}.${prop}`

      bubbleMenuEventBus.emit(eventType, {
        prop,
        scope: formattedScope,
        value: formattedValue,
        type,
        mentionAttrs: {
          id,
          label: fieldRecordDefault.value?.field[scope as ScopeFieldKey]?.[prop]?.title?.trim() || id,
          query: id,
          // TODO: resolve context items, items may change after the mention is inserted
          renderInlineAs: `{{${formattedScope}|${prop}, value=${formattedValue ?? ""}, type=${type}}}`,
          itemType: "getFieldValue",
        },
      })
    }
  })
}

bubbleMenuEventBus.on((event, payload) => {
  if (instanceStore.aiEnabled && event === "triggerChatAction" && payload && typeof payload === "object" && "event" in payload) {
    openRecorderChat(payload.event, payload.value, document.activeElement instanceof HTMLElement ? document.activeElement : undefined)
  }
})

const contextBus = useEventBus<"request:context/getContextItems" | "response:context/getContextItems", ResolveContextItemPayload | ContextItemWithId[]>("submenu-eventbus")

contextBus.on(async (event, payload) => {
  if (event !== "request:context/getContextItems" || !payload) {
    return
  }

  const { name, query } = payload as ResolveContextItemPayload

  if (!name || !query) {
    return
  }

  const [scope, prop] = query.split(".")

  if (!scope || !prop) {
    return
  }

  const result = _get(fieldModel, [scopeNameRecord[scope] || scope, prop, "value"])

  const response: ContextItemWithId[] = [{
    content: result,
    id: {
      providerTitle: "",
      itemId: "",
    },
    description: "",
    name: "",
  }]

  contextBus.emit("response:context/getContextItems", response)
})

const isEditorBubbleActive = ref(false)
provideLocal("isEditorBubbleActive", isEditorBubbleActive)

function getTagColor(scopeName: string): TagColor {
  const { colors } = themeSettings.tokens.light
  switch (scopeName) {
    case "research_variable":
      return { color: colors["field-var-bg"], textColor: "white", borderColor: colors["field-var-bg"] } as TagColor
    case "var_table":
      return { color: colors["field-table-bg"], textColor: "white", borderColor: colors["field-table-bg"] } as TagColor
    case "research_check":
      return { color: colors["field-check-bg"], textColor: "white", borderColor: colors["field-check-bg"] } as TagColor
    case "research_step":
      return { color: colors["field-step-bg"], textColor: "white", borderColor: colors["field-step-bg"] } as TagColor
    default:
      return { color: colors["field-var-bg"], textColor: "white", borderColor: colors["field-var-bg"] } as TagColor
  }
}

/** Render aimd tokens to component */
const aimdProps = computed((): IAIMDWrapperProps => ({
  protocolId: props.protocolId,
  record: fieldRecordDefault.value,
  propList: fieldPropList.value,
  scopeList: scopeList.value,
  typed: nativeEnv.value.typed as any,
  refRecord: refRecord.value,
  tableRecord: tableRecord.value,
  varScopeRecord: varScopeRecord.value as any,
  readonly: props.readonly,
  assignerLoadingRecord: assignerLoadingRecord.value,
  assignerErrorRecord: assignerErrorRecord.value,
  assignerRequestRecord: assignerRequestRecord.value,
}))

const aimdEmit: AIMDEmits = (event, ...args) => {
  if (event === "add-row:table") {
    handleTableRowActions("add-row", ...args)
  }
  if (event === "remove-row:table") {
    handleTableRowActions("remove-row", ...args)
  }
}

const { variableList, fieldEventBus, fieldModel: componentFieldModel, restoreTableVariableRecord: restoreTableVariableRecordFn, formItemRef: aimdFormItemRef } = useAIMDProvide(aimdProps, aimdEmit)

// Assign to the store so it can be used by functions defined earlier
aimdFormItemRefStore = aimdFormItemRef

async function handlePreviewRendered() {
  const content = templateRef.value
  if (domMounted.value && lastParsedAimd.value === content) {
    return
  }

  lastParsedAimd.value = content
  setDomMounted()

  // Access template environment data directly
  if (previewRef.value) {
    const { env } = previewRef.value

    // Call the field parser with the analysis data
    handleParseField(env)

    // After parsing fields and tables, restore table variable records
    await nextTick()
    if (restoreTableVariableRecordFn) {
      restoreTableVariableRecordFn()
    }
  }
}

const hostedContent = computed(() => hostedRecorderContent(templateRef.value))
function handleNativeFields() {
  handleParseField(nativeEnv.value)
  setDomMounted()
}

function nativeValue(value: any): any {
  if (Array.isArray(value))
    return value.map(row => row && typeof row === "object" ? Object.fromEntries(Object.entries(row).map(([key, cell]) => [key, nativeValue(cell)])) : row)
  if (value && typeof value === "object" && ("displayedValue" in value || "formattedValue" in value))
    return processFieldValue(value)
  return value
}
const nativeRecord = computed<AimdProtocolRecordData>(() => ({
  var: Object.fromEntries(Object.entries(resourceRecord.value.var).map(([id, value]) => {
    const field = fieldRecordDefault.value?.field.research_variable?.[id]
    // Older Platform drafts may wrap a single attachment in an upload-list item.
    const reference = /^(?:file|image)/i.test(String(field?.type)) ? aimdFileReference(value) : undefined
    return [id, reference ?? nativeValue(value)]
  })),
  step: { ...props.recordData?.research_step, ...resourceRecord.value.step },
  check: { ...props.recordData?.research_check, ...resourceRecord.value.check },
  quiz: props.recordData?.quiz ?? {},
}))
const nativeSchema = computed(() => props.protocol?.json_schema ? { ...props.protocol.json_schema } : undefined)
const tableNames = computed(() => new Set(nativeEnv.value.tables?.map(([id]) => id)))
const drawerVariables = computed(() => Object.keys(fieldRecordDefault.value?.field.research_variable || {})
  .filter(id => id !== "__SCOPE__" && !tableNames.value.has(id) && !fieldRecordDefault.value?.field.research_variable?.[id]?.originalName))
async function focusNativeField(key: string) {
  let target: HTMLElement | null = null
  if (props.readonly) {
    const split = key.indexOf(":")
    target = previewRef.value?.rootElement?.querySelector<HTMLElement>(
      `[data-aimd-type="${CSS.escape(key.slice(0, split))}"][data-aimd-id="${CSS.escape(key.slice(split + 1))}"]`,
    ) ?? null
    if (!target)
      return false
  }
  if (window.matchMedia("(max-width: 767px)").matches)
    isCollapsed.value = true
  selectedTab.value = "form-fields"
  await nextTick()
  if (target) {
    target.setAttribute("tabindex", "-1")
    target.focus({ preventScroll: true })
    target.scrollIntoView({ block: "center" })
    return true
  }
  return nativeRecorder.value?.focusField(key) ?? false
}
const nativeMeta = computed(() => {
  const meta: Record<string, AimdFieldMeta> = {}
  for (const [id, field] of Object.entries(fieldRecordDefault.value?.field.research_variable || {})) {
    if (id === "__SCOPE__")
      continue
    const schema = fieldRecordDefault.value?.rules?.research_variable?.[id]?.ajv?.schema
    meta[`var:${id}`] = {
      title: field.title,
      description: field.description,
      disabled: field.disabled,
      assigner: field.assigner,
      ...(schema?.type === "integer" || schema?.type === "number" ? { inputType: "number" } : {}),
      ...(schema?.type === "boolean" ? { inputType: "boolean" } : {}),
      ...(schema?.format && ["date", "date-time", "time"].includes(schema.format) ? { inputType: schema.format.replace("date-time", "datetime") } : {}),
      ...(Array.isArray(schema?.enum) ? { enumOptions: schema.enum.map(value => ({ label: String(value), value })) } : {}),
    }
  }
  return meta
})
function fieldChatButton(field: string, inDrawer = false) {
  if (!authStore.isLogin || !instanceStore.aiEnabled || props.readonly)
    return null
  const label = `${$t("chat.addToChat")} · ${nativeMeta.value[`var:${field}`]?.title || field}`
  return h("button", {
    "type": "button",
    "class": "recorder-field-chat",
    "aria-label": label,
    "title": label,
    onClick(event: MouseEvent) {
      event.stopPropagation()
      const schemaType = fieldRecordDefault.value?.rules?.research_variable?.[field]?.ajv?.schema?.type
      const type: ChatField["type"] = schemaType === "integer" ? "number" : schemaType || "string"
      const compactDrawer = inDrawer && window.matchMedia("(max-width: 767px)").matches
      if (compactDrawer)
        isCollapsed.value = true
      const trigger = compactDrawer ? document.querySelector<HTMLElement>('[data-testid="record-open-fields"]') : event.currentTarget as HTMLElement
      openRecorderChat("addToChat", { prop: field, scope: "research_variable", type }, trigger ?? undefined)
    },
  }, [h(IconMessagePlus, { "aria-hidden": true })])
}

// Preserve the existing focus targets used by the record forms and Aira.
function wrapDrawerField(key: string, type: string, vnode: VNode) {
  const id = key.slice(key.indexOf(":") + 1)
  return h("div", { "id": `form-${nativeSections[type as keyof typeof nativeSections]}-${id}`, "data-recorder-field": id }, [vnode, type === "var" && fieldChatButton(id, true)])
}
const nativeState = computed(() => Object.fromEntries(Object.keys(assignerLoadingRecord.value).concat(Object.keys(assignerErrorRecord.value)).map(id =>
  [`var:${id}`, { loading: !!assignerLoadingRecord.value[id], error: assignerErrorRecord.value[id] ? String(assignerErrorRecord.value[id]) : undefined }])))
function handleNativeAssigner({ fieldKey, section }: FieldEventPayload) {
  const scope = nativeSections[section]
  const field = _get(fieldModel, [scope, fieldKey])
  if (field?.assigner)
    localFieldEventBus.emit("assigner-request", { scope, prop: fieldKey, assigner: field.assigner })
}
function fieldHint({ field }: { field: string }) {
  const suggestion = pending.value.get(field)
  const change = suggestion || edits.value.get(field)
  return change && h(RecorderFieldReview, { change, pending: !!suggestion, busy: busy.value, onAccept: accept, onDismiss: dismiss, onUndo: undo })
}
function wrapNativeField(key: string, type: string, vnode: VNode) {
  if (type !== "var")
    return vnode
  const field = key.slice(4)
  return h("span", { "data-recorder-field": field }, [vnode, fieldChatButton(field), h(fieldHint, { field })])
}

// Keep the Platform attachment card (authorized download, rename and versioned file IDs).
const hostAdapters: AimdRecorderFieldAdapters = {
  var: ({ node, messages }) => {
    const item = variableList.value.find(it => it.scope === "research_variable" && it.prop === node.id)
    if (!item || !/^(?:file(?:id.*)?|image|recordid)$/i.test(String(node.definition?.type || item.type)))
      return null
    return h(AIMDItem, {
      ...item,
      required: isRequiredField(`var:${node.id}`),
      fieldDisplay: recordingFieldDisplay.value,
      fieldTitle: nativeMeta.value[`var:${node.id}`]?.title || getAimdFieldTitle(node.definition),
      scopeLabel: messages.scope.var,
      optionalLabel: messages.common.optional,
    })
  },
}
const panelAdapters: AimdRecorderFieldAdapters = {
  var: (context) => {
    const item = variableList.value.find(it => it.scope === "research_variable" && it.prop === context.node.id)
    // Record references use the Platform picker. Model-only file declarations
    // can also lack an AIMD type, so preserve the existing schema-aware control.
    if (item && (item.type.toLowerCase() === "recordid" || (!context.node.definition?.type && /^(?:file|image)/i.test(item.type))))
      return h(AIMDItem, { ...item, fieldDisplay: "compact" })
    return null
  },
}
async function uploadNativeFile(file: File) {
  const { data, error } = await postAddAttachments(file, props.protocolId)
  if (error || !data?.airalogy_file_id)
    throw error || new Error($t("page.protocol.addRecord.uploadFailed"))
  return data.airalogy_file_id
}
async function resolveNativeFile(src: string, context: AimdFileResolveContext) {
  // The SDK can invoke this resolver for any string value. Only declared file
  // fields may use the attachment API; ordinary observations are not paths.
  if (!getAimdFileKindFromType(context.type, context.node.definition?.kwargs, context.fieldMeta))
    return null
  if (src.startsWith("airalogy.id.file.")) {
    const file = await getCachedAttachment(src)
    return file ? { name: file.filename, url: file.url } : null
  }
  // Saved file fields from older Records may contain only the attachment UUID.
  if (/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(src)) {
    const { data } = await getReferenceAssets(src, false)
    return data ? { name: data.filename, url: data.url } : null
  }
  return resolvePreviewFile(src)
}

let lastSnapshot: AimdProtocolRecordData | undefined
let droppingTable: string | undefined
function captureTableDrop(event: DragEvent) {
  const field = event.target instanceof Element ? event.target.closest<HTMLElement>("[data-aimd-recorder-field]")?.dataset.aimdRecorderField : undefined
  if (field?.startsWith("var_table:")) {
    droppingTable = field.slice("var_table:".length)
    queueMicrotask(() => {
      droppingTable = undefined
    })
  }
}
function handleNativeSnapshot(record: AimdProtocolRecordData) {
  lastSnapshot = record
  if (droppingTable)
    writeNativeTable(droppingTable)
}
function writeNativeTable(id: string) {
  const rows = lastSnapshot?.var[id]
  if (Array.isArray(rows) && !isEqual(nativeRecord.value.var[id], rows))
    void handleFieldChange({ prop: id, scope: "research_variable", value: rows })
}
function keepResourceSearchFocus(event: MouseEvent) {
  // Blurring the search box refreshes its results before the option receives its click.
  if (event.button === 0 && event.target instanceof Element && event.target.closest(".aimd-rec-entity-ref__option"))
    event.preventDefault()
}
function handleNativeField({ section, fieldKey, value, rowIndex, column }: FieldEventPayload) {
  if (props.readonly)
    return
  if (section === "var_table" && rowIndex !== undefined && column) {
    const group = fieldKey.split(":")[0]
    void handleFieldChange({ scope: "var_table", prop: column, value: value as any, info: { group, row: rowIndex } })
    return
  }
  const id = fieldKey.split(":")[0]
  const scope = nativeSections[section]
  if (section === "quiz") {
    emit("quizChange", id, value)
    return
  }
  const field = _get(fieldModel, [scope, id])
  if (section === "step" || section === "check") {
    value = lastSnapshot?.[section][id] ?? value
  }
  else if (typeof value === "number" && ["number", "float", "integer"].includes(field?.type)) {
    value = { type: field.type, value, displayedValue: String(value) }
  }
  else if (section === "var" && nativeMeta.value[`var:${id}`]?.inputType === "datetime" && typeof value === "string") {
    // datetime-local supplies minutes. JSON Schema date-time also requires seconds.
    value = value.replace(/^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2})(Z|[+-]\d{2}:\d{2})$/, "$1:00$2")
  }
  void handleFieldChange({ scope, prop: id, value: value as any })
}

watchEffect(() => {
  const { userInfo } = authStore
  const record = fieldRecordDefault.value
  const propList = fieldPropList.value
  if (!record || !record.field || !userInfo || !Array.isArray(propList) || propList.length === 0) {
    return []
  }
  const { field } = record

  scopeList.value.forEach((scopeName, idx) => {
    const scopePropList = propList[idx] as string[]

    scopePropList.forEach((prop) => {
      const item = field[scopeName]?.[prop]
      if (!item) {
        return
      }

      let val: any = _cloneDeepWith(toRaw(item.value), (objVal) => {
        if (objVal instanceof Big) {
          return new Big(objVal)
        }

        return undefined
      })

      if (!val && (scopeName === "research_check" || scopeName === "research_step")) {
        val = {
          annotation: "",
          // checked: scopeName === "research_step" && !step_check ? null : false,
          // checked: item.raw?.check ? false : null,
          checked: null,
        }
      }
      if (componentFieldModel[scopeName]) {
        componentFieldModel[scopeName][prop] = { value: val }
      }
      else {
        componentFieldModel[scopeName] = { [prop]: { value: val } }
      }
    })
  })

  return () => { }
})

// Watch for changes in external fieldModel and sync to componentFieldModel
// This ensures left panel changes are reflected in the right AIMD preview
watch(
  fieldModel,
  (newFieldModel) => {
    if (!newFieldModel)
      return

    scopeList.value.forEach((scopeName) => {
      const scopeData = newFieldModel[scopeName]
      if (!scopeData)
        return

      Object.entries(scopeData).forEach(([prop, propData]) => {
        if (!propData || typeof propData !== "object")
          return

        const val = (propData as any).value
        if (componentFieldModel[scopeName]?.[prop]) {
          // Only update if value actually changed to avoid infinite loops
          const currentVal = componentFieldModel[scopeName][prop].value
          if (JSON.stringify(currentVal) !== JSON.stringify(val)) {
            // Replace the entire object to trigger reactivity
            componentFieldModel[scopeName][prop] = { value: val }
          }
        }
        else if (componentFieldModel[scopeName]) {
          // Create the prop if it doesn't exist
          componentFieldModel[scopeName][prop] = { value: val }
        }
      })
    })
  },
  { deep: true },
)

watch(
  fieldRecordDefault,
  (record) => {
    if (!record || props.readonly) {
      return
    }

    const propList = fieldPropList.value

    const { field } = record

    const batchList: { scope: IRecordDataKey, prop: string, value: any, assigner: any, dependent: any, info: any }[] = []

    scopeList.value.forEach((scopeName, idx) => {
      const scopePropList = propList[idx]
      scopePropList.forEach((prop) => {
        if (Array.isArray(prop)) {
          return
        }

        const item = field[scopeName]?.[prop]
        if (!item) {
          return
        }

        const { value: val, type, scope } = item
        const assigner = (item as any).assigner
        const dependent = (item as any).dependent
        const info = (item as any).info

        // Check if field has an assigner
        const hasAssigner = !!assigner
        const hasAutoAssigner = assigner && assigner.mode !== "manual"

        if (typeof val !== "undefined" && val !== null) {
          if (!(
            ((type === "float" || type === "integer" || type === "number")
              && (val.value === null || typeof val.value === "undefined"))
              || (Array.isArray(val) && val.length === 0)
          )) {
            batchList.push({
              scope: scope as IRecordDataKey,
              prop,
              value: val,
              assigner,
              dependent,
              info,
            })
          }
        }
        // Also add fields with auto assigners even if they don't have values yet
        // This ensures assigners are triggered during initial load
        else if (hasAutoAssigner) {
          batchList.push({
            scope: scope as IRecordDataKey,
            prop,
            value: undefined,
            assigner,
            dependent,
            info,
          })
        }
        // Also add manual assigner fields (for dependency checking, not execution)
        else if (hasAssigner && assigner.mode === "manual") {
          batchList.push({
            scope: scope as IRecordDataKey,
            prop,
            value: undefined,
            assigner,
            dependent,
            info,
          })
        }
      })
    })

    void nextTick(() => {
      const batchId = nanoid()
      fieldEventBus.emit("preview-field-change-batch", {
        batchId,
        list: batchList,
      })
    })
  },
  { immediate: true },
)

// watch(componentFieldModel, (val) => {
//   if (previewRef.value?.reload) {
//     previewRef.value.reload(false)
//   }
// } )

const reportScope = computed(() => props.readonly && props.recorderRecordId && props.recordRevision
  ? JSON.stringify(["record", props.protocolId, props.recorderRecordId, props.recordRevision, props.recorderVersion])
  : undefined)
const assistantChat = ref<InstanceType<typeof ChatComponent>>()
const analysisRequested = ref(false)
function assistWithFields(trigger: HTMLElement) {
  if (props.readonly || !aira.context.value)
    return
  aira.open(trigger)
}
function analyzeReport(trigger: HTMLElement) {
  if (!props.readonly || !props.recorderRecordId || !props.recordRevision || !aira.context.value)
    return
  aira.open(trigger)
  analysisRequested.value = true
}
watch([assistantChat, analysisRequested], ([chat, requested]) => {
  if (chat && requested && aira.visible.value) {
    analysisRequested.value = false
    syncCurrentRecorderRecordContext()
    if (!chat.analyzeRecord($t("page.airaActions.analysisPrompt")))
      message.info($t("page.airaActions.reportBusy"))
  }
}, { flush: "post" })

defineExpose({
  analyzeReport,
  assistWithFields,
  validate: wrappedValidate,
  requiredCompletion,
  focusFirstInvalidField,
  toggle: () => {
    if (isCollapsed.value) {
      splitSize.value = 0.35
    }
    else {
      splitSize.value = 0
    }
    isCollapsed.value = !isCollapsed.value
  },
  previewRef,
  fieldRecord: fieldRecordDefault,
  fieldModel,
  restoreFieldRecord: async (recordData?: Partial<IRecordData>) => {
    resetReview()
    if (restoreFieldRecord) {
      restoreFieldRecord(recordData)
    }

    // restoreTableVariableRecord runs after the shared preview reports a completed render.
    // after the markdown preview is mounted and fields are parsed
  },
  restoreTableVariableRecord: restoreTableVariableRecordFn,
})
</script>

<style lang="sass">
@mixin rings($duration, $delay)
  opacity: 0
  display: flex
  flex-direction: row
  justify-content: center
  align-items: center
  position: absolute
  top: -2px
  left: -2px
  right: -2px
  bottom: -2px
  content: ''
  border: 4px solid rgba(65, 129, 253, 0.6)
  border-radius: 8px
  animation-name: ripple
  animation-duration: $duration
  animation-delay: $delay
  animation-direction: alternate
  animation-iteration-count: infinite
  animation-timing-function: cubic-bezier(.65, 0, .34, 1)
  box-sizing: border-box

.aimd-field--focus
  position: relative
  .n-input__border
    border-width: 2px
    border-color: rgba(65, 129, 253, 0.6)

  &::before
    @include rings(1s, 0s)

@keyframes ripple
  from
    opacity: 1
    transform: scale3d(1, 1 , 1)

  to
    opacity: 0
    transform: scale3d(1, 1.05, 1)
</style>

<style scoped lang="sass">
@use "@styles/sass/list.sass" as *

.record-inline-content
  padding-inline: 24px

@media (max-width: 767px)
  .record-inline-content
    padding-inline: 0

:deep(.n-form-item-blank)
  flex-direction: column
:deep(.n-input-wrapper)
  width: 100%

:deep(.n-form-item-label__text)
  flex: 1
:deep(.n-collapse-item__header-main)
  overflow: hidden
:deep(.n-form-item-label__text)
  overflow: hidden
</style>

<style scoped>
:deep(.recorder-field-chat) {
  display: inline-grid;
  place-items: center;
  min-width: 1.75rem;
  min-height: 1.75rem;
  margin-inline-start: .25rem;
  vertical-align: middle;
  color: var(--primary-color, #1764ae);
  border-radius: .25rem;
  cursor: pointer;
}
@media (hover: hover) and (pointer: fine) {
  :deep([data-recorder-field]:not(:hover, :focus-within) > .recorder-field-chat) {
    opacity: 0;
  }
}
:deep([data-recorder-field]:has(.recorder-field-undo)) {
  outline: 2px solid var(--primary-color, #0084e2);
  outline-offset: 2px;
}
</style>
