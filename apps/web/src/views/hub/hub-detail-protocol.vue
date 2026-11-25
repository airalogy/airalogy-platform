<template>
  <add-record-layout
    v-if="protocolInfo"
    v-model:collapsed="isCollapsed"
    v-model:split-size="splitSize"
    v-model:selected-tab="selectedTab"
    :wrapper="wrapper"
    responsive
    @update:collapsed="handleUpdateCollapsed"
  >
    <template #tabs>
      <n-tab-pane
        name="protocol-detail" class="relative" :tab="$t('common.fields')"
        display-directive="show"
        :style="{ paddingLeft: isCollapsed ? '32px' : undefined }"
      >
        <template #tab>
          <hub-protocol-menu-icon
            :selected="selectedTab === 'protocol-detail'" data-tab="protocol-detail"
            @click="handleCollapse"
          />
        </template>
        <div v-show="!isCollapsed" class="px-4 space-y-4">
          <div class="space-x-4">
            <apply-protocol-modal
              show-trigger
              :protocol-id="protocolInfo?.id"
              :button-props="{
                type: 'primary',
                class: 'min-w-25',
              }"
              :icon-props="{ size: 16 }"
              :trigger="$t('common.reuse')"
              :label="$t('common.reuse')"
              title="Reuse hub protocol"
              @modal:apply-protocol="handleProtocolApplied"
            >
              <template #icon>
                <n-icon>
                  <icon-ion-document-outline />
                </n-icon>
              </template>
            </apply-protocol-modal>
            <add-to-bookmarker-modal
              type="protocol"
              :starred="isStarred"
              :tooltip="$t('page.hub.protocolCard.addToBookmarks')"
              :icon-props="{ size: 18, color: isStarred ? '#E3B341' : '#A1A4AF' }"
              :protocol-id="protocolInfo?.id"
              @modal:add-to-bookmarker="folders => isStarred = folders.length > 0"
            >
              <template #trigger>
                <span>
                  {{ $t("common.star") }}
                  <n-tag size="tiny" class="ml-1">
                    {{ protocolInfo?.stars_count }}
                  </n-tag>
                </span>
              </template>
            </add-to-bookmarker-modal>
            <protocol-download :protocol-id="protocolInfo?.id" :version="protocolInfo?.latest_version" />
          </div>
          <!-- Categories and Tags Card -->
          <protocol-categories-card
            :discipline="protocolInfo?.disciplines || []"
            :keywords="protocolInfo?.keywords || []"
          />

          <protocol-stats-card
            v-if="protocolInfo"
            :download-count="0"
            :protocol-id="protocolInfo.id"
            :stars="protocolInfo.stars_count"
            :records="protocolInfo.records_count"
            :reuse-count="protocolInfo.forks_count"
            :version="protocolInfo.latest_version"
            :last-updated="protocolInfo.created_at"
            :license="protocolInfo.metadata?.license"
            :created-at="protocolInfo.created_at"
            records-clickable
            @records-click="handleRecordsClick"
          />
        </div>
      </n-tab-pane>
    </template>
    <template #content>
      <context-aira-panel v-if="showAssistant && protocolInfo" :key="protocolInfo.id" :title="protocolInfo.name" :version="protocolInfo.latest_version">
        <chat-component hide-collapse in-side-panel class="relative min-h-0 w-full flex-1"
                        :protocol-id="protocolInfo.id" source="protocol" enable-tool-action :airalogy-id="protocolInfo.airalogy_id"
                        :resolve-file="getCachedAttachment"  />
      </context-aira-panel>
      <n-tabs
        type="segment"
        animated
        placement="top"
        :theme-overrides="{ tabPaddingVerticalMediumLine: '8px 0 20px 5px' }"
        class="protocol-content h-fit min-h-[calc(100vh-18rem)] px-4"
      >
        <n-tab-pane name="aimd" tab="Markdown">
          <report-template v-if="protocolInfo" :item="protocolInfo" :show-actions="false" />
        </n-tab-pane>
        <n-tab-pane name="fields" :tab="$t('common.fields')">
          <protocol-fields v-if="protocolInfo" :item="protocolInfo" />
        </n-tab-pane>
        <n-tab-pane name="ratings" :tab="$t('page.protocol.rating.title')">
          <protocol-rating-panel v-if="protocolInfo" :protocol-id="String(protocolInfo.id)" :version="protocolInfo.metadata?.version || protocolInfo.latest_version" initial-scope="public" />
        </n-tab-pane>
        <n-tab-pane name="history" :tab="$t('common.history')">
          <protocol-history v-if="protocolInfo" :item="protocolInfo" />
        </n-tab-pane>
        <n-tab-pane name="assigner_graph" :tab="$t('common.assigner')" :disabled="!(protocolInfo as any)?.assigner_graph">
          <assigner-graph />
        </n-tab-pane>
      </n-tabs>
    </template>
  </add-record-layout>
