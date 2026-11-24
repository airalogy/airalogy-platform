import type { ResourceFailure } from "@/utils/resource-access"
import { useAuthStore } from "@/store/modules/auth"
import { resourceFailure } from "@/utils/resource-access"
import { ref, watch } from "vue"

/** Only the latest resource and account may publish a result into this view. */
export function useResourcePage<T>(
  identity: () => string,
  read: (signal: AbortSignal) => Promise<T>,
  display: (data: T | null) => void,
) {
  const auth = useAuthStore()
  const attempt = ref(0)
  const failure = ref<ResourceFailure | null>(null)
  const loading = ref(false)
  watch([identity, () => auth.token, attempt], async (_, __, onCleanup) => {
    const controller = new AbortController()
    onCleanup(() => controller.abort())
    display(null)
    failure.value = null
    loading.value = true
    try {
      const data = await read(controller.signal)
      if (!controller.signal.aborted)
        display(data)
    }
    catch (error) {
      if (!controller.signal.aborted)
        failure.value = resourceFailure(error)
    }
    finally {
      if (!controller.signal.aborted)
        loading.value = false
    }
  }, { immediate: true })
  function retry() {
    attempt.value++
  }
  return { failure, loading, retry }
}
