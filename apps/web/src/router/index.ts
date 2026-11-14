import type { App } from "vue"
import { useInstanceStore } from "@/store/modules/instance"
import {
  createRouter,
  createWebHistory,
} from "vue-router"
import { createRouterGuard } from "./guard"
import { configureOrganizationRouting, installOrganizationRouting } from "./organization-routing"
import { createRoutes } from "./routes"

export const router = createRouter({
  history: createWebHistory("/"),
  routes: [],
})

/** Setup Vue Router */
export async function setupRouter(app: App) {
  const context = configureOrganizationRouting(useInstanceStore().status)
  const { constantRoutes, authRoutes } = createRoutes()
  for (const route of [...constantRoutes, ...authRoutes])
    router.addRoute(route)
  installOrganizationRouting(router, context)
  createRouterGuard(router)
  app.use(router)

  await router.isReady()
}
