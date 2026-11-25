<script setup lang="ts">
import type { AimdRecordPresentation } from "@airalogy/aimd-renderer/vue"
import { computed, useId } from "vue"
import { useI18n } from "vue-i18n"

const props = defineProps<{ forRecording?: boolean }>()
const { t } = useI18n()
const groupName = useId()
const groupLabel = computed(() => props.forRecording ? t("page.protocol.recordReport.fieldDisplay") : t("page.protocol.recordReport.reportStyle"))
const detailedLabel = computed(() => props.forRecording ? t("page.protocol.recordReport.detailed") : t("page.protocol.recordReport.highlighted"))
const mode = defineModel<AimdRecordPresentation>({ required: true })
</script>

<template>
  <div class="report-presentation" data-testid="report-presentation">
    <span aria-hidden="true">{{ groupLabel }}</span>
    <n-radio-group v-model:value="mode" size="small" role="radiogroup" :name="groupName" :aria-label="groupLabel">
      <n-radio-button value="detailed">{{ detailedLabel }}</n-radio-button>
      <n-radio-button value="compact">{{ $t("page.protocol.recordReport.compact") }}</n-radio-button>
    </n-radio-group>
  </div>
</template>

<style scoped>
.report-presentation {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: .6rem;
  margin-block-end: .75rem;
  color: #52657b;
  font-size: .8125rem;
}
@media print {
  .report-presentation { display: none; }
}
</style>
