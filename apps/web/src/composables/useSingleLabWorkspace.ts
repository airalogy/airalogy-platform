import { LabRole } from "@/enum"
import { getLabInfoByUid } from "@/service/api/labs"
import { useAuthStore } from "@/store/modules/auth"
import { useInstanceStore } from "@/store/modules/instance"
import { createSharedComposable } from "@vueuse/core"

/** Share authenticated Lab identity across the shell without persisting roles. */
export const useSingleLabWorkspace = createSharedComposable(() => {
  const auth = useAuthStore()
  const instance = useInstanceStore()
  const info = shallowRef<Api.Lab.LabInfo | null>(null)
  let generation = 0
  watch(() => [instance.isSingleLab, instance.lab?.uid, auth.token, auth.userInfo.id], async () => {
    const current = ++generation
    info.value = null
    if (!instance.isSingleLab || !instance.lab || !auth.isLogin || !auth.userInfo.id)
      return
    try {
      const { data } = await getLabInfoByUid(instance.lab.uid)
      if (current === generation)
        info.value = data?.data || null
    }
    catch {
      // Core navigation remains usable if optional Lab metadata is unavailable.
    }
  }, { immediate: true })
  onScopeDispose(() => {
    generation++
  })
  const canManageLab = computed(() => {
    const role = info.value?.users?.find(user => user.id === auth.userInfo.id)?.lab_role
    return role === LabRole.OWNER || role === LabRole.MANAGER
  })
  return { info, canManageLab }
})
