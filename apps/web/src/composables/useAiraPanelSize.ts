import { createSharedComposable, useLocalStorage, useWindowSize } from "@vueuse/core"
import { computed, ref } from "vue"

export const useAiraPanelSize = createSharedComposable(() => {
  const { width: viewport } = useWindowSize()
  const saved = useLocalStorage("aira-panel-width", 0)
  const preview = ref<number | null>(null)
  const minimum = 320
  const phone = computed(() => viewport.value < 600)
  const drawer = computed(() => viewport.value < 900)
  const maximum = computed(() => Math.min(720, viewport.value - (drawer.value ? 96 : 520)))
  function clamp(width: number) {
    return Math.round(Math.min(maximum.value, Math.max(minimum, width)))
  }
  const width = computed(() => {
    if (phone.value)
      return viewport.value
    const initial = drawer.value ? 460 : Math.min(380, viewport.value * 0.28)
    return clamp(preview.value ?? (Number.isFinite(saved.value) && saved.value > 0 ? saved.value : initial))
  })
  function save(width: number) {
    saved.value = clamp(width)
    preview.value = null
  }
  function reset() {
    saved.value = 0
  }
  return { width, minimum, maximum, drawer, phone, preview, save, reset }
})
