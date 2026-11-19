import { documentRequest } from "./research-documents"

export type BusinessRole = "lead" | "finance" | "viewer"
export type Kind = "contract" | "installment" | "cost" | "cash" | "forecast" | "closing"
export interface DocRef {
  id: string
  version: number
}
export type Value = string | number | null | DocRef
export type EntryData = { kind: Kind } & Record<string, Value>
export interface Entry {
  id: string
  kind: Kind
  data: EntryData
  status: string
  revision: number
  updated_by?: string
  updated_at?: string
  created_by: string
  verified_by: string | null
  verified_at: string | null
}
export interface Summary {
  gross: number
  received: number
  paid: number
  net_cash: number
  direct: number
  profit: number | null
  overdue: number
  unpaid: number
  unmatched: number
  pending: number
  shared: number
  needs_review: boolean
  estimate_date: string | null
  verified_through: string | null
  contracts: Record<
    string,
    { outstanding: number | null, unscheduled: number, cost: number, entries: string[] }
  >
  installments: Record<
    string,
    { balance: number, overdue: number, matched: string[], conditional: boolean }
  >
  sources: Record<string, string[]>
}
export type Metric =
  | "gross"
  | "received"
  | "paid"
  | "net_cash"
  | "direct"
  | "profit"
  | "overdue"
  | "unpaid"
  | "unmatched"
  | "pending"
  | "shared"
export interface Person {
  id: string
  name: string
  username?: string
}
export interface Book {
  owner: Person | null
  role: BusinessRole
  entries: Entry[]
  people: Record<string, string>
  summary: Summary
}
export interface PortfolioRow {
  id: string
  name: string
  href: string
  owner: Person | null
  summary: Summary
  contracts: { id: string, title: string }[]
}
export interface Source {
  id: string
  title: string
  version?: number
}
export interface Choices {
  documents: Source[]
  work: Source[]
  files: Source[]
}
export interface Revision {
  actor: string
  actor_id: string
  at: string
  reason: string
  before: Entry | null
  after: Entry
}
export interface Settings {
  enabled: boolean
  revision: number
  people: Person[]
  grants: Record<string, BusinessRole>
}
const prefix = "/project-operations"
export function readOps<T>(path: string, params?: Record<string, string>) {
  return documentRequest<T>({ url: prefix + path, params })
}
export function writeOps<T>(path: string, data: unknown, method: "POST" | "PUT" = "PUT") {
  return documentRequest<T>({ url: prefix + path, method, data })
}
export function money(fen: number | null) {
  return fen === null
    ? "—"
    : new Intl.NumberFormat("zh-CN", { style: "currency", currency: "CNY" }).format(fen / 100)
}
export function toFen(text: string) {
  if (!/^\d{1,10}(?:\.\d{1,2})?$/.test(text))
    throw new Error("amount")
  const [whole, fraction = ""] = text.split(".")
  return Number(whole) * 100 + Number(fraction.padEnd(2, "0"))
}
