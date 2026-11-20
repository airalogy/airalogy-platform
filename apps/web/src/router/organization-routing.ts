import type { RouteLocationNormalized, RouteLocationRaw, Router, RouteRecordRaw } from "vue-router"

export interface OrganizationRoutingScope {
  single: boolean
  uid?: string
}

let scope: OrganizationRoutingScope = { single: false }

/** Configure from the instance contract, never from how many organizations a user can see. */
export function configureOrganizationRouting(status: {
  deployment_mode: string
  organization?: { uid: string } | null
  lab?: { uid: string } | null
  default_organization_uid?: string
}) {
  scope = {
    single: ["single_lab", "single_organization"].includes(status.deployment_mode),
    uid: status.organization?.uid ?? status.lab?.uid ?? status.default_organization_uid,
  }
  return scope
}

/** Browser paths only. API paths and published Airalogy identifiers do not change. */
export function canonicalOrganizationPath(path: string, context = scope): string {
  const match = /^\/(?:labs|orgs)(?=[/?#]|$)/.exec(path)
  if (!match)
    return path
  const suffixIndex = path.search(/[?#]/)
  const pathname = suffixIndex < 0 ? path : path.slice(0, suffixIndex)
  const suffix = suffixIndex < 0 ? "" : path.slice(suffixIndex)
  const tail = pathname.slice(match[0].length)
  if (!context.single)
    return `/orgs${tail}${suffix}`
  if (!tail || tail === "/" || tail === "/my" || tail === "/my/")
    return `/projects/my${suffix}`
  const nextSlash = tail.indexOf("/", 1)
  const encodedUid = tail.slice(1, nextSlash < 0 ? undefined : nextSlash)
  const rest = nextSlash < 0 ? "" : tail.slice(nextSlash)
  let uid: string
  try {
    uid = decodeURIComponent(encodedUid)
  }
  catch {
    return "/404/lab"
  }
  // Never reinterpret a foreign organization's link as a local project of the same name.
  if (!context.uid || uid !== context.uid)
    return "/404/lab"
  if (rest === "/projects" || rest === "/projects/")
    return `/projects/my${suffix}`
  if (rest.startsWith("/projects/"))
    return `${rest}${suffix}`
  return `/organization${rest}${suffix}`
}

export function projectBrowserPath(labUid: string, projectUid: string, context = scope) {
  return canonicalOrganizationPath(`/orgs/${encodeURIComponent(labUid)}/projects/${encodeURIComponent(projectUid)}`, context)
}

const organizationPrefix = "/orgs/:labUid([\\w-]+)"

/** One page tree, with deployment-specific public paths and stable internal route names. */
export function organizationRoutes<T extends RouteRecordRaw>(routes: T[], context = scope): T[] {
  function transform(route: T, organizationUid?: string): T {
    let path = route.path
    let scoped = organizationUid !== undefined
    if (context.single && path.startsWith(organizationPrefix)) {
      const tail = path.slice(organizationPrefix.length)
      path = tail.startsWith("/projects/") ? tail : `/organization${tail}`
      scoped = true
    }
    const meta = { ...route.meta, ...(scoped ? { organizationUid: context.uid } : {}) }
    if (context.single && route.name === "project-dashboard") {
      meta.i18nKey = "page.project.tab.list"
      meta.breadcrumbI18nKey = "page.project.tab.list"
    }
    const children = route.children
      ?.filter(child => context.single || child.name !== "projects-research-overview")
      .map(child => transform(child as T, scoped ? context.uid : undefined))
    return {
      ...route,
      path,
      meta,
      ...(context.single && route.path === organizationPrefix ? { redirect: { name: "lab-settings" } } : {}),
      ...(context.single && route.name === "lab-research-overview" ? { redirect: { name: "projects-research-overview", params: {} } } : {}),
      ...(children ? { children } : {}),
    } as T
  }
  return routes.map(route => transform(route))
}

/**
 * Compatibility boundary for existing pages that consume labUid route context.
 * Resolve, RouterLink, push and replace all use the same canonical destinations.
 * The implicit UID comes only from the deployment contract; API authorization is unchanged.
 */
export function installOrganizationRouting(router: Router, context = scope) {
  const resolve = router.resolve.bind(router)
  const push = router.push.bind(router)
  const replace = router.replace.bind(router)

  function location(raw: RouteLocationRaw): RouteLocationRaw {
    if (typeof raw === "string")
      return canonicalOrganizationPath(raw, context)
    if ("path" in raw && raw.path)
      return { ...raw, path: canonicalOrganizationPath(raw.path, context) }
    if (!context.single || !("name" in raw) || !raw.name)
      return raw
    if (["labs", "labs-my", "lab-projects"].includes(String(raw.name))) {
      const requestedUid = raw.params?.labUid
      if (requestedUid != null && requestedUid !== context.uid)
        return { path: "/404/lab" }
      return { name: "project-dashboard", query: raw.query, hash: raw.hash }
    }
    const target = router.getRoutes().find(route => route.name === raw.name)
    if (!target?.meta.organizationUid)
      return raw
    const params = { ...raw.params }
    const requestedUid = params.labUid
    if (requestedUid != null && requestedUid !== context.uid)
      return { path: "/404/lab" }
    delete params.labUid
    return { ...raw, params }
  }

  function addContext<T extends { meta: Record<string, unknown>, params: Record<string, unknown> }>(route: T): T {
    if (context.single && route.meta.organizationUid)
      route.params = { ...route.params, labUid: context.uid }
    return route
  }

  router.resolve = ((raw, current) => addContext(resolve(location(raw), current))) as Router["resolve"]
  router.push = raw => push(location(raw))
  router.replace = raw => replace(location(raw))

  router.beforeEach((to: RouteLocationNormalized) => {
    const path = canonicalOrganizationPath(to.path, context)
    if (path !== to.path)
      return { path, query: to.query, hash: to.hash, replace: true }
    addContext(to)
  })
}
