import { router } from "@/router"
import { useAuthStore } from "@/store/modules/auth"
import { $t } from "@airalogy/shared/locales"

let showUnauthorizedMessage = true

export function handleUnauthorized() {
  if (showUnauthorizedMessage) {
    window.$message?.error($t("resourceAccess.signInTitle"))
    showUnauthorizedMessage = false
  }

  useAuthStore().clearSession()
  const route = router.currentRoute.value
  const target = route.name === "login" ? route.fullPath : { name: "login" as const, query: { redirect: route.fullPath } }
  void router.replace(target).then(() => {
    setTimeout(() => {
      showUnauthorizedMessage = true
    }, 100)
  })
}

export function registerUnauthorizedHandler() {
  (window as any).$handleUnauthorized = handleUnauthorized
}
