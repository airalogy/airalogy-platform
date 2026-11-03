<template>
  <n-button
    v-if="Boolean(draft)"
    size="medium"
    type="primary"
    :disabled="loading"
    :loading="loading"
    class="mr-4 px-4"
    quaternary
    @click="showModal"
  >
    {{ $t("page.protocol.draft.restoreButton") }}
  </n-button>
  <n-modal
    v-model:show="isShown"
    :title="$t('page.protocol.draft.title')"
    :show-icon="false"
    display-directive="if"
    :mask-closable="false"
    preset="dialog"
    class="draft__modal !w-80vw"
    action-class="flex-wrap justify-start items-center"
  >
    <template #action>
      <n-checkbox v-model:checked="deleteDraft">
        {{ $t("page.protocol.draft.delete") }}
      </n-checkbox>
      <n-checkbox v-model:checked="mergeDraft">
        {{ $t("page.protocol.draft.merge") }}
      </n-checkbox>

      <n-button @click="hideModal">
        {{ $t("common.cancel") }}
      </n-button>
      <n-button type="primary" @click="handleRestoreDraft">
        {{ $t("page.protocol.draft.restoreAction") }}
      </n-button>
    </template>
    <n-select
      v-if="available.length > 1" v-model:value="selectedId" class="mb-3" :aria-label="$t('page.protocol.draft.restoreButton')"
      :options="available.map(item => ({ value: item.draftId, label: new Date(item.timestamp).toLocaleString() }))"
    />
    <template v-if="Boolean(draft)">
      <div>{{ $t("page.protocol.draft.prompt") }}</div>

      <n-tabs v-model:value="draftViewTab" type="line" class="mt-4">
        <n-tab-pane name="preview" :tab="$t('page.protocol.draft.previewTab')">
          <n-collapse v-if="draft?.data" :default-expanded-names="['preview']">
            <n-collapse-item name="preview">
              <template #header>
                <span>{{ $t("page.protocol.draft.previewTitle") }}</span>
                <n-text class="ml-1" :depth="3">
                  ({{ $t("page.protocol.draft.lastModified") }}: {{ lastModified }})
                </n-text>
              </template>
              <timeline-list-item
                class="max-h-40vh overflow-y-auto"
                :protocol-id="props.protocolId"
                :item="draftPreviewItem"
                :record-data="draftPreviewRecord"
                :show-header="false"
              />
            </n-collapse-item>
          </n-collapse>
          <div v-else class="text-gray-500 italic">
            {{ $t("page.protocol.draft.noPreview") }}
          </div>
        </n-tab-pane>
        <n-tab-pane name="json" :tab="$t('page.protocol.draft.jsonTab')">
          <div v-if="draft?.data" class="draft-json max-h-40vh overflow-y-auto">
            <pre>{{ draftJson }}</pre>
          </div>
          <div v-else class="text-gray-500 italic">
            {{ $t("page.protocol.draft.noJson") }}
          </div>
        </n-tab-pane>
      </n-tabs>
    </template>
    <div v-else>
      {{ $t("page.protocol.draft.noDraft") }}
    </div>
  </n-modal>
</template>

<script setup lang="ts">
import type { ITimelineItem } from "@/views/project-protocols/types"
import type { AimdRecordDataValue } from "@airalogy/aimd-core/utils"
import type { IRecordData } from "@airalogy/shared"
import type { ProtocolModels } from "@airalogy/shared/types/models"
import type { FieldRecord } from "../../views/project-protocols/modules/protocol/helpers/parseFieldStructure"
import TimelineListItem from "@/components/common/protocol-timeline/timeline-list-item.vue"
import { useClosableMessage, useLoading, useShowModal } from "@/composables"
import { useAuthStore } from "@/store/modules/auth"
import { type DraftScope, listProtocolDrafts } from "@/utils/recordDrafts"
import { useDraftManagement } from "@/views/project-protocols/modules/protocol/composables/useDraftManagement"
import { processFieldValue } from "@/views/project-protocols/utils"
import { normalizeAimdRecordDataValue } from "@airalogy/aimd-core/utils"

