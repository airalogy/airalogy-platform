import type { ExternalDashboard } from "@/service/api/external-access"

import { canManageCash, canManageContracts } from "@/service/api/project-operations"
import { $t } from "@airalogy/shared/locales"

export type Coverage = "single" | "selected" | "accessible"
export interface ProjectTarget {
  mode: Coverage
  organization: string | null
  ids: string[]
}

type Project = ExternalDashboard["projects"][number]

export function coveredProjects(target: ProjectTarget, singleId: string | null, projects: Project[]) {
  if (target.mode === "single")
    return projects.filter(p => p.enabled && p.id === singleId)
  return projects.filter(p => p.enabled && p.lab_id === target.organization && (target.mode === "accessible" || target.ids.includes(p.id)))
}

export function projectTarget(target: ProjectTarget, singleId: string | null) {
  if (target.mode === "single")
    return { project_id: singleId || undefined }
  return { project_coverage: target.mode, organization_id: target.organization || undefined, selected_project_ids: target.mode === "selected" ? target.ids : undefined }
}

export function eligibleScope(scope: string, projects: Project[], ongoing: boolean) {
  function allows(p: Project) {
    if (["records:import", "records:revise"].includes(scope))
      return p.can_record !== false
    if (scope === "collaboration:read")
      return p.can_collaborate !== false
    if (scope === "collaboration:write")
      return p.can_collaborate !== false && p.can_write_collaboration !== false
    if (scope === "contracts:create")
      return canManageContracts(p.cash_role)
    if (scope === "cash:create" || scope === "cash:link")
      return canManageCash(p.cash_role)
    if (scope === "cash:read" || scope === "contracts:read")
      return Boolean(p.cash_role)
    if (["records:export", "analysis:read", "analysis:write"].includes(scope))
      return p.can_export
    if (["protocols:candidate", "protocols:publish"].includes(scope))
      return p.can_author
    return true
  }
  return projects.length > 0 && (ongoing ? projects.some(allows) : projects.every(allows))
}

const scopeLabels = {
  "projects:find": "externalAccess.findProject",
  "projects:create": "externalAccess.registerProject",
  "cash:read": "externalAccess.readCash",
  "cash:create": "externalAccess.postCash",
  "contracts:read": "externalAccess.readContracts",
  "contracts:create": "externalAccess.createContracts",
  "cash:link": "externalAccess.linkReceipt",
  "collaboration:read": "externalAccess.readCollaboration",
  "collaboration:write": "externalAccess.writeCollaboration",
  "protocols:read": "externalAccess.readProtocols",
  "records:read": "externalAccess.readRecords",
  "records:export": "externalResearch.exportRecords",
  "analysis:read": "externalResearch.readAnalysis",
  "analysis:write": "externalResearch.writeAnalysis",
  "records:complex": "externalResearch.complex",
  "knowledge:read": "externalResearch.knowledge",
  "documents:read": "externalResearch.documents",
  "materials:read": "externalResearch.materials",
  "files:read": "externalResearch.files",
  "protocols:source": "externalResearch.readSource",
  "protocols:candidate": "externalResearch.candidate",
  "protocols:publish": "externalResearch.publish",
  "records:import": "externalAccess.importRecords",
  "records:revise": "externalAccess.reviseRecords",
} as const

export function scopeLabel(scope: string) {
  const key = scopeLabels[scope as keyof typeof scopeLabels]
  return key ? $t(key) : scope
}

export const externalScopes = Object.keys(scopeLabels)
