import { request } from "../request"

export interface ExternalPolicy { enabled: boolean, blocked_fields: string[], revision: number }
export interface ExternalGrant {
  id: string
  name: string
  project_id: string | null
  organization_id?: string | null
  project_coverage?: "selected" | "accessible" | null
  selected_project_ids?: string[] | null
  scopes: string[]
  token_prefix: string
  expires_at: string
  revoked_at: string | null
}
export interface ExternalOperation {
  id: string
  kind: string
  state: string
  grant_id?: string
  expires_at: string
  digest?: string
  tool_name?: string
  summary?: {
    project_name?: string
    meeting_url?: string
    filename?: string
    audience?: "participants" | "selected" | "project"
    protocol_name?: string
    title?: string
    snapshot_id?: string
    snapshot_digest?: string
    reproducibility?: string
    files?: Array<{ filename: string, kind: string, sha256: string, size_bytes: number }>
    protocol_version?: string
    row_count?: number
    record_id?: string
    expected_version?: number
    changes?: Record<string, { before: unknown, after: unknown }>
    source_digest?: string
    version?: string
    base_version?: string
    compatibility?: Record<string, unknown> | null
    file_changes?: Array<{ path: string, status: string, diff: string }>
    reason?: string
  }
  payload?: { content?: string, binary_files?: Record<string, string>, csv?: string, reason?: string, changes?: Record<string, unknown>, report?: string, method?: string, limitations?: string, environment?: Record<string, string>, files?: Array<{ filename: string, kind: string, content_base64: string, sha256: string }> }
  result?: { links?: string[] }
}
export interface ExternalDashboard {
  organizations?: Array<{ id: string, name: string, enabled: boolean, can_register?: boolean }>
  projects: Array<{ cash_role?: string | null, id: string, name: string, lab_id: string, enabled: boolean, can_export: boolean, can_author: boolean, can_record?: boolean, can_collaborate?: boolean, can_write_collaboration?: boolean }>
  grants: ExternalGrant[]
  operations: ExternalOperation[]
  analysis_next_offset?: number | null
  analyses?: Array<{ id: string, title: string, project_id: string, created_at: string }>
  audit: Array<{ id: string, event: string, created_at: string, grant_id: string | null }>
}

async function data<T>(options: Parameters<typeof request<T>>[0]): Promise<T> {
  const result = await request<T>({ ...options, metadata: { showError: false } })
  if (result.error || result.data === null)
    throw result.error || new Error("No external access response")
  return result.data
}

export const getExternalDashboard = (projectId?: string, analysisOffset = 0) => data<ExternalDashboard>({ url: "/external-access/dashboard", params: { project_id: projectId, analysis_offset: analysisOffset, include_reports: Boolean(projectId) } })
export function createExternalGrant(payload: { name: string, project_id?: string, organization_id?: string, project_coverage?: "selected" | "accessible", selected_project_ids?: string[], scopes: string[], expires_in_days: number }) {
  return data<{ grant: ExternalGrant, token: string }>({ url: "/external-access/grants", method: "POST", data: payload })
}
export const revokeExternalGrant = (id: string) => data<{ revoked: boolean }>({ url: `/external-access/grants/${id}`, method: "DELETE" })
export const getExternalOperation = (id: string, projectId?: string) => data<ExternalOperation>({ url: `/external-access/operations/${id}`, params: { project_id: projectId } })
export function decideExternalOperation(id: string, digest: string, approve: boolean) {
  return data<ExternalOperation>({ url: `/external-access/operations/${id}/decision`, method: "POST", data: { digest, approve } })
}
export const getExternalPolicy = (id: string) => data<ExternalPolicy>({ url: `/external-access/labs/${id}/policy` })
export function saveExternalPolicy(id: string, payload: ExternalPolicy) {
  return data<ExternalPolicy>({
    url: `/external-access/labs/${id}/policy`,
    method: "PUT",
    data: { enabled: payload.enabled, blocked_fields: payload.blocked_fields, expected_revision: payload.revision },
  })
}

export interface ExternalAnalysis {
  id: string
  question: string
  created_at: string
  source_digest: string
  source_snapshot: Record<string, unknown>
  source_selection: Record<string, unknown>
  recipe: { method: string, environment: Record<string, string>, parameters: Record<string, unknown> }
  result: { method?: { pipeline_id: string, revision_id: string, revision: number }, title: string, report: string, limitations: string, execution: string, executor: string, reproducibility: string, files: Array<{ id: string, filename: string, sha256: string, size_bytes: number }> }
  rerun_of_id: string | null
}
export const getExternalAnalysis = (id: string, projectId?: string) => data<ExternalAnalysis>({ url: `/external-access/analyses/${id}`, params: { project_id: projectId } })
export async function downloadExternalAnalysisFile(runId: string, fileId: string) {
  const result = await request<Blob, "blob">({ url: `/external-access/analyses/${runId}/files/${fileId}`, responseType: "blob", metadata: { showError: false } })
  if (result.error || result.data === null)
    throw result.error || new Error("No analysis file response")
  return result.data
}

type PriorOAuthGrant = Pick<ExternalGrant, "id" | "scopes" | "project_id" | "organization_id" | "project_coverage" | "selected_project_ids">
export const readExternalOAuthRequest = (payload: Record<string, unknown>) => data<{ client_name: string, redirect_uri: string, resource: string, scopes: string[], prior_grants?: PriorOAuthGrant[] }>({ url: "/external-access/oauth/request", method: "POST", data: payload })
export const consentExternalOAuth = (payload: Record<string, unknown>) => data<{ redirect_to: string }>({ url: "/external-access/oauth/consent", method: "POST", data: payload })
export const registerExternalOAuthClient = (name: string, redirectUri: string) => data<{ client_id: string }>({ url: "/external-access/oauth/clients", method: "POST", data: { name, redirect_uris: [redirectUri] } })
export const listExternalOAuthClients = () => data<{ items: Array<{ client_id: string, name: string, redirect_uris: string[] }> }>({ url: "/external-access/oauth/clients" })
export const deleteExternalOAuthClient = (id: string) => data<{ deleted: boolean }>({ url: `/external-access/oauth/clients/${id}`, method: "DELETE" })