interface IProps {
  draftId?: string
  scope: DraftScope
  data: Partial<IRecordData>
  protocolId: string
  fieldModel: FieldRecord
  protocol: ProtocolModels.ProtocolInfo | null
  savedAt?: number
}

const props = defineProps<IProps>()

const emit = defineEmits<IEmits>()

interface IEmits {
  (e: "update:data", data: IRecordData): void
  (e: "update:field-model", fieldModel: FieldRecord): void
  (e: "restore:draft", data: Partial<IRecordData>, simulatedFields: string[], merge: boolean, removed: boolean): boolean
}

const { showModal, hideModal, isShown } = useShowModal()
const { loading } = useLoading()
const message = useClosableMessage()

const data = useVModel(props, "data", emit)

const auth = useAuthStore()
const selectedId = ref<string>()
const { prepareRestoreDraft, formatLastModified } = useDraftManagement(() => props.protocol, data, () => selectedId.value, () => props.scope)
const available = ref<ReturnType<typeof listProtocolDrafts>>([])
watch(() => [props.protocolId, props.savedAt, props.draftId, props.scope, auth.userInfo.id, isShown.value], () => {
  available.value = listProtocolDrafts(auth.userInfo.id, props.protocolId, props.scope)
  if (!isShown.value || !available.value.some(item => item.draftId === selectedId.value))
    selectedId.value = available.value.find(item => item.draftId === props.draftId)?.draftId || available.value[0]?.draftId
}, { immediate: true })
const draft = computed(() => available.value.find(item => item.draftId === selectedId.value))

const lastModified = computed(() => formatLastModified(draft.value ?? null))
const draftViewTab = ref<"preview" | "json">("preview")

const draftPreviewRecord = computed<AimdRecordDataValue>(() => {
  const data = (draft.value?.data || {}) as Record<string, unknown>

  // Compatibility boundary for drafts written by the legacy Platform form model.
  return normalizeAimdRecordDataValue({
    var: data.var ?? data.research_variable,
    var_table: data.var_table,
    step: data.step ?? data.research_step,
    check: data.check ?? data.research_check,
    quiz: data.quiz,
  })
})

const draftPreviewItem = computed(() => {
  return {
    id: "draft-preview",
    time: lastModified.value,
    field: draft.value?.data || {} as IRecordData,
  } as ITimelineItem
})

const draftJson = computed(() => {
  if (!draft.value?.data) {
    return ""
  }
  try {
    return JSON.stringify(draft.value.data, null, 2)
  }
  catch (error) {
    console.error("Failed to stringify draft data:", error)
    return ""
  }
})

const deleteDraft = ref(false)
const mergeDraft = ref(false)

function handleRestoreDraft() {
  if (!draft.value)
    return

  const draftData = prepareRestoreDraft(props.protocolId, mergeDraft.value, deleteDraft.value)

  if (!draftData) {
    message.error("No draft data found.")
    return
  }

  const fields = (draft.value.simulatedFields || []).filter(field => Object.is(
    processFieldValue(draft.value?.data.research_variable?.[field]),
    processFieldValue(draftData.research_variable?.[field]),
  ))
  emit("restore:draft", draftData, fields, mergeDraft.value, deleteDraft.value)
  if (deleteDraft.value)
    available.value = available.value.filter(item => item.draftId !== selectedId.value)

  hideModal()
}
</script>

<style lang="sass">
.draft__modal
  .n-collapse .n-collapse-item .n-collapse-item
    margin-left: 0!important

.draft-json
  background: var(--n-color)
  border: 1px solid var(--n-border-color)
  border-radius: 6px
  padding: 12px
  font-size: 12px
  line-height: 1.4
  white-space: pre-wrap
  word-break: break-word
</style>
