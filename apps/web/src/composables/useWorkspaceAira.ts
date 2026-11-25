import type { InjectionKey, Ref } from "vue"
import { organizationUid } from "@/service/request/organization"
import { useAuthStore } from "@/store/modules/auth"
import { useInstanceStore } from "@/store/modules/instance"
import { createInjectionState } from "@vueuse/core"
import { useAiraPanelSize } from "./useAiraPanelSize"

export function useAiraNarrowScreen() {
  return useAiraPanelSize().drawer
}

export const projectAiraKey: InjectionKey<{ available: Ref<boolean>, visible: Ref<boolean>, open: (trigger?: HTMLElement) => void }> = Symbol("projectAira")

export const [provideWorkspaceAira, useWorkspaceAira] = createInjectionState(() => {
  const project = inject(projectAiraKey, null)
  const auth = useAuthStore()
  const instance = useInstanceStore()
  const route = useRoute()
  const visible = ref(false)
  const mounted = ref(false)
  // Contextual tools stay under the page that owns the draft and its Vue providers.
  const context = shallowRef<symbol>()
  const host = shallowRef<HTMLElement | null>(null)
  let opener: HTMLElement | undefined
  function bindContext(id: symbol) {
    context.value = id
    return () => {
      // A keyed page can replace its tools during the same render. Carry the
      // open panel to the replacement, but release it on leaving the page.
      nextTick(() => {
        if (context.value === id) {
          context.value = undefined
          visible.value = false
          mounted.value = false
          opener = undefined
        }
      })
    }
  }
  watch([() => auth.userInfo.id, organizationUid, () => instance.aiEnabled, () => route.name === "global-chat"], () => {
    visible.value = false
    mounted.value = false
    opener = undefined
  }, { flush: "sync" })
  function open(trigger?: HTMLElement) {
    if (!auth.isLogin || !instance.aiEnabled || route.name === "global-chat")
      return
    if (!context.value && project?.available.value) {
      project.open(trigger)
      return
    }
    opener = trigger
    mounted.value = true
    visible.value = true
  }
  function restoreFocus() {
    if (!visible.value && opener?.isConnected)
      opener.focus({ preventScroll: true })
  }
  const projectAvailable = computed(() => !context.value && (project?.available.value ?? false))
  watch(projectAvailable, (available) => {
    if (available) {
      visible.value = false
      mounted.value = false
    }
  })
  const expanded = computed(() => projectAvailable.value ? project!.visible.value : visible.value)
  return { context, host, bindContext, mounted, visible, expanded, projectAvailable, open, restoreFocus }
})
