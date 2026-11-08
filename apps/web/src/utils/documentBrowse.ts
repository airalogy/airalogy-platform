/** Local calendar dates are distinct from saved UTC timestamps. */
export function localDocumentDate(value: string | Date = new Date()): string {
  const d = new Date(value)
  if (!Number.isFinite(d.getTime()))
    return ""
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
}
export function documentDateInstant(day: string, previous?: string | null): string | undefined {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(day))
    return undefined
  const [year, month, date] = day.split("-").map(Number)
  const value = previous ? new Date(previous) : new Date()
  if (!Number.isFinite(value.getTime()))
    return undefined
  value.setFullYear(year, month - 1, date)
  return localDocumentDate(value) === day ? value.toISOString() : undefined
}
export function documentTimeZone() {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC"
}
export function queryText(value: unknown) {
  return typeof value === "string" ? value : ""
}
export function documentBrowseQuery(query: Record<string, unknown>) {
  // Only carry document filters, never arbitrary redirect or privilege parameters.
  const result: Record<string, string> = {}
  for (const key of ["q", "kind", "order", "from", "to", "page", "read"]) {
    const value = queryText(query[key])
    if (value)
      result[key] = value
  }
  return result
}
