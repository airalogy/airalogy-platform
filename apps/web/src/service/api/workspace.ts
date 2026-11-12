import { baseURL } from "@/service/request"
import { localStg } from "@/utils/storage"
import { documentRequest } from "./research-documents"

export interface ProjectVisitInput {
  kind: "project" | "protocol" | "recording" | "record" | "document" | "editor"
  section?: "work" | "overview" | "protocols" | "documents" | "materials" | "knowledge"
  project_id?: string
  lab_uid?: string
  project_uid?: string
  protocol_uid?: string
  protocol_version?: string
  resource_id?: string
  record_version?: number
}
export interface WorkspaceProject {
  id: string
  uid: string
  name: string
  lab_uid: string
  lab_name: string
  visited_at: string | null
  pinned_id: number | null
  target: null | {
    kind: ProjectVisitInput["kind"]
    section?: ProjectVisitInput["section"]
    title: string | null
    protocol_id?: string
    protocol_version?: string
    record_number?: number
    route: { name: "project-work" | "project-overview" | "project-protocols" | "project-documents" | "project-materials" | "project-knowledge" | "research-document-detail" | "protocol-detail" | "protocol-editor" | "protocol-record-report", params: Record<string, string> }
  }
}

let pendingVisit: Promise<unknown> = Promise.resolve()
export function captureProjectVisit(input: ProjectVisitInput) {
  const token = localStg.get("token")
  if (!token)
    return
  // Separate from route-cancelled reads so a quick return Home still records the visit.
  pendingVisit = pendingVisit.catch(() => {}).then(async () => {
    if (localStg.get("token") !== token)
      return
    await fetch(`${baseURL.replace(/\/$/, "")}/workspace/project-visits`, {
      method: "POST",
      headers: { "Auth-Token": token, "Content-Type": "application/json" },
      body: JSON.stringify(input),
      keepalive: true,
      signal: AbortSignal.timeout(5000),
    })
  }).catch(() => {})
}

export async function recentProjectWorkspaces() {
  await pendingVisit
  return documentRequest<{ items: WorkspaceProject[] }>({ url: "/workspace/recent-projects" })
}
export function resolveDraftDestinations(protocol_ids: string[]) {
  return documentRequest<{ items: WorkspaceProject[] }>({ url: "/workspace/draft-destinations", method: "POST", data: { protocol_ids } })
}
