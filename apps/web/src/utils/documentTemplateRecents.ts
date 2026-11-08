// Store only identifiers, per account. Re-fetch every template through authorized
// APIs before displaying it; a cached reference never grants access to its body.
export function recentTemplateIds(value: string | null): string[] {
  try {
    const ids: unknown = JSON.parse(value || "[]")
    return Array.isArray(ids)
      ? [...new Set(ids.filter((id): id is string => typeof id === "string" && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id)))].slice(0, 4)
      : []
  }
  catch { return [] }
}
