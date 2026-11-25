<template>
  <section v-if="Boolean(props.item?.aimd)">
    <header v-if="props.showActions" class="flex flex-wrap items-center gap-2 border-b py-4">
      <div class="mr-auto flex-center">
        <span v-if="parentProtocolInfo" class="block w-full">
          {{ $t("page.protocol.reusedFrom") }}
          <protocol-path-tooltip :protocol-info="parentProtocolInfo" />
        </span>
        <n-skeleton v-else-if="isFetchingInfo" width="min(40em, 70vw)" />
      </div>
      <aira-action-button v-if="aira?.context.value" :aria-expanded="aira.expanded.value" data-testid="protocol-ask-aira" @click="aira.open($event.currentTarget)">
        {{ $t("page.airaActions.askProtocol") }}
      </aira-action-button>
      <add-log-modal
        v-if="canOpenDataEntryForOthers"
        :protocol-id="props.item.id"
        :trigger="$t('page.protocol.addRecord.title')"
        :lab-uid="props.item.lab.uid "
        :project-uid="props.item.project.uid"
        :protocol-uid="props.item.uid"
      />
      <apply-protocol-modal
        ref="applyProtocolModalRef"
        :protocol-id="props.item.id"
        :label="$t('common.reuse')"
        :title="`Reuse ${props.item.name} to another project`"
        :show-trigger="false"
      />

      <n-dropdown v-if="canManageOwnProtocols || canManageOthersProtocols" trigger="click" :options="actionList" :render-option="renderDropdownOption">
        <n-button icon-placement="right" class="ml-3">
          {{ $t("common.more") }}
          <template #icon>
            <n-icon :component="DropdownIcon" />
          </template>
        </n-button>
      </n-dropdown>
    </header>

    <main ref="readingSurface" class="relative min-h-40 pt-5">
      <n-alert
        v-if="props.item.knowledge_sources?.length"
        class="mb-5"
        type="info"
        :title="$t('page.protocol.knowledgeSources')"
      >
        <div class="flex flex-col gap-1">
          <span v-for="source in props.item.knowledge_sources" :key="`${source.item_id}:${source.revision}:${source.protocol_version}`">
            {{ $t("page.protocol.knowledgeSource", { title: source.title, revision: source.revision, version: source.protocol_version }) }}
          </span>
        </div>
      </n-alert>
      <n-spin :show="!Boolean(props.item)">
        <!-- <edit-protocol v-if="isEdit" :protocol="protocol" :protocol-id="props.item?.id" /> -->
        <aimd-markdown-preview
          v-if="props.item?.aimd"
          :content="props.item.aimd"
          :mermaid-component="MermaidBlock"
          :resolve-url="resolveProtocolFile"
          body-class="markdown-body"
          mode="preview"
        />
        <protocol-bubble-menu v-if="aira?.context.value && readingSurface" :container-ref="readingSurface" />
        <!-- <asset-teleport
          v-if="domMounted && props.item"
          :uuid="props.item.id"
        /> -->
      </n-spin>
    </main>
  </section>
  <n-skeleton v-else class="h-full w-full flex-center flex-col" />
</template>

<script setup lang="ts">
import type { ProtocolModels } from "@airalogy/shared/types"
import type { RenderOption } from "naive-ui/es/dropdown/src/interface"
import AiraActionButton from "@/components/common/aira-action-button.vue"
import ProtocolPathTooltip from "@/components/protocol/protocol-path-tooltip.vue"
import { useBoolean, useLoading, useProjectPermissions } from "@/composables"
import { useProtocolChatHandoff } from "@/composables/useProtocolChatHandoff"

import { useRouterPush } from "@/composables/useRouterPush"
import { useWorkspaceAira } from "@/composables/useWorkspaceAira"
import { getProtocolInfo } from "@/service/api/project-protocols"
import { downloadProtocolExport, type ProtocolExportFormat } from "@/service/api/protocol-export"
import { request } from "@/service/request"
import { resolveProtocolFile as resolveProtocolFileUtil } from "@/utils/resolveProtocolFile"
import ApplyProtocolModal from "@/views/hub/components/apply-protocol-modal.vue"
import AddLogModal from "@/views/project-protocols/modules/add-log-modal.vue"
import { AimdMarkdownPreview } from "@airalogy/aimd-renderer/vue"
import MermaidBlock from "@airalogy/components/markdown-editor/modules/mermaid/mermaid-block.vue"
import ProtocolBubbleMenu from "@airalogy/components/protocol-bubble-menu.vue"
import { useClosableMessage } from "@airalogy/composables"
import { $t } from "@airalogy/shared/locales"
import EditIcon from "~icons/ion/build-outline"
import DownloadIcon from "~icons/ion/cloud-download-outline"
import UploadIcon from "~icons/ion/cloud-upload-outline"
import DropdownIcon from "~icons/local/dropdown-outline"
import ReuseIcon from "~icons/local/reuse"

