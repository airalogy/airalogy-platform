/** Keep the workspace location stable across list, reading and editor routes. */
export function workspaceDestination(name: string) {
  if (name === "research-documents" || name === "research-document-detail")
    return "research-documents"
  if (name.includes("knowledge"))
    return "knowledge-home"
  if (["profile-records", "project-records", "lab-records"].includes(name))
    return "profile-records"
  if (name === "projects-research-overview")
    return "project-dashboard"
  if (name === "lab-research-overview")
    return "labs-my"
  if (name.includes("research"))
    return "research-tasks"
  if (name.includes("protocol"))
    return "protocols-my"
  if (name.startsWith("project"))
    return "project-dashboard"
  if (name.startsWith("lab"))
    return "labs-my"
  if (name === "home" || name === "root")
    return "home"
  return null
}
