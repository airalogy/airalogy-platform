import { isAxiosError } from "axios"

export type ResourceFailure = "unavailable" | "temporary"

/** Older deployments used 400 for denied reads. Other 400s may be unrelated. */
export function resourceFailure(error: unknown): ResourceFailure {
  if (isAxiosError(error)) {
    const status = error.response?.status
    const detail = error.response?.data?.detail
    if (status === 422 && Array.isArray(detail) && detail.some(issue => ["path", "query"].includes(issue.loc?.[0])))
      return "unavailable"
    if (status === 401 || status === 403 || status === 404
      || (status === 400 && error.response?.data?.detail === "Permission denied")) {
      return "unavailable"
    }
  }
  return "temporary"
}
