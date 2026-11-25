import type { ProtocolModels } from "@airalogy/shared/types"
import { useChatStore } from "@airalogy/components/chat/store"
import { getAiralogyId } from "@airalogy/shared/utils"
import { useWorkspaceAira } from "./useWorkspaceAira"

export function useProtocolChatHandoff() {
  const aira = useWorkspaceAira()
  return (protocol: ProtocolModels.ProjectProtocolInfo) => {
    if (!aira?.context.value || !aira.visible.value)
      return undefined
    const session = useChatStore().findSessionByUUID()
    if (session?.source === "protocol" && session.airalogyId === getAiralogyId(protocol))
      return { chat: session.uuid }
    return undefined
  }
}
