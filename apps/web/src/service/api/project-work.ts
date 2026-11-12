import { documentRequest } from "./research-documents"

export const workStates = [
  "pending",
  "in_progress",
  "blocked",
  "in_review",
  "done",
  "cancelled",
] as const
export const workKinds = ["requirement", "task", "bug", "milestone"] as const
export type WorkState = (typeof workStates)[number]
export interface WorkEvidence {
  kind:
    | "document"
    | "protocol"
    | "record"
    | "file"
    | "analysis"
    | "research_task"
    | "external"
    | "unavailable"
  id?: string
  version?: string
  label?: string
  href?: string
  available?: boolean
}
export interface WorkContent {
  title: string
  kind: (typeof workKinds)[number]
  state: WorkState
  goal: string
  acceptance: string
  priority: "low" | "normal" | "high" | "urgent"
  assignee_user_id: string | null
  collaborator_ids: string[]
  planned_start: string | null
  planned_end: string | null
  blocker: string
  next_step: string
  dependency_ids: string[]
  evidence: WorkEvidence[]
}
export interface ProjectWork extends WorkContent {
  id: string
  project_id: string
  revision: number
  created_by_user_id: string
  created_at: string
  updated_at: string
  completed_at?: string | null
  can_write?: boolean
  can_approve?: boolean
  project_name?: string
  project_uid?: string
  lab_uid?: string
}
export interface WorkEvent {
  id: string
  kind: "created" | "updated" | "comment" | "progress" | "decision" | "test" | "acceptance"
  actor: string | null
  created_at: string
  payload: {
    body?: string
    rationale?: string
    scope?: string
    outcome?: string
    occurred_at?: string | null
    supersedes?: string
    reason?: string
    source_revision?: number
    snapshot?: ProjectWork
    evidence?: WorkEvidence[]
  }
}
export function blankWork(): WorkContent {
  return {
    title: "",
    kind: "task",
    state: "pending",
    goal: "",
    acceptance: "",
    priority: "normal",
    assignee_user_id: null,
    collaborator_ids: [],
    planned_start: null,
    planned_end: null,
    blocker: "",
    next_step: "",
    dependency_ids: [],
    evidence: [],
  }
}
export function workContent(item: WorkContent): WorkContent {
  return Object.fromEntries(
    Object.keys(blankWork()).map(key => [key, item[key as keyof WorkContent]]),
  ) as unknown as WorkContent
}
export function evidencePayload(items: WorkEvidence[]) {
  return items
    .map(({ kind, id, version, label }) => ({
      kind,
      id,
      version: version || "",
      label: label || "",
    }))
}
export function listProjectWork(params: {
  project_id?: string
  state?: WorkState
  mine?: boolean
  active_only?: boolean
  q?: string
  page?: number
  page_size?: number
}) {
  return documentRequest<{ items: ProjectWork[], total: number, can_write: boolean }>({
    url: "/project-work",
    params,
  })
}
export function getProjectWork(id: string) {
  return documentRequest<ProjectWork>({ url: `/project-work/${id}` })
}
export function saveProjectWork(
  item: WorkContent,
  id: string,
  projectId: string,
  revision: number,
  requestId: string,
  reason: string,
) {
  return documentRequest<ProjectWork>({
    url: revision ? `/project-work/${id}` : "/project-work",
    method: revision ? "PUT" : "POST",
    data: {
      ...item,
      planned_start: item.planned_start || null,
      planned_end: item.planned_end || null,
      evidence: evidencePayload(item.evidence),
      ...(revision
        ? { expected_revision: revision, request_id: requestId, change_reason: reason }
        : { id, project_id: projectId }),
    },
  })
}
export function projectWorkMembers(projectId: string) {
  return documentRequest<{ members: { id: string, name: string, username: string }[] }>({
    url: "/project-work/members",
    params: { project_id: projectId },
  })
}
export function projectWorkSources(projectId: string, kind: string, q = "") {
  return documentRequest<{ items: WorkEvidence[], limited: boolean }>({
    url: "/project-work/sources",
    params: { project_id: projectId, kind, q },
  })
}
export function projectWorkHistory(id: string, page = 1) {
  return documentRequest<{ events: WorkEvent[], total: number }>({
    url: `/project-work/${id}/activity`,
    params: { page },
  })
}
export function addWorkActivity(
  id: string,
  data: {
    request_id: string
    expected_revision: number
    kind: string
    body: string
    rationale: string
    scope: string
    outcome: string | null
    occurred_at: string | null
    supersedes: string | null
    evidence: WorkEvidence[]
  },
) {
  return documentRequest<{ revision: number }>({
    url: `/project-work/${id}/activity`,
    method: "POST",
    data: { ...data, evidence: evidencePayload(data.evidence) },
  })
}
export function workDocumentSnapshot(projectId: string, id: string, version: string) {
  return documentRequest<{ snapshot: Record<string, unknown> }>({
    url: `/project-work/document-snapshot/${id}/${version}`,
    params: { project_id: projectId },
  })
}

export function workProtocolSnapshot(projectId: string, id: string, version: string) {
  return documentRequest<{ snapshot: Record<string, unknown> }>({
    url: `/project-work/protocol-snapshot/${id}/${encodeURIComponent(version)}`,
    params: { project_id: projectId },
  })
}
