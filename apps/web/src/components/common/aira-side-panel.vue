<script setup lang="ts">
import { useAiraPanelSize } from "@/composables/useAiraPanelSize"
import { useId } from "vue"

const props = defineProps<{ open: boolean, label: string }>()
const emit = defineEmits<{ close: [] }>()
const { drawer: narrow, phone, width, minimum, maximum, preview, save, reset } = useAiraPanelSize()
const drawerBody = shallowRef<HTMLElement | null>(null)
const contentId = useId()
let drag: { id: number, x: number, width: number } | undefined

function startResize(event: PointerEvent) {
  if (event.button !== 0 || !event.isPrimary)
    return
  const handle = event.currentTarget as HTMLElement
  handle.setPointerCapture(event.pointerId)
  drag = { id: event.pointerId, x: event.clientX, width: width.value }
}
function moveResize(event: PointerEvent) {
  if (drag?.id === event.pointerId)
    preview.value = drag.width + drag.x - event.clientX
}
function cancelResize() {
  if (drag) {
    preview.value = null
    drag = undefined
  }
}
function finishResize(event: PointerEvent) {
  if (!drag || drag.id !== event.pointerId)
    return
  if (drag.x !== event.clientX)
    save(drag.width + drag.x - event.clientX)
  cancelResize()
}
function onCaptureLost(event: PointerEvent) {
  if (drag?.id === event.pointerId)
    cancelResize()
}
function resizeWithKeyboard(event: KeyboardEvent) {
  switch (event.key) {
    case "ArrowLeft":
      save(width.value + 16)
      break
    case "ArrowRight":
      save(width.value - 16)
      break
    case "Home":
      save(minimum)
      break
    case "End":
      save(maximum.value)
      break
    default:
      return
  }
  event.preventDefault()
}
watch([narrow, phone, () => props.open], cancelResize)
onBeforeUnmount(cancelResize)

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
    :show="open && narrow" placement="right" :width="phone ? '100%' : width"
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
      <div
        v-if="!phone" class="aira-resize-handle" role="separator" tabindex="0"
        aria-orientation="vertical" :aria-controls="contentId" :aria-label="$t('common.resizeAiraPanel')"
        :title="$t('common.resizeAiraHint')" :aria-valuemin="minimum" :aria-valuemax="maximum" :aria-valuenow="width"
        @pointerdown="startResize" @pointermove="moveResize" @pointerup="finishResize"
        @lostpointercapture="onCaptureLost" @dblclick="reset" @keydown="resizeWithKeyboard"
      />
      <div :id="contentId" class="h-full min-h-0"><slot /></div>
    </Teleport>
  </aside>
</template>

<style>
.aira-resize-handle {
  position: absolute;
  inset: 0 auto 0 0;
  z-index: 2;
  width: 10px;
  cursor: col-resize;
  touch-action: none;
  user-select: none;
}
.aira-resize-handle::after {
  content: "";
  position: absolute;
  top: 50%;
  left: 1px;
  width: 3px;
  height: 28px;
  transform: translateY(-50%);
  border-radius: 2px;
  background: var(--aira-shell-border);
}
.aira-resize-handle:is(:hover, :active, :focus-visible)::after {
  background: var(--primary-color, #2563eb);
}
@media (pointer: coarse) {
  .aira-resize-handle { width: 16px; }
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
