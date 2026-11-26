import { documentTimeZone } from "@/utils/documentBrowse"
import { documentRequest } from "./research-documents"

export interface MeetingLink { href?: string, id: string, title: string, relation: "created" | "discussed" }
interface WorkEntry { id: string, title: string, project: string, href: string }
export interface AgendaEntry extends WorkEntry {
  at: string | null
  day: string | null
  time_precision: "date" | "datetime"
  status: "held" | "planned" | "cancelled"
  open_count: number
}
export interface TodoEntry extends WorkEntry {
  due: string | null
  status: string
  assignee: string | null
  kind: string
  meetings: (MeetingLink & { href: string })[]
}
export type Scope = "mine" | "managed" | "visible"
export type Period = "upcoming" | "past" | "undated"
export type WorkView = "meetings" | "todos"
interface WorkQuery { scope: Scope, period: Period, project_id?: string, page: number }
export function loadWorkPage(view: WorkView, query: WorkQuery) {
  return documentRequest<{ items: (AgendaEntry | TodoEntry)[], has_more: boolean }>({
    url: "/my-work",
    params: { ...query, view, time_zone: documentTimeZone() },
  })
}
export function loadWorkProjects(scope: Scope) {
  return documentRequest<{ projects: { id: string, name: string }[] }>({ url: "/my-work", params: { view: "projects", scope } })
}
export function loadWorkSummary() {
  return documentRequest<{ meeting: AgendaEntry | null, todo: TodoEntry | null }>({ url: "/my-work", params: { view: "summary", time_zone: documentTimeZone() } })
}
