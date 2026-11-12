import { request } from "../request"

export type UseOutcome = "as_planned" | "adjusted" | "stopped" | "unknown"
export interface ProtocolUseFeedback {
  id: string
  outcome: UseOutcome
  is_real: boolean
  public: boolean
  active: boolean
  comment: string
  revision: number
  record_ids: string[]
  source_version_id: string
  source_protocol_id: string
  source_version: string
  source_name: string
  source_url: string
  eligible: boolean
}
export interface MyProtocolRating {
  id: string
  score: number
  comment: string
  conditions: string
  use_id: string | null
  public: boolean
  active: boolean
  revision: number
}
export interface RatingSummary {
  score: number | null
  rating_count: number
  rating_average: number | null
  distribution: Record<string, number>
  protocol_id: string
  version: string
  scope: "accessible" | "public"
  generated_at: string
  algorithm: string
  components: Record<string, number>
  policy: Record<string, number>
  basis: Record<string, unknown>
  records_count: number
  unclassified_records: number
  use_count: number
  copies_count: number
  effective_reuse_count: number
  lab_count: number
  reviews: { id: string, score: number, comment: string, conditions: string, kind: "use" | "author" | "reading", public: boolean, revision: number, author: string, updated_at: string, mine: boolean }[]
  feedback: { id: string, outcome: UseOutcome, comment: string, is_real: boolean, revision: number, mine: boolean }[]
  versions: string[]
}
export interface RatingMine {
  rating: MyProtocolRating | null
  uses: ProtocolUseFeedback[]
  history: { revision: number, payload: MyProtocolRating, created_at: string }[]
}
export const ratingApi = {
  summary: (id: string, version: string, scope = "accessible") => request<RatingSummary>({ metadata: { showError: false }, url: `/protocol-ratings/${id}`, params: { version, scope } }),
  mine: (id: string, version: string) => request<RatingMine>({ metadata: { showError: false }, url: `/protocol-ratings/${id}/mine`, params: { version } }),
  records: (id: string, version: string, page = 1) => request<{ items: { id: string, version: number, number: number, use_id: string | null }[], has_more: boolean }>({ metadata: { showError: false }, url: `/protocol-ratings/${id}/records`, params: { version, page } }),
  save: (id: string, version: string, data: Omit<MyProtocolRating, "id" | "revision"> & { expected_revision: number }) => request<RatingMine>({ metadata: { showError: false }, url: `/protocol-ratings/${id}/mine`, method: "PUT", params: { version }, data }),
  use: (id: string, version: string, data: { request_key: string, record_ids: string[], outcome: UseOutcome, is_real: boolean, public: boolean, comment: string }) => request<ProtocolUseFeedback>({ metadata: { showError: false }, url: `/protocol-ratings/${id}/uses`, method: "POST", params: { version }, data }),
  updateUse: (id: string, version: string, useId: string, data: { expected_revision: number, outcome: UseOutcome, is_real: boolean, public: boolean, active: boolean, comment: string }) => request<ProtocolUseFeedback>({ metadata: { showError: false }, url: `/protocol-ratings/${id}/uses/${useId}`, method: "PUT", params: { version }, data }),
}
