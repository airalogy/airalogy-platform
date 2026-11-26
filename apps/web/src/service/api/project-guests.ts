import { request } from "../request"

const root = "/project-guests"
export type GuestRole = "reader" | "recorder" | "editor"
export interface GuestPerson { avatar_url: string | null, id: string, name: string, email: string, username: string, display_name: string | null, projects: string[] }
interface Project { id: string, name: string }
export interface GuestProject extends Project { uid: string, description: string, role: GuestRole }
export interface GuestTeam {
  can_manage: boolean
  people: { id: string, name: string, username: string, avatar_url: string | null, email: string | null, access_until: string | null, role: GuestRole, expired: boolean }[]
  pending: { id: string, name: string | null, email: string, role: GuestRole }[]
}
export const guestTeam = (id: string) => request<GuestTeam>({ url: `${root}/projects/${id}/team` })
export function inviteGuest(id: string, data: { email: string, display_name?: string, role: GuestRole, access_until: string | null, locale: string }) {
  return request<{ url: string, delivery: "sent" | "link" | "failed" }>({ url: `${root}/projects/${id}/invitations`, method: "POST", data })
}
export function removeGuest(id: string, kind: "people" | "invitations", target: string) {
  return request({ url: `${root}/projects/${id}/${kind}/${target}`, method: "DELETE" })
}
export function inviteNameStatus(id: string, email: string) {
  return request<{ reuse: boolean }>({ url: `${root}/projects/${id}/invitation-name`, method: "POST", data: { email } })
}
export type DirectoryFilter = "all" | "staff" | "guest"
export type DirectoryPerson = (Api.Lab.MemberListItem & { kind: "staff" }) | (GuestPerson & { kind: "guest" })
export function organizationPeople(kind: DirectoryFilter, page: number, pageSize: number) {
  return request<{ list: DirectoryPerson[], total: number }>({ url: `${root}/people`, params: { kind, page, page_size: pageSize } })
}
export function renameGuest(id: string, displayName: string) {
  return request<{ display_name: string }>({ url: `${root}/directory/${id}`, method: "PATCH", data: { display_name: displayName } })
}
export const previewConversion = (id: string) => request<{ projects: Project[], transfer_first: string[] }>({ url: `${root}/conversion/${id}` })
export function convertMember(id: string, projects: string[], keepNone: boolean) {
  return request({ url: `${root}/conversion/${id}`, method: "POST", data: { projects, keep_none: keepNone, confirm: true } })
}
export const previewPromotion = (id: string) => request<{ projects: (Project & { role: GuestRole, access_until: string | null })[] }>({ url: `${root}/promotion/${id}` })
export function promoteGuest(id: string, projects: string[], keepNone: boolean) {
  return request({ url: `${root}/promotion/${id}`, method: "POST", data: { projects, keep_none: keepNone, confirm: true } })
}
export const guestProjects = () => request<GuestProject[]>({ url: `${root}/mine` })
export const guestProtocols = (id: string) => request<{ protocols: (Project & { uid: string })[] }>({ url: `${root}/mine/${id}` })
export interface GuestProtocol { name: string, aimd: string, version: string, role: GuestRole }
export const guestProtocol = (id: string) => request<GuestProtocol>({ url: `${root}/protocols/${id}` })

export function changeGuestAccess(project: string, person: string, role: GuestRole, until: number | null, previous: Pick<GuestTeam["people"][number], "role" | "access_until">) {
  return request({ url: `${root}/projects/${project}/people/${person}`, method: "PATCH", data: { previous: { role: previous.role, access_until: previous.access_until }, role, access_until: until === null ? null : new Date(until).toISOString() } })
}
export interface PersonProject extends Project {
  source: "direct" | "group" | "guest" | "inherited"
  role: Api.Project.ProjectRole | null
  path: string | null
  expired: boolean
  access_until: string | null
}
export const personProjects = (id: string) => request<PersonProject[]>({ url: `${root}/people/${id}/projects` })
export function reviseGuestProtocol(id: string, base: string, version: string, aimd: string) {
  return request<{ version: string }>({ url: `${root}/protocols/${id}/revisions`, method: "POST", data: { base_version: base, version, aimd } })
}
