<template>
  <n-drawer
    :show="isShown"
    class="record-report-drawer"
    :mask-closable="false"
    :theme-overrides="{ borderRadius: '1.5rem' }"
    header-class="py-7"
    height="calc(100vh - 4.375rem)"
    placement="bottom"
    @update-show="handleUpdateShow"
    @after-leave="handleTransitionEnd"
  >
    <n-drawer-content closable>
      <template #header>
        {{ props.title || $t("page.protocol.recordReport.title") }}
      </template>
      <n-spin
        :show="loading"
        class="h-full w-full"
        :content-class="`h-full w-full${props.record ? '' : ' flex-center flex-col'}`"
      >
        <template v-if="props.record && props.aimd">
          <readonly-record-preview
            show-presentation-control
            :aimd="props.aimd"
            :record="props.record"
          />
        </template>
        <template v-else-if="!loading">
          Error
        </template>
      </n-spin>
    </n-drawer-content>
  </n-drawer>
</template>

<script setup lang="ts">
import type { ProtocolModels } from "@airalogy/shared/types"
import { useLoading, useShowModal } from "@/composables/"
import ReadonlyRecordPreview from "./readonly-record-preview.vue"

defineOptions({ name: "ShowReportModal" })

const props = withDefaults(defineProps<IProps>(), {
  aimd: "",
  record: null,
})

const emits = defineEmits<IEmits>()

interface IProps {
  aimd?: string
  record: ProtocolModels.RecordInfo | null
  title?: string
}

const { loading } = useLoading()

interface IEmits {
  (e: "update:show", show: boolean): void
}
const { isShown, showModal, setModalStatus } = useShowModal()

const handleUpdateShow = (show: boolean) => setModalStatus(show)

function handleTransitionEnd() {
  emits("update:show", isShown.value)
}

watch(
  () => props.record,
  (data) => {
    if (data) {
      showModal()
    }
  },
)
</script>

<style>
.record-report-drawer {
  margin-inline: 4%;
}

@media (max-width: 640px) {
  .record-report-drawer {
    margin-inline: 0;
  }
}
</style>
