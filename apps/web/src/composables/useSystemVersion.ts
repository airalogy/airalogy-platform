import type { SystemVersion } from "@/service/api/instance"
import { fetchSystemVersion } from "@/service/api/instance"
import { readonly, ref, shallowRef } from "vue"

const systemInfo = shallowRef<SystemVersion | null>(null)
const loading = ref(false)
const error = ref(false)
let request: Promise<void> | undefined

/** Runtime identity is shared across footer mounts for this page session. */
export function useSystemVersion() {
  function load() {
    if (!request) {
      loading.value = true
      request = (async () => {
        try {
          const result = await fetchSystemVersion()
          systemInfo.value = result.data ?? null
          error.value = !systemInfo.value?.version
        }
        catch {
          error.value = true
        }
        finally {
          loading.value = false
        }
      })()
    }
    return request
  }
  return { systemInfo: readonly(systemInfo), loading: readonly(loading), error: readonly(error), load }
}
