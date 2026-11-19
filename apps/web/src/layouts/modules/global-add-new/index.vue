<template>
  <n-dropdown
    :show="isShow && !isModalOpen" trigger="manual" display-directive="show" :options="addOptions" placement="bottom-start" :render-label="renderLabel"
    @clickoutside="handleClickOutside"
    @select="handleSelect"
    @update:show="!$event && hideDropdown()"
  >
    <n-button
      secondary type="primary"
      class="h-[34px] shrink-0 rounded-2 px-3 max-[374px]:ml-0 max-[374px]:w-11 max-[374px]:px-0"
      :aria-label="$t('common.new')"
      :title="$t('common.new')"
      :aria-expanded="isShow && !isModalOpen"
      :loading="openingDocument"
      data-testid="global-create-trigger"
      @click="isShow ? hideDropdown() : showDropdown()"
      @keydown.enter.stop
    >
      <span class="hidden min-[375px]:inline">{{ $t('common.new') }}</span>
      <template #icon>
        <add-icon />
      </template>
    </n-button>
  </n-dropdown>
</template>

<script setup lang="ts">
import type { DropdownMixedOption, DropdownOption } from "naive-ui/es/dropdown/src/interface"
import { useRouterPush } from "@/composables/useRouterPush"
import { getLabInfoByUid } from "@/service/api/labs"
import { getResearchDocument } from "@/service/api/research-documents"
import { useInstanceStore } from "@/store/modules/instance"
import CreateLabModal from "@/views/labs/modules/lab/create-lab-modal.vue"
import AddProtocolModal from "@/views/project-protocols/modules/add-protocol-modal.vue"
import SelectProtocolModal from "@/views/project-protocols/modules/select-protocol-modal.vue"
import CreateProjectModal from "@/views/projects/modules/create-project-modal.vue"
import { useBoolean } from "@airalogy/composables"
import { $t } from "@airalogy/shared/locales"
import { NButton } from "naive-ui"
import { computed } from "vue"

defineOptions({ name: "GlobalAddNew" })

const { bool: isShow, setFalse: hideDropdown, setTrue: showDropdown } = useBoolean()

const { bool: isModalOpen, setFalse: closeModal, setTrue: openModal } = useBoolean()

const instanceStore = useInstanceStore()
const addOptions = computed<DropdownMixedOption[]>(() => ([
  { label: $t("common.newProtocol"), key: "new-protocol" },
  { label: $t("common.newRecord"), key: "new-record" },
  { label: $t("page.researchDocuments.new"), key: "new-document" },
  { type: "divider", key: "workspace-divider" },
  { label: $t("common.newProject"), key: "new-project" },
  ...(!instanceStore.isSingleLab ? [{ label: $t("common.newLab"), key: "new-lab" }] : []),
]))

const { routerPushByKey } = useRouterPush()
const router = useRouter()
const route = useRoute()
const openingDocument = ref(false)

type DropdownKey = "new-project" | "new-protocol" | "new-lab" | "new-record" | "new-document"

async function handleSelect(key: string) {
  if (key !== "new-document" || openingDocument.value)
    return
  hideDropdown()
  openingDocument.value = true
  const sourcePath = route.fullPath
  try {
    const { labUid, projectUid, documentId } = route.params
    if (typeof labUid === "string" && typeof projectUid === "string") {
      await router.push({ name: "project-documents", params: { labUid, projectUid }, query: { create: "document" } })
      return
    }
    let scopeQuery: { project_id?: string, lab_id?: string } = {}
    if (route.name === "research-documents") {
      if (typeof route.query.project_id === "string")
        scopeQuery = { project_id: route.query.project_id }
      else if (typeof route.query.lab_id === "string")
        scopeQuery = { lab_id: route.query.lab_id }
    }
    else if (route.name === "research-document-detail" && typeof documentId === "string") {
      const document = await getResearchDocument(documentId)
      scopeQuery = document.project_id ? { project_id: document.project_id } : document.lab_id ? { lab_id: document.lab_id } : {}
    }
    else if (typeof labUid === "string") {
      const { data, error } = await getLabInfoByUid(labUid)
      if (error || !data?.data?.id)
        throw new Error("Lab context unavailable")
      scopeQuery = { lab_id: data.data.id }
    }
    // Resolve explicit context afresh. A failed or stale lookup must never
    // silently create a document in a different audience or remembered Project.
    if (route.fullPath === sourcePath)
      await router.push({ name: "research-documents", query: { ...scopeQuery, create: "document" } })
  }
  catch {
    window.$message?.error($t("page.researchDocuments.failed"))
  }
  finally { openingDocument.value = false }
}

