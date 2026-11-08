import type { DocumentKind, DocumentPreview } from "./research-documents"
import type { ResearchLogScopeParams } from "./research-log"
import { documentRequest } from "./research-documents"

export interface TemplateScope extends ResearchLogScopeParams {
  name: string
  can_write: boolean
}
export interface TemplateContent {
  title: string
  description: string
  kind: DocumentKind
  body: string
}
export interface DocumentTemplate extends TemplateContent {
  id: string
  revision: number
  scope_type: "builtin" | "personal" | "lab" | "project"
  lab_id?: string
  project_id?: string
  builtin: boolean
  can_edit: boolean
  archived: boolean
  updated_at?: string
}
export function scopeKey(scope: ResearchLogScopeParams) {
  return scope.project_id ? `project:${scope.project_id}` : scope.lab_id ? `lab:${scope.lab_id}` : "personal"
}
export function scopeParams(scope: ResearchLogScopeParams): ResearchLogScopeParams {
  return { scope_type: scope.scope_type, lab_id: scope.lab_id || undefined, project_id: scope.project_id || undefined }
}
export function templateScopes() {
  return documentRequest<{ items: TemplateScope[] }>({ url: "/document-templates/scopes" })
}
export function builtinTemplates(locale: string) {
  return documentRequest<{ items: DocumentTemplate[] }>({ url: "/document-templates/builtins", params: { locale } })
}
export function listDocumentTemplates(scope: ResearchLogScopeParams, params: { q?: string, page?: number, archived?: boolean, page_size?: number } = {}) {
  return documentRequest<{ items: DocumentTemplate[], total_count: number, can_write: boolean }>({ url: "/document-templates", params: { ...scopeParams(scope), ...params } })
}
export function getDocumentTemplate(id: string) {
  return documentRequest<DocumentTemplate>({ url: `/document-templates/${id}` })
}
export function createDocumentTemplate(data: TemplateContent & ResearchLogScopeParams & { id: string, source_document_id?: string, source_revision?: number, source_template_id?: string, source_template_revision?: number, preview_digest?: string }) {
  return documentRequest<DocumentTemplate | DocumentPreview>({ url: "/document-templates", method: "POST", data })
}
export function updateDocumentTemplate(id: string, data: TemplateContent & { expected_revision: number, preview_digest?: string }) {
  return documentRequest<DocumentTemplate | DocumentPreview>({ url: `/document-templates/${id}`, method: "PUT", data })
}
export function archiveDocumentTemplate(item: DocumentTemplate, archived: boolean) {
  return documentRequest<DocumentTemplate>({ url: `/document-templates/${item.id}/archive`, method: "POST", data: { expected_revision: item.revision, archived } })
}
export function templateHistory(id: string) {
  return documentRequest<{ items: { revision: number, snapshot: TemplateContent & { archived: boolean }, created_at: string }[] }>({ url: `/document-templates/${id}/revisions` })
}
export function templateError(err: unknown, fallback: string) {
  const detail = (err as { response?: { data?: { detail?: string | { message?: string } } } })?.response?.data?.detail
  return typeof detail === "string" ? detail : detail?.message || fallback
}
