import type { Router } from "vue-router"
import { captureProjectVisit } from "@/service/api/workspace"
import { useAuthStore } from "@/store/modules/auth"
import { projectVisitForRoute } from "@/utils/projectWorkspace"

export function createWorkspaceHistoryGuard(router: Router) {
  router.afterEach((to, from, failure) => {
    if (failure || !useAuthStore().isLogin)
      return
    const target = projectVisitForRoute(to)
    if (target && JSON.stringify(target) !== JSON.stringify(projectVisitForRoute(from)))
      captureProjectVisit(target)
  })
}
