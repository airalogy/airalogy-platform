<template>
  <n-layout :has-sider="!embedded" class="h-full">
    <n-layout-sider
      v-if="!embedded && !appStore.isMobile"
      v-model:collapsed="appStore.siderCollapse"
      :collapsed-width="64"
      :width="280"
      collapse-mode="width"
      bordered
      show-trigger="bar"
      class="h-full"
    >
      <chat-menu />
    </n-layout-sider>
    <n-layout class="h-full">
      <div v-if="!embedded && appStore.isMobile" class="border-b border-gray-200 px-2 py-1">
        <n-button size="small" @click="showMobileHistory = true">{{ $t('chat.history') }}</n-button>
        <n-drawer v-model:show="showMobileHistory" placement="left" width="min(85%, 300px)">
          <n-drawer-content :title="$t('common.allChats')" closable :native-scrollbar="false">
            <chat-menu mobile @opened="showMobileHistory = false" />
          </n-drawer-content>
        </n-drawer>
      </div>
      <div ref="conversationViewport" class="h-full w-full overflow-x-hidden" :class="{ 'overflow-y-auto overscroll-contain': embedded }">
        <div class="mx-auto w-full max-w-3xl min-h-full flex flex-col">
          <chat-interface
            v-model:role="role"
            v-model:full-screen="appStore.fullContent"
            v-model:could-change-role="couldChangeRole"
            v-model:collapsed="isCollapsed"
            v-model:docked="docked"
            class="w-full flex-1"
            source="global"
            :chat-id="chatId"
            :show-scroll-button="arrivedState.bottom"
            :resolve-file="getCachedAttachment"
            @scroll-to-bottom="handleScrollToBottom"
          >
            <template v-if="embedded" #empty>
              <p class="aira-type-body aira-text-muted px-2">{{ $t('page.home.workspace.airaPrompt') }}</p>
            </template>
          </chat-interface>
          <context-select-dialog source="global" v-bind="contextDialog" v-on="contextDialogEventHandlers" />
        </div>
      </div>
    </n-layout>
  </n-layout>
</template>

<script setup lang="ts">
import type { ChatProviderProps } from "@airalogy/components/chat/providers/useChatProvider"
import type { DropdownOption } from "naive-ui"
import ContextSelectDialog from "@/components/chat/modules/context-select-dialog.vue"
import { useOrProvideChatConfigStore } from "@/composables"
import { LAYOUT_SCROLL_EL_ID } from "@/layouts/base-layout/utils/shared"
import { getCachedAttachment } from "@/service/api/attachments"
import { useAppStore } from "@/store/modules/app"
import { useScroll } from "@airalogy/components/chat/composables"
import { useOrProvideChatInfoStore } from "@airalogy/components/chat/composables/useChatInfoStore"
import ChatInterface from "@airalogy/components/chat/index.vue"
import { useBoolean, useScrollTrap } from "@airalogy/composables"
import { capitalCase } from "@airalogy/shared/utils"
import ChevronUpIcon from "~icons/ion/chevron-up"
import RemoveIcon from "~icons/ion/trash-bin-outline"
import LabIcon from "~icons/local/lab-outline"
import DiscussionIcon from "~icons/local/message-outline"
import ProjectIcon from "~icons/local/project-outline"
import ProtocolIcon from "~icons/local/protocol-outline"
import RecordIcon from "~icons/local/record-outline"
import { NDropdown, NIcon, NTag } from "naive-ui"
import { nanoid } from "nanoid"
import { h, nextTick } from "vue"
import ChatMenu from "./chat-menu.vue"

defineOptions({
  name: "ChatRootView",
})

const { embedded = false } = defineProps<{ embedded?: boolean }>()
const showMobileHistory = ref(false)
const conversationViewport = ref<HTMLElement | null>(null)

// Add scroll trapping to prevent parent scrolling
const { measure, scrollToBottom, scrollRef, arrivedState } = useScroll()
useScrollTrap(scrollRef)

function handleScrollToBottom(smart?: boolean) {
  scrollToBottom({ smart: smart ?? false, instant: true })
}

const contentRef = ref<HTMLElement | null>(null)
watch([() => scrollRef.value?.clientHeight, () => contentRef.value?.clientHeight], () => {
  setTimeout(() => {
    measure()
    scrollToBottom({ smart: false, instant: true })
  }, 200)
}, { flush: "post", immediate: true })

const {
  handleAddNewSession,
  chatId,
  context,
  updateContext,
  contextDialog,
  contextOptions,
  contextDialogEventHandlers,
} = useOrProvideChatInfoStore({ source: ref("global"), airalogyId: ref("") }, (event, smart) => {
  if (event === "scrollToBottom") {
    handleScrollToBottom(smart)
  }
})