</template>

<script setup lang="ts">
import type { ProtocolModels } from "@airalogy/shared/types"
import type { Component } from "vue"
import ChatComponent from "@/components/chat/index.vue"
import AddToBookmarkerModal from "@/components/common/add-to-bookmarker-modal.vue"
import ContextAiraPanel from "@/components/common/context-aira-panel.vue"
import StickyFillWrapper from "@/components/common/sticky-fill-wrapper.vue"
import AddRecordLayout from "@/components/custom/add-record-layout.vue"
import HubProtocolMenuIcon from "@/components/icon/hub-protocol-menu-icon.vue"
import ProtocolDownload from "@/components/protocol/protocol-download.vue"
import ProtocolRatingPanel from "@/components/protocol/protocol-rating-panel.vue"
import { useRouterPush } from "@/composables/useRouterPush"
import { getCachedAttachment } from "@/service/api/attachments"
import { useAuthStore } from "@/store/modules/auth"
import { useInstanceStore } from "@/store/modules/instance"
import { useOrProvideProtocolInfoStore } from "@/views/project-protocols/hooks/useProtocolInfoStore"
import AssignerGraph from "@/views/project-protocols/modules/protocol/assigner-graph.vue"
import ProtocolFields from "@/views/project-protocols/modules/protocol/protocol-fields.vue"
import ProtocolHistory from "@/views/project-protocols/modules/protocol/protocol-history.vue"
import ReportTemplate from "@/views/project-protocols/modules/protocol/report-template.vue"
import { $t } from "@airalogy/shared/locales"
import ApplyProtocolModal from "./components/apply-protocol-modal.vue"
import ProtocolCategoriesCard from "./components/protocol-categories-card.vue"
import ProtocolStatsCard from "./components/protocol-stats-card.vue"

const wrapper: Component = (props, { slots }) => h(StickyFillWrapper, { style: { height: "100%", width: "100%" }, offset: 20, ...props }, {
  ...slots,
  prefix: ({ position }: { position: string }) => h("div", { style: { height: "20px", width: "100%", display: position === "fixed" ? "block" : "none" } }),
})

const isCollapsed = ref(false)
const splitSize = ref(0.35)
const selectedTab = ref<"protocol-detail" | undefined>("protocol-detail")
const authStore = useAuthStore()
const instanceStore = useInstanceStore()
const showAssistant = computed(() => authStore.isLogin && instanceStore.aiEnabled)
const { protocolInfo } = useOrProvideProtocolInfoStore(null)
const isStarred = ref(false)

const { routerPushByKey } = useRouterPush()
function handleProtocolApplied(data: ProtocolModels.ProtocolInfo) {
  const { lab_uid: labUid, project_uid: projectUid, uid } = data
  if (labUid && projectUid && uid) {
    routerPushByKey("protocol-info", {
      params: {
        labUid,
        projectUid,
        protocolUid: uid,
      },
    })
  }
}

function handleRecordsClick() {
  if (!protocolInfo.value?.uid || !protocolInfo.value?.lab?.uid || !protocolInfo.value?.project?.uid)
    return
  routerPushByKey("protocol-records", {
    params: {
      labUid: protocolInfo.value.lab.uid,
      projectUid: protocolInfo.value.project.uid,
      protocolUid: protocolInfo.value.uid,
    },
  })
}

function handleCollapse(e: MouseEvent) {
  const target = e.currentTarget as HTMLElement
  if (!target) {
    // NOPE
    return
  }

  const { tab } = target.dataset
  if (isCollapsed.value) {
    selectedTab.value = "protocol-detail"

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

function handleUpdateCollapsed(val: boolean) {
  if (val || selectedTab.value) {
    return
  }

  selectedTab.value = "protocol-detail"
}
</script>

<style scoped lang="sass">
:deep(.protocol-content .n-tabs-nav--segment-type)
  margin: 0!important
</style>
