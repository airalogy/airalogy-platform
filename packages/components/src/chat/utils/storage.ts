import { createStorage } from "@airalogy/shared/utils"

const identityStorage = createStorage<{ userInfo: { id: string } }>("local")
export const chatStorage = createStorage<Record<string, Chat.ChatState>>("local", null)

export function chatAccountId() {
  return identityStorage.get("userInfo")?.id || ""
}