watch(() => route.fullPath, hideDropdown)

function handleMenuKeydown(event: KeyboardEvent) {
  // These options contain native buttons. Let Enter activate the focused
  // button instead of the dropdown's document-level selection handler.
  if (event.key === "Enter" && event.target instanceof HTMLElement && event.target.closest("button"))
    event.stopPropagation()
}

const creationButtonProps = {
  text: true,
  type: "default" as const,
  class: "!color-base-text h-full w-full justify-start",
  onKeydown: handleMenuKeydown,
}

function renderLabel(option: DropdownOption) {
  const key = option.key as DropdownKey
  const label = option.label as string

  if (key === "new-document") {
    return h(NButton, {
      ...creationButtonProps,
      onClick: (event: MouseEvent) => {
        event.stopPropagation()
        void handleSelect(key)
      },
    }, { default: () => label })
  }

  if (key === "new-record") {
    return h(SelectProtocolModal, {
      "title": $t("common.addRecord"),
      "showIcon": false,
      "buttonProps": creationButtonProps,
      "trigger": label,
      "mode": "record",
      "onModal:open": () => openModal(),
      "onModal:close": () => {
        hideDropdown()
        closeModal()
      },
      "onModal:select-protocol": async (payload) => {
        const { labUid, projectUid, protocolUid = "", protocolVersion = "" } = payload

        await routerPushByKey("add-protocol-record", {
          query: { newRecord: "true" },
          params: { labUid, projectUid, protocolUid, protocolVersion },
        })
      },
    })
  }

  if (key === "new-project") {
    return h(CreateProjectModal, {
      "showIcon": false,
      "buttonProps": creationButtonProps,
      "trigger": label,
      "onModal:open": () => openModal(),
      "onModal:close": () => {
        hideDropdown()
        closeModal()
      },
      "onModal:new-project": async (project: Api.Project.MyProjectInfo) => {
        const { lab_uid: labUid, uid: projectUid } = project

        await routerPushByKey("project-overview", {
          params: { labUid, projectUid },
        })
      },
    })
  }
  if (key === "new-lab") {
    return h(CreateLabModal, {
      "showIcon": false,
      "buttonProps": creationButtonProps,
      "trigger": label,
      "onModal:open": () => openModal(),
      "onModal:close": () => {
        hideDropdown()
        closeModal()
      },
      "onModal:new-lab": async (item: Api.Lab.LabInfo) => {
        const { uid: labUid } = item

        await routerPushByKey("lab-projects", { params: { labUid } })
      },
    })
  }
  if (key === "new-protocol") {
    return h(AddProtocolModal, {
      "showIcon": false,
      "buttonProps": creationButtonProps,
      "trigger": label,
      "onModal:open": () => openModal(),
      "onModal:close": () => {
        hideDropdown()
        closeModal()
      },
      "onModal:new-protocol": async (payload: {
        labUid: string
        id: string
        labId: string
        projectUid: string
        name: string
        uid: string
      }) => {
        const { uid, projectUid, labUid } = payload

        await routerPushByKey("protocol-info", {
          params: {
            labUid,
            protocolUid: uid,
            projectUid,
          },
        })
      },
    })
  }

  return h("span", null, { default: () => option.label })
}

function handleClickOutside() {
  if (isModalOpen.value) {
    return
  }

  hideDropdown()
}
</script>
