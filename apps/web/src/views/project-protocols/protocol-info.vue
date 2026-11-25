<template>
  <split-layout :chat-props="{ source: 'protocol', airalogyId, role: ChatType.NORMAL }">
    <n-tabs
      type="segment"
      animated
      placement="top"
      :theme-overrides="{ tabPaddingVerticalMediumLine: '8px 0 20px 5px' }"
      class="protocol-content h-fit min-h-[calc(100vh-18rem)] p-4"
    >
      <n-tab-pane name="research_markdown" tab="Markdown">
        <report-template v-if="protocolInfo" :item="protocolInfo" />
      </n-tab-pane>
      <n-tab-pane name="fields" :tab="$t('common.fields')">
        <protocol-fields v-if="protocolInfo" :item="protocolInfo" />
      </n-tab-pane>
      <n-tab-pane name="ratings" :tab="$t('page.protocol.rating.title')">
        <protocol-rating-panel v-if="protocolInfo" :protocol-id="String(protocolInfo.id)" :version="protocolInfo.metadata?.version || protocolInfo.latest_version" />
      </n-tab-pane>
      <n-tab-pane name="history" :tab="$t('common.history')">
        <protocol-history v-if="protocolInfo" :item="protocolInfo" />
      </n-tab-pane>
      <n-tab-pane name="assigner_graph" :tab="$t('common.assigner')" :disabled="!(protocolInfo as any)?.assigner_graph">
        <assigner-graph />
      </n-tab-pane>
    </n-tabs>
  </split-layout>
</template>

<script setup lang="ts">
import ProtocolRatingPanel from "@/components/protocol/protocol-rating-panel.vue"
import { ChatType } from "@airalogy/shared/enum"
import { useProtocolInfoStore } from "./hooks/useProtocolInfoStore"
import SplitLayout from "./layout/split-layout.vue"
import AssignerGraph from "./modules/protocol/assigner-graph.vue"
import ProtocolFields from "./modules/protocol/protocol-fields.vue"
import ProtocolHistory from "./modules/protocol/protocol-history.vue"
import ReportTemplate from "./modules/protocol/report-template.vue"

defineOptions({ name: "ProtocolProtocols" })

const { protocolInfo, airalogyId } = useProtocolInfoStore()!
</script>

<style scoped lang="sass">
:deep(.n-tabs-nav-scroll-wrapper)
  &:before, &:after
    content: none
:deep(.n-tabs-tab.n-tabs-tab--active)
  background: transparent!important
  color: #333333
</style>
