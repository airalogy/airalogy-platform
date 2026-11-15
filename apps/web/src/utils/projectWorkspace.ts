import type { ProjectVisitInput, WorkspaceProject } from "@/service/api/workspace"
import type { RecordDraft } from "./recordDrafts"

interface RouteContext {
  name?: unknown
  params: Record<string, unknown>
  query: Record<string, unknown>
}
const text = (value: unknown) => typeof value === "string" ? value : undefined

/** Persist only known destinations, never arbitrary URLs, search terms or form values. */
export function projectVisitForRoute(route: RouteContext): ProjectVisitInput | null {
  const name = String(route.name || "")
  const base = { lab_uid: text(route.params.labUid), project_uid: text(route.params.projectUid) }
  if (name === "research-document-detail")
    return { kind: "document", resource_id: text(route.params.documentId) }
  if (["research-documents", "project-documents"].includes(name) && text(route.query.read))
    return { ...base, kind: "document", resource_id: text(route.query.read), project_id: text(route.query.project_id) }
  if (name === "research-documents" && text(route.query.project_id)) {
    const section = route.query.tab === "materials" ? "materials" : "documents"
    return { kind: "project", project_id: text(route.query.project_id), section }
  }
  if (!base.lab_uid || !base.project_uid)
    return null
  const section = name.replace("project-", "")
  if (["overview", "protocols", "documents", "materials", "knowledge", "work", "meetings", "records"].includes(section))
    return { ...base, kind: "project", section: section as ProjectVisitInput["section"] }
  const protocol_uid = text(route.params.protocolUid)
  if (!protocol_uid)
    return null
  if (name === "protocol-record-report") {
    const version = Number(route.params.recordVersion)
    return Number.isInteger(version) && version > 0 ? { ...base, protocol_uid, kind: "record", resource_id: text(route.params.recordId), record_version: version } : null
  }
  if (["add-protocol-record", "add-protocol-record-from-workflow"].includes(name))
    return { ...base, protocol_uid, kind: "recording" }
  if (name === "protocol-editor")
    return { ...base, protocol_uid, kind: "editor", protocol_version: text(route.params.protocolVersion) }
  if (["protocol-detail", "protocol-records", "protocol-discussions"].includes(name))
    return { ...base, protocol_uid, kind: "protocol" }
  return null
}

export interface ProjectCard extends WorkspaceProject {
  draft?: RecordDraft
  lastUsed: number
}

export function mergeProjectWorkspaces(recent: WorkspaceProject[], authorizedDrafts: WorkspaceProject[], drafts: RecordDraft[]): ProjectCard[] {
  const result = new Map<string, ProjectCard>(recent.map(item => [item.id, { ...item, lastUsed: item.visited_at ? Date.parse(item.visited_at) || 0 : 0 }]))
  for (const project of authorizedDrafts) {
    const draft = drafts.filter(item => item.protocolId === project.target?.protocol_id && Number.isFinite(item.timestamp) && (!item.scope?.version || item.scope.version === project.target?.protocol_version)).sort((a, b) => b.timestamp - a.timestamp)[0]
    if (!draft)
      continue
    const current = result.get(project.id)
    if (!current || draft.timestamp >= current.lastUsed || (current.target?.kind === "recording" && current.target.protocol_id === draft.protocolId)) {
      result.set(project.id, { ...project, pinned_id: current?.pinned_id ?? null, visited_at: current?.visited_at ?? null, draft, lastUsed: Math.max(draft.timestamp, current?.lastUsed || 0) })
    }
  }
  const pinOrder = new Map(recent.filter(item => item.pinned_id).map((item, i) => [item.id, i]))
  return [...result.values()].sort((a, b) => {
    if (a.pinned_id || b.pinned_id)
      return (pinOrder.get(a.id) ?? Infinity) - (pinOrder.get(b.id) ?? Infinity)
    return b.lastUsed - a.lastUsed || a.id.localeCompare(b.id)
  })
}
