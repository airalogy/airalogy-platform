import type { CustomRoute } from "#/page-route"
import GlobalLayout from "@/layouts/global-layout/index.vue"

export const researchDocumentsRoute: CustomRoute = {
  path: "/research-documents",
  component: GlobalLayout,
  meta: { title: "Research documents", hideInMenu: true, requiresAuth: true },
  children: [
    { path: "", name: "research-documents", component: () => import("@/views/research-documents/index.vue"), meta: { title: "Research documents", hideInMenu: true, requiresAuth: true } },
    { path: ":documentId", name: "research-document-detail", component: () => import("@/views/research-documents/document-editor.vue"), meta: { title: "Research document", hideInMenu: true, requiresAuth: true } },
  ],
}