import { type DropdownOption, NAlert, NIcon, NTooltip } from "naive-ui"
import { nanoid } from "nanoid"
import { useOrProvideProjectInfoStore } from "../../hooks/useProjectInfoStore"

interface IProps {
  item: ProtocolModels.ProjectProtocolInfo
  showActions?: boolean
}

const props = withDefaults(defineProps<IProps>(), {
  showActions: true,
})

const aira = useWorkspaceAira()
const readingSurface = ref<HTMLElement | null>(null)
const { projectInfo } = useOrProvideProjectInfoStore(null)
const { canOpenDataEntryForOthers, canManageOwnProtocols, canManageOthersProtocols } = useProjectPermissions(projectInfo)
const { bool: isFetchingInfo, setFalse: endFetchingInfo, setTrue: startFetchingInfo } = useBoolean()

const message = useClosableMessage()
const applyProtocolModalRef = ref<{ showModal: () => void }>()

// Resolve file paths for protocol assets
async function resolveProtocolFile(src: string): Promise<{ url: string } | null> {
  if (!props.item?.id)
    return null
  return resolveProtocolFileUtil(src, props.item.id)
}

async function handleDownload(version: string, format: ProtocolExportFormat) {
  try {
    await downloadProtocolExport(props.item.id, version, format)
  }
  catch {
    message.error($t("page.protocol.exportFailed"))
  }
}

const { routerPushByKey } = useRouterPush()
const protocolChatHandoff = useProtocolChatHandoff()

function handleApplyProtocol() {
  void routerPushByKey("protocol-info-apply-protocol", {
    params: { protocolId: String(props.item.id) },
  })
}

function handleReuseProtocol() {
  applyProtocolModalRef.value?.showModal()
}

const renderDropdownOption: RenderOption = ({ option, node }) => {
  return h(
    NTooltip,
    { keepAliveOnHover: false, style: { width: "max-content" } },
    {
      default: () => option.tooltip,
      trigger: () => [node],
    },
  )
}

const { loadingState, startTargetLoading, endTargetLoading } = useLoading(false, ["edit"])
const actionList = computed<DropdownOption[] >(() => [
  {
    label: $t("common.edit"),
    key: "edit",
    tooltip: "View this protocol in the editor. This version is read-only; click the lock icon to create an editable copy.",
    icon: () => h(NIcon, null, { default: () => h(EditIcon) }),
    loading: loadingState.value.edit,
    props: {
      onClick: async () => {
        startTargetLoading("edit")
        const { lab, project, uid, latest_version } = props.item
        if (!uid) {
          return
        }

        await routerPushByKey("protocol-editor", {
          query: protocolChatHandoff(props.item),
          params: {
            labUid: lab.uid,
            projectUid: project.uid,
            protocolUid: uid,
            protocolVersion: latest_version,
          },
        })
        endTargetLoading("edit")
      },
    },
  },
  {
    label: $t("common.download"),
    key: "download",
    icon: () => h(NIcon, null, { default: () => h(DownloadIcon) }),
    children: [
      { label: $t("page.protocol.exportAira"), key: "download-aira", props: { onClick: () => handleDownload(props.item.latest_version, "aira") } },
      { label: $t("page.protocol.exportZip"), key: "download-zip", props: { onClick: () => handleDownload(props.item.latest_version, "zip") } },
    ],
  },
  {
    label: $t("common.reupload"),
    key: "reupload",
    tooltip: "Update the current Protocol by uploading a new ZIP file (this will overwrite the existing Protocol)",
    icon: () => h(NIcon, null, { default: () => h(UploadIcon) }),
    props: {
      onClick: handleApplyProtocol,
    },
  },
  {
    label: $t("common.reuse"),
    key: "reuse",
    tooltip: "Reuse the Protocol to another project",
    icon: () => h(NIcon, { size: 12 }, { default: () => h(ReuseIcon) }),
    props: {
      onClick: handleReuseProtocol,
    },
  },
])

const parentProtocolInfo = ref<ProtocolModels.ProjectProtocolInfo | null>(null)

const requestId = ref<string | null>(null)
watchEffect(async () => {
  parentProtocolInfo.value = null

  const { parent_protocol_id } = props.item

  if (parent_protocol_id) {
    requestId.value = nanoid()
    startFetchingInfo()
    try {
      const res = await getProtocolInfo(parent_protocol_id, undefined, false, requestId.value)
      if (res && res.data) {
        parentProtocolInfo.value = res.data as ProtocolModels.ProjectProtocolInfo
      }
    }
    catch (e) {
      //
    }
    finally {
      endFetchingInfo()
    }
  }

  return () => {
    if (requestId.value) {
      request.cancelRequest(requestId.value)
      requestId.value = null
    }
  }
})
</script>
