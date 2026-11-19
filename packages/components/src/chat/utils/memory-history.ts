import { $t } from "@airalogy/shared/locales"

export function localizeMemoryTitle(title: string, isMemoryRequest = false) {
  return isMemoryRequest ? $t("airaMemory.historyRequest") : title
}

// Older device caches contain the two neutral messages but no presentation hint.
// Only server-restored messages have zero timestamps and these parent/child links.
export function restoreCachedMemorySummaries(session: Chat.ChatSession) {
  if (!session.serverId || session.memorySummariesResolved)
    return

  for (const [index, message] of session.data.entries()) {
    if (message.memorySummary || message.dateTime !== 0 || !message.inversion
      || message.text !== "[Personal memory management request]" || message.attachments?.length) {
      continue
    }
    const reply = session.data[index + 1]
    if (reply && reply.dateTime === 0 && !reply.inversion && reply.parentIndex === index
      && reply.text === "[Memory management handled by Platform; no research data changed.]") {
      message.memorySummary = "request"
      reply.memorySummary = "handled"
    }
  }
}
