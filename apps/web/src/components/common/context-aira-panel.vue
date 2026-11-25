<script setup lang="ts">
import type { AddToChatPayload, BubbleMenuEventName, BubbleMenuEventPayload } from "@airalogy/composables/useBubbleMenu"
import { useWorkspaceAira } from "@/composables/useWorkspaceAira"
import { bubbleMenuEventKey } from "@airalogy/shared/constants/eventKey"
import AiraSidePanel from "./aira-side-panel.vue"

const props = defineProps<{ title?: string, version?: string, handlesFieldSelection?: boolean }>()
const emit = defineEmits<{ selectText: [] }>()
const aira = useWorkspaceAira()!
const owner = Symbol("contextual assistant")
const release = aira.bindContext(owner)
onScopeDispose(release)
const { host, visible, mounted, restoreFocus } = aira
const selections = useEventBus<BubbleMenuEventName, BubbleMenuEventPayload>(bubbleMenuEventKey)
selections.on(async (event, payload) => {
  if (props.handlesFieldSelection || aira.context.value !== owner || event !== "triggerChatAction" || !payload || typeof payload !== "object" || !("event" in payload))
    return
  const { event: action, value } = payload as { event: "sendToChat" | "addToChat", value: string | AddToChatPayload }
  emit("selectText")
  aira.open(document.activeElement instanceof HTMLElement ? document.activeElement : undefined)
  await nextTick()
  if (visible.value && aira.context.value === owner)
    selections.emit(action, value)
})
function close() {
  visible.value = false
  nextTick(restoreFocus)
}
</script>

<template>
  <Teleport v-if="mounted && aira.context.value === owner" :to="host || 'body'" :disabled="!host">
    <aira-side-panel :open="visible" label="Aira" @close="close">
      <section class="h-full min-h-0 flex flex-col bg-white" data-testid="context-aira">
        <header class="flex shrink-0 items-center gap-2 border-b border-gray-200 px-3 py-2">
          <n-icon :size="24" aria-hidden="true">
            <icon-shared-airalogy-chat />
          </n-icon>
          <strong>Aira</strong>
          <span v-if="title" class="min-w-0 truncate text-sm text-gray-600" :title="title">{{ title }}</span>
          <small v-if="version" class="shrink-0 text-gray-600">{{ version }}</small>
          <n-button class="ml-auto" size="small" quaternary circle :aria-label="$t('common.close')" data-testid="context-aira-close" @click="close">
            <template #icon>
              <n-icon><icon-tabler-x /></n-icon>
            </template>
          </n-button>
        </header>
        <slot />
      </section>
    </aira-side-panel>
  </Teleport>
</template>
