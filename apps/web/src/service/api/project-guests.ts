import { request } from "../request"

const root = "/project-guests"
export type GuestRole = "reader" | "recorder"
export interface GuestPerson { id: string, name: string, email: string, projects: string[] }
interface Project { id: string, name: string }
export interface GuestProject extends Project { uid: string, description: string, role: GuestRole }
export interface GuestTeam {
  people: { id: string, name: string, email: string, role: GuestRole, expired: boolean }[]
  pending: { id: string, email: string, role: GuestRole }[]
}
export const guestTeam = (id: string) => request<GuestTeam>({ url: `${root}/projects/${id}/team` })
export function inviteGuest(id: string, data: { email: string, role: GuestRole, access_until: string | null, locale: string }) {
  return request<{ url: string, delivery: "sent" | "link" | "failed" }>({ url: `${root}/projects/${id}/invitations`, method: "POST", data })
}
export function removeGuest(id: string, kind: "people" | "invitations", target: string) {
  return request({ url: `${root}/projects/${id}/${kind}/${target}`, method: "DELETE" })
}
export const guestDirectory = () => request<GuestPerson[]>({ url: `${root}/directory` })
export const previewConversion = (id: string) => request<{ projects: Project[], transfer_first: string[] }>({ url: `${root}/conversion/${id}` })
export function convertMember(id: string, projects: string[], keepNone: boolean) {
  return request({ url: `${root}/conversion/${id}`, method: "POST", data: { projects, keep_none: keepNone, confirm: true } })
}
export const guestProjects = () => request<GuestProject[]>({ url: `${root}/mine` })
export const guestProtocols = (id: string) => request<{ protocols: (Project & { uid: string })[] }>({ url: `${root}/mine/${id}` })
export interface GuestProtocol { name: string, aimd: string, version: string, role: GuestRole }
export const guestProtocol = (id: string) => request<GuestProtocol>({ url: `${root}/protocols/${id}` })
