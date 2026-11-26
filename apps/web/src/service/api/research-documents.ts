import type { AimdProtocolRecordData, AimdRecordValidationSchema } from "@airalogy/aimd-recorder"
import type { ResearchLogScopeParams } from "./research-log"
import { request } from "../request"
import { fetchBlobContent } from "./common"

export type DocumentKind =
  | "document"
  | "experiment"
  | "progress"
  | "meeting"
  | "reflection"
  | "blocker"
  | "milestone"
export interface DocumentContent {
  title: string
  kind: DocumentKind
  body_format?: "md" | "aimd"
  body: string
  record_data: AimdProtocolRecordData
  file_ids: string[]
  tags: string[]
  collection: string
  occurred_at?: string | null
}
export interface Material {
  id: string
  filename: string
  content_type: string
  size_bytes: number
  sha256: string
  created_at?: string
  source_note?: string
  occurred_at?: string | null
  previewable?: boolean
  unavailable?: boolean
}
export interface ResearchDocument extends DocumentContent, ResearchLogScopeParams {
  meeting_id?: string | null
  meeting_url?: string | null
  id: string
  revision: number
  state: "draft" | "submitted"
  scope_name: string
  can_edit: boolean
  origin: Record<string, unknown>
  files: Material[]
  created_at: string
  updated_at: string
}
export interface DocumentSummary {
  meeting_url?: string | null
  meeting_status?: "held" | "planned" | "cancelled" | null
  id: string
  title: string
  kind: DocumentKind
  state: "draft" | "submitted"
  revision: number
  tags: string[]
  collection: string
  excerpt: string
  updated_at: string
  occurred_at: string
}
export interface DocumentBrowseParams {
  q?: string
  kind?: string
  page?: number
  page_size?: number
  order?: "updated" | "recorded"
  date_from?: string
  date_to?: string
  time_zone?: string
}
export interface DocumentValidation {
  valid: boolean
  schema: AimdRecordValidationSchema | null
  errors: { field: string, message: string }[]
}
export interface DocumentPreview {
  preview_digest: string
  requires_confirmation?: boolean
  snapshot?: Record<string, unknown>
  impact?: {
    field_changes: { field: string, before?: Record<string, unknown>, after?: Record<string, unknown> }[]
    definition_changed: boolean
    existing_values: boolean
    removed_values: string[]
    requires_confirmation: boolean
  }
}
export interface DocumentRevision {
  revision: number
  snapshot: Record<string, unknown>
  change_summary: string
  created_at: string
}
export async function documentRequest<T>(options: Parameters<typeof request<T>>[0]): Promise<T> {
  const { data, error } = await request<T>({ ...options, metadata: { showError: false } })
  if (error)
    throw error
  if (data === null)
    throw new Error("No data returned")
  return data
}
export function listResearchDocuments(
  scope: ResearchLogScopeParams,
  params: DocumentBrowseParams = {},
) {
  return documentRequest<{ items: DocumentSummary[], total_count: number, has_searchable_items: boolean, can_write: boolean }>({
    url: "/research-documents",
    params: { ...scope, ...params },
  })
}
export function researchDocumentCalendar(scope: ResearchLogScopeParams, params: { month: string, q?: string, kind?: string, time_zone: string }) {
  return documentRequest<{ days: { date: string, count: number }[] }>({ url: "/research-documents/calendar", params: { ...scope, ...params } })
}
export function createResearchDocument(
  data: Partial<DocumentContent> &
    ResearchLogScopeParams & {
      id: string
      title: string
      source_document_id?: string
      source_template_id?: string
      source_template_revision?: number
      template_locale?: string
      source_protocol_version_id?: string
    },
) {
  return documentRequest<ResearchDocument>({ url: "/research-documents", method: "POST", data })
}
export function getResearchDocument(id: string) {
  return documentRequest<ResearchDocument>({ url: `/research-documents/${id}` })
}
export function saveResearchDocument(
  id: string,
  data: DocumentContent & {
    expected_revision: number
    preview_digest?: string
    change_summary?: string
  },
) {
  return documentRequest<ResearchDocument>({
    url: `/research-documents/${id}`,
    method: "PUT",
    data,
  })
}
export function previewResearchDocument(
  id: string,
  data: DocumentContent & { expected_revision: number },
) {
  return documentRequest<DocumentPreview>({
    url: `/research-documents/${id}/preview`,
    method: "POST",
    data,
  })
}
export function validateResearchDocument(id: string) {
  return documentRequest<DocumentValidation>({
    url: `/research-documents/${id}/validate`,
    method: "POST",
  })
}
export function submitResearchDocument(
  id: string,
  expected_revision: number,
  preview_digest?: string,
) {
  return documentRequest<DocumentPreview & { state?: "submitted", submission_id?: string }>({
    url: `/research-documents/${id}/submit`,
    method: "POST",
    data: { expected_revision, preview_digest },
  })
}
export function researchDocumentHistory(id: string) {
  return documentRequest<{ items: DocumentRevision[] }>({
    url: `/research-documents/${id}/revisions`,
  })
}
export function restoreResearchDocument(
  id: string,
  revision: number,
  expected_revision: number,
  preview_digest?: string,
) {
  return documentRequest<DocumentPreview | ResearchDocument>({
    url: `/research-documents/${id}/restore/${revision}`,
    method: "POST",
    data: { expected_revision, preview_digest },
  })
}
export function deriveResearchDocument(
  id: string,
  data: {
    expected_revision: number
    kind: "protocol" | "knowledge"
    title: string
    body: string
    preview_digest?: string
  },
) {
  return documentRequest<DocumentPreview & { id?: string, knowledge_id?: string }>({
    url: `/research-documents/${id}/derive`,
    method: "POST",
    data,
  })
}
export function listResearchMaterials(scope: ResearchLogScopeParams, q = "", page = 1) {
  return documentRequest<{ items: Material[], total_count: number, can_upload: boolean }>({
    url: "/research-materials",
    params: { ...scope, q, page },
  })
}
export function uploadResearchMaterial(
  scope: ResearchLogScopeParams,
  file: File,
  key: string,
  sourceNote = "",
  occurredAt?: string,
) {
  const data = new FormData()
  for (const [name, value] of Object.entries(scope)) {
    if (value)
      data.set(name, value)
  }
  data.set("file", file)
  data.set("request_key", key)
  data.set("source_note", sourceNote)
  if (occurredAt)
    data.set("occurred_at", occurredAt)
  return documentRequest<Material>({ url: "/research-materials", method: "POST", data })
}
export function extractResearchMaterial(id: string) {
  return documentRequest<{
    file_id: string
    sha256: string
    text: string
    truncated: boolean
    empty: boolean
  }>({ url: `/research-materials/${id}/text` })
}
export async function downloadResearchDocument(id: string, derivationId?: string) {
  return fetchBlobContent(
    derivationId
      ? `/research-documents/${id}/methods/${derivationId}/package`
      : `/research-documents/${id}/export`,
  )
}

export function importResearchDocument(
  scope: ResearchLogScopeParams,
  file: File,
  key: string,
  digest?: string,
) {
  const data = new FormData()
  for (const [name, value] of Object.entries(scope)) {
    if (value)
      data.set(name, value)
  }
  data.set("file", file)
  data.set("request_key", key)
  if (digest)
    data.set("preview_digest", digest)
  return documentRequest<DocumentPreview | ResearchDocument>({
    url: "/research-documents/import",
    method: "POST",
    data,
  })
}

export function recentResearchDocuments(scope_type?: ResearchLogScopeParams["scope_type"]) {
  return documentRequest<{
    items: Pick<DocumentSummary, "id" | "title" | "state" | "updated_at">[]
  }>({ url: "/research-documents/recent", params: { scope_type } })
}
export function researchProtocolSources(project_id: string, q = "") {
  return documentRequest<{ items: { id: string, name: string, version: string }[] }>({
    url: "/research-documents/protocol-sources",
    params: { project_id, q },
  })
}

export function researchDocumentSubmissions(id: string) {
  return documentRequest<{ items: { id: string, source_revision: number, snapshot: Record<string, unknown>, created_at: string }[] }>({ url: `/research-documents/${id}/submissions` })
}