const { bool: isCollapsed, setFalse: expand, toggle } = useBoolean(false)
const docked = ref(false)

const appStore = useAppStore()
const role = ref<1 | 2>(1)
const couldChangeRole = ref<boolean>(true)

const {
  enableDiscussion,
  discussionScope,
} = useOrProvideChatConfigStore()

contextDialog.value.defaultSelectedOptions = []
contextDialog.value.defaultSelectedPath = undefined
contextDialog.value.readonlyList = []
enableDiscussion.value = false
discussionScope.value = "protocol"

const discussionOptions: DropdownOption[] = [
  {
    label: "Discussions in the protocol",
    key: "protocol",
    icon: () => h(NIcon, null, { default: () => h(ProtocolIcon) }),
  },
  {
    label: "Discussions in the project",
    key: "project",
    icon: () => h(NIcon, null, { default: () => h(ProjectIcon) }),
  },
  {
    label: "Discussions in the lab",
    key: "lab",
    icon: () => h(NIcon, null, { default: () => h(LabIcon) }),
  },
  {
    label: "Remove discussion context",
    key: "remove",
    icon: () => h(NIcon, { size: 14 }, { default: () => h(RemoveIcon) }),
  },
]

function handleConfirmContexts(
  selected: (Chat.ChatContext & { version: number })[],
) {
  if (!context.value) {
    updateContext(selected)
    return
  }

  const existingContextIds = new Set(context.value.map(item => item.id))
  const updatedContext = [...context.value]
  selected.forEach((item) => {
    if (!existingContextIds.has(item.id)) {
      updatedContext.push(item)
    }
  })
  updateContext(updatedContext)
}

function handleDiscussionSelect(key: "protocol" | "project" | "lab" | "remove") {
  if (key === "remove") {
    enableDiscussion.value = false
    discussionScope.value = "protocol"
  }
  else {
    discussionScope.value = key
  }
}

function handleDiscussionContext() {
  enableDiscussion.value = !enableDiscussion.value
}

function renderDiscussionContextTag() {
  return h(
    NDropdown,
    { placement: "top-start", options: discussionOptions, onSelect: key => handleDiscussionSelect(key as "protocol" | "project" | "lab" | "remove") },
    {
      default: () => h(
        NTag,
        { class: "cursor-pointer", closable: true, onClose: handleDiscussionContext },
        {
          icon: () => h(NIcon, { size: 16 }, { default: () => h(DiscussionIcon) }),
          default: () => [
            h("span", { class: "align-middle" }, `${capitalCase(discussionScope.value)} Discussions`),
            h(NIcon, { size: 16, class: "ml-1 align-middle" }, { default: () => h(ChevronUpIcon) }),
          ],
        },
      ),
    },
  )
}

watch(() => !enableDiscussion.value, (disabled) => {
  const discussionIdx = contextDialog.value.options.findIndex(({ value }) => value === "discussion")

  if (disabled) {
    if (discussionIdx !== -1) {
      contextDialog.value.options.splice(discussionIdx, 1)
    }
    return
  }

  if (discussionIdx === -1) {
    contextDialog.value.options.push({
      label: discussionScope.value,
      value: "discussion",
      component: renderDiscussionContextTag,
    })
  }
}, { immediate: true })

watch(() => discussionScope.value, (scope) => {
  const discussionOption = contextDialog.value.options.find(({ value }) => value === "discussion")
  if (discussionOption) {
    discussionOption.label = scope
  }
})

watch(() => context.value, (val) => {
  contextDialog.value.selected = val?.map(it => it.id) || []
}, { immediate: true })

watch([enableDiscussion], () => {
  const options: ChatProviderProps["contextOptions"] = [
    {
      label: "Records",
      key: "record",
      icon: () => h(NIcon, null, { default: () => h(RecordIcon) }),
    },
    {
      label: "Protocols",
      key: "protocol",
      icon: () => h(NIcon, null, { default: () => h(ProtocolIcon) }),
    },
    {
      label: "Discussion",
      key: "discussion",
      icon: () => h(NIcon, null, { default: () => h(DiscussionIcon) }),
    },
  ]

  contextOptions.value = options
}, { immediate: true })

onMounted(async () => {
  await nextTick()
  scrollRef.value = embedded ? conversationViewport.value : document.getElementById(LAYOUT_SCROLL_EL_ID)
  if (!chatId.value) {
    handleAddNewSession(nanoid(), "global")
  }
  contextDialogEventHandlers.value.confirm = handleConfirmContexts
})
</script>

<style lang="sass" scoped>

</style>
