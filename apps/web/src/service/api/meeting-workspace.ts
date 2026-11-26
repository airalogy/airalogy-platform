import { fetchBlobContent } from "./common"
import { documentRequest } from "./research-documents"

export interface Person {
  id: string
  name: string
  username: string
}
export interface Cue {
  start: number | null
  end: number | null
  text: string
  speaker: string
  account_id?: string | null
  account_name?: string | null
}
export interface Source {
  audio: boolean
  transcript: { revision: number, filename: string, cues: Cue[] } | null
}
export interface Room {
  projects?: { id: string, name: string, path: string }[]
  attendees?: Person[]
  id: string
  title: string
  body: string
  body_format: "md" | "aimd"
  lab_id?: string
  occurred_at?: string
  revision: number
  project_ids: string[]
  participants: string[]
  shared_with: string[]
  can_manage: boolean
  can_read_sources: boolean
}
export interface Task {
  id: string
  title: string
  description: string
  due: string | null
  state: string
  assignee_id: string | null
  audience: string
  revision: number
  href?: string
  can_update?: boolean
}
export interface Options {
  people: Person[]
  projects: { id: string, name: string }[]
}
export const spaceUrl = (id: string) => `/meeting-workspace/rooms/${id}`
export function workspaceGet<T>(url: string, params?: Record<string, unknown>) {
  return documentRequest<T>({ url, params })
}
export function workspaceSave<T>(url: string, method: "PUT" | "POST" | "PATCH", data: unknown) {
  return documentRequest<T>({ url, method, data })
}
export function roomOptions(id: string, project?: string) {
  return workspaceGet<Options>(`/meeting-workspace/organizations/${id}/options`, { project_id: project })
}
export async function sourceFile(id: string, path: string) {
  const blob = await fetchBlobContent(`${spaceUrl(id)}/${path}`)
  if (!blob)
    throw new Error("Download failed")
  return blob
}
