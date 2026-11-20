import type { InjectionKey, Ref } from "vue"
import { organizationUid } from "@/service/request/organization"
import { useAuthStore } from "@/store/modules/auth"
import { useInstanceStore } from "@/store/modules/instance"
import { createInjectionState, useMediaQuery } from "@vueuse/core"

export function useAiraNarrowScreen() {
  return useMediaQuery("(max-width: 899px)")
}

export const projectAiraKey: InjectionKey<{ available: Ref<boolean>, visible: Ref<boolean>, open: (trigger?: HTMLElement) => void }> = Symbol("projectAira")

export const [provideWorkspaceAira, useWorkspaceAira] = createInjectionState(() => {
  const project = inject(projectAiraKey, null)
  const auth = useAuthStore()
  const instance = useInstanceStore()
  const route = useRoute()
  const visible = ref(false)
  const mounted = ref(false)
  let opener: HTMLElement | undefined
  watch([() => auth.userInfo.id, organizationUid, () => instance.aiEnabled, () => route.name === "global-chat"], () => {
    visible.value = false
    mounted.value = false
    opener = undefined
  }, { flush: "sync" })
  function open(trigger?: HTMLElement) {
    if (!auth.isLogin || !instance.aiEnabled || route.name === "global-chat")
      return
    if (project?.available.value) {
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
  const projectAvailable = computed(() => project?.available.value ?? false)
  watch(projectAvailable, (available) => {
    if (available) {
      visible.value = false
      mounted.value = false
    }
  })
  const expanded = computed(() => projectAvailable.value ? project!.visible.value : visible.value)
  return { mounted, visible, expanded, projectAvailable, open, restoreFocus }
})
