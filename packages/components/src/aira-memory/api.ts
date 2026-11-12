export const preferenceOptions = {
  language: ["zh-CN", "en-US"],
  detail: ["concise", "detailed"],
  format: ["paragraphs", "steps"],
  explanation: ["accessible", "technical"],
} as const
export type PreferenceKey = keyof typeof preferenceOptions
export interface MemoryState {
  enabled: boolean
  revision: number
  preferences: Partial<Record<PreferenceKey, { value: string, source: "chat" | "settings", updated_at: string, chat_id: string | null }>>
}
export interface MemoryEvent {
  revision: number
  action: string
  keys: PreferenceKey[]
  created_at: string
}
export async function memoryRequest<T>(endpoint: string, token: string, path = "", body?: Record<string, unknown>): Promise<T> {
  const response = await fetch(`${endpoint}${path}`, {
    method: body ? "PATCH" : "GET",
    headers: { "Auth-Token": token, "Content-Type": "application/json" },
    cache: "no-store",
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!response.ok)
    throw new Error(response.status === 409 ? "conflict" : "failed")
  return response.json()
}
