import type { CustomRoute, HomeNameKey } from "#/page-route"
import GlobalLayout from "@/layouts/global-layout/index.vue"

export const homeRoute: CustomRoute<HomeNameKey> = {
  meta: { title: "Home", hideInBreadcrumb: true },
  path: "/",
  component: GlobalLayout,
  children: [
    {
      meta: { title: "My work", i18nKey: "page.myWork.title", requiresAuth: true },
      path: "my-work",
      name: "my-work",
      component: () => import("@/views/home/my-work.vue"),
    },
    {
      meta: { title: "Home", hideInBreadcrumb: true },
      path: "home",
      name: "home",
      component: () => import("@/views/home/index.vue"),
    },
  ],
}
