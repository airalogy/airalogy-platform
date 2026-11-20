<script setup lang="ts">
import { useAiraNarrowScreen } from "@/composables/useWorkspaceAira"

const props = defineProps<{ open: boolean, label: string }>()
const emit = defineEmits<{ close: [] }>()
const narrow = useAiraNarrowScreen()
const drawerBody = shallowRef<HTMLElement | null>(null)

const rail = shallowRef<HTMLElement | null>(null)
// Some routes scroll the document and others scroll the shell. Follow the
// visible header without moving the page into a different scroll container.
watchEffect((cleanup) => {
  const element = rail.value
  if (!element || narrow.value || !props.open)
    return
  const header = element.closest(".workspace-shell")?.querySelector(":scope > header")
  const updateTop = () => {
    const bottom = Math.max(0, header?.getBoundingClientRect().bottom ?? 0)
    element.style.setProperty("--aira-rail-top", `${bottom}px`)
  }
  updateTop()
  window.addEventListener("scroll", updateTop, { capture: true, passive: true })
  const observer = new ResizeObserver(updateTop)
  if (header)
    observer.observe(header)
  cleanup(() => {
    window.removeEventListener("scroll", updateTop, true)
    observer.disconnect()
  })
}, { flush: "post" })
watch(() => props.open, async (open) => {
  if (open && !narrow.value) {
    await nextTick()
    rail.value?.focus({ preventScroll: true })
  }
}, { immediate: true })

// The rich-text editor consumes Escape even when its suggestion menu is closed.
function onEditorEscape(event: KeyboardEvent) {
  const target = event.target
  if (target instanceof HTMLElement && target.isContentEditable && target.closest('[data-chat-suggestions-open="false"]'))
    onEscape(event)
}
function onEscape(event: KeyboardEvent) {
  if (!narrow.value && props.open && !event.defaultPrevented && !event.isComposing) {
    event.stopPropagation()
    emit("close")
  }
}
</script>

<template>
  <n-drawer
    :show="open && narrow" placement="right" width="var(--aira-drawer-width, min(100%, 460px))"
    display-directive="show" :aria-label="label" :auto-focus="true"
    @update:show="shown => { if (!shown && narrow) emit('close') }"
  >
    <div ref="drawerBody" class="h-full min-h-0" />
  </n-drawer>
  <aside
    v-show="open && !narrow" ref="rail" class="aira-rail" tabindex="-1" :data-aira-docked="open && !narrow"
    :aria-label="label" @keydown.esc.capture="onEditorEscape" @keydown.esc="onEscape"
  >
    <Teleport :to="drawerBody || 'body'" :disabled="!narrow || !drawerBody">
      <slot />
    </Teleport>
  </aside>
</template>

<style>
@media (max-width: 599px) {
  :root { --aira-drawer-width: 100%; }
}
.aira-rail {
  position: fixed;
  inset-block: var(--aira-rail-top, var(--aira-header-height, 56px)) 0;
  inset-inline-end: 0;
  width: var(--aira-rail-width);
  min-width: 0;
  overflow: hidden;
  border-inline-start: 1px solid var(--aira-shell-border);
  background: var(--n-color, white);
}
</style>
