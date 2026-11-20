import type { CustomRoute, ProjectsNameKey } from "#/page-route"

export const projectsRoute: CustomRoute<ProjectsNameKey> = {
  meta: { title: "Projects", i18nKey: "breadcrumb.projects", breadcrumbI18nKey: "breadcrumb.projects" },
  name: "projects",
  path: "/projects",
  redirect: "/projects/my",
  component: () => import("@/views/projects/layout.vue"),
  children: [
    {
      meta: {
        title: "Projects",
        i18nKey: "page.project.tab.my",
        breadcrumbI18nKey: "breadcrumb.myProjects",
      },
      path: "my",
      name: "project-dashboard",
      component: () => import("@/views/projects/dashboard.vue"),
    },
    {
      path: "research-overview",
      name: "projects-research-overview",
      meta: { title: "Research overview", i18nKey: "page.orgResearch.title", allowGuest: false },
      component: () => import("@/views/labs/research-overview.vue"),
    },
    {
      meta: {
        title: "Starred Projects",
        i18nKey: "page.project.tab.star",
        breadcrumbI18nKey: "breadcrumb.starredProjects",
      },
      path: "starred",
      name: "project-starred",
      component: () => import("@/views/projects/starred.vue"),
    },
  ],
}
