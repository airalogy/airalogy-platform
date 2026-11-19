/** Presentation only: every destination still enforces its existing API permissions. */
export const singleLabSharedEntries = [
  { name: "lab-knowledge", label: "page.singleLabWorkspace.knowledge" },
  { name: "lab-resources", label: "page.resourceLibrary.title" },
  { name: "lab-records", label: "page.singleLabWorkspace.log" },
] as const

export const singleLabManagementRoutes = new Set(["lab-research-overview", "lab-members", "lab-organization", "lab-access", "lab-settings", "lab-groups"])

export function singleLabManagementEntries(structured: boolean, canManageLab: boolean) {
  return [
    ...(canManageLab ? [{ name: "lab-research-overview", label: "page.orgResearch.title" }] : []),
    { name: "lab-members", label: "page.labs.members" },
    ...(structured
      ? [{ name: "lab-organization", label: "page.labs.access.organization" }, { name: "lab-access", label: "page.labs.access.title" }]
      : [{ name: "lab-groups", label: "page.labs.groups" }]),
    ...(canManageLab ? [{ name: "lab-settings", label: "page.labs.settings" }] : []),
  ] as { name: App.Global.RouteNameKey, label: I18n.I18nKey }[]
}
