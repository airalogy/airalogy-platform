import type { ChatModel } from "@airalogy/shared/enum/chat"
import { request } from "../request"

export type DeploymentMode = "community" | "single_lab" | "single_organization"
export type SignupMode = "open" | "invite_only" | "disabled"
export type LabStructureMode = "flat" | "structured"
export type DocumentationProfile = "community" | "customer_managed" | "vendor_managed"

export type OrganizationType = "laboratory" | "company" | "institution" | "other"

export interface InstanceLabInfo {
  organization_type?: OrganizationType
  id: string
  uid: string
  name: string
}
export interface InstanceStatus {
  single_organization?: boolean
  organization?: InstanceLabInfo | null
  organization_structure_mode?: LabStructureMode
  default_organization_uid?: string
  default_organization_name?: string
  default_organization_type?: OrganizationType
  default_invitation_project_role?: Api.Project.ProjectRole
  deployment_mode: DeploymentMode
  single_lab: boolean
  initialized: boolean
  signup_mode: SignupMode
  bootstrap_token_required: boolean
  site_url: string
  lab_structure_mode: LabStructureMode
  documentation_profile: DocumentationProfile
  documentation_url: string
  support_url: string
  ai_enabled: boolean
  sms_login_enabled: boolean
  sms_signup_required: boolean
  enabled_chat_models: ChatModel[]
  chat_model_names?: Partial<Record<ChatModel, string>>
  lab: InstanceLabInfo | null
}

export interface SystemVersion {
  version: string
  tag: string | null
  commit: string
  build_time: string | null
  dirty: boolean
  release_manifest_sha256: string | null
  database_revision: string
  deployment_id: string | null
}

export async function fetchSystemVersion() {
  return request<SystemVersion>({
    url: "/system/version",
    metadata: { showError: false },
  })
}

export interface BootstrapPayload {
  organizationUid?: string
  organizationName?: string
  organizationType?: OrganizationType
  projectName?: string
  setupToken: string
  username: string
  email: string
  name: string
  password: string
  confirmPassword: string
}

export async function fetchInstanceStatus() {
  return request<InstanceStatus>({
    url: "/instance",
    metadata: { showError: false },
  })
}

export async function postInstanceBootstrap(payload: BootstrapPayload) {
  return request<{ token: string, user: Api.Auth.UserInfo, lab: InstanceLabInfo }>({
    url: "/instance/bootstrap",
    method: "POST",
    data: {
      organization_uid: payload.organizationUid,
      organization_name: payload.organizationName,
      organization_type: payload.organizationType,
      project_name: payload.projectName,
      username: payload.username,
      setup_token: payload.setupToken,
      email: payload.email,
      name: payload.name,
      password: payload.password,
      confirm_password: payload.confirmPassword,
    },
  })
}

export interface InvitationInfo {
  email: string
  expires_at: string
  lab: InstanceLabInfo
  existing_account: boolean
}

export async function fetchInvitation(token: string) {
  return request<InvitationInfo>({
    url: `/instance/invitations/${encodeURIComponent(token)}`,
    metadata: { showError: false },
  })
}

export async function postInvitation(payload: {
  displayName: string
  email?: string
  note?: string
  labRole: Api.Lab.LabRole
  projectRole: Api.Project.ProjectRole
}) {
  return request<{
    id: string
    email: string
    expires_at: string
    existing_account: boolean
    url: string
  }>({
    url: "/instance/invitations",
    method: "POST",
    data: {
      email: payload.email,
      display_name: payload.displayName,
      note: payload.note,
      lab_role: payload.labRole,
      project_role: payload.projectRole,
    },
  })
}

export interface InvitationRecord {
  id: string
  display_name: string | null
  note: string | null
  email: string
  expires_at: string
  status: "pending" | "claimed" | "expired" | "revoked" | "closed"
  claimed_by: string | null
  can_revoke: boolean
}

export function listInvitations(page: number) {
  return request<{ items: InvitationRecord[], total: number }>({ url: "/instance/invitations", params: { page } })
}

export function revokeInvitation(id: string) {
  return request<{ success: boolean }>({ url: `/instance/invitations/${id}/revoke`, method: "POST" })
}

export async function acceptInvitation(token: string) {
  return request<{ success: boolean, lab: InstanceLabInfo }>({
    url: `/instance/invitations/${encodeURIComponent(token)}/accept`,
    method: "POST",
  })
}

export async function createPasswordResetLink(userId: string) {
  return request<{ id: string, email: string, expires_at: string, url: string }>({
    url: "/instance/password-reset-links",
    method: "POST",
    data: { user_id: userId },
  })
}

export async function fetchPasswordReset(token: string) {
  return request<{ email: string, expires_at: string }>({
    url: `/instance/password-resets/${encodeURIComponent(token)}`,
    metadata: { showError: false },
  })
}

export async function postPasswordReset(
  token: string,
  payload: {
    password: string
    confirmPassword: string
  },
) {
  return request<{ success: boolean }>({
    url: `/instance/password-resets/${encodeURIComponent(token)}`,
    method: "POST",
    data: {
      password: payload.password,
      confirm_password: payload.confirmPassword,
    },
  })
}

export async function putOwnPassword(payload: {
  currentPassword: string
  password: string
  confirmPassword: string
}) {
  return request<{ success: boolean, token: string }>({
    url: "/instance/account/password",
    method: "PUT",
    data: {
      current_password: payload.currentPassword,
      password: payload.password,
      confirm_password: payload.confirmPassword,
    },
  })
}
