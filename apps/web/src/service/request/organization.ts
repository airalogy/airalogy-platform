// Route context is a hint. The API checks membership and project ownership.
export const organizationUid = ref("")

export function organizationHeaders(): Record<string, string> {
  return organizationUid.value ? { "X-Airalogy-Organization": organizationUid.value } : {}
}
