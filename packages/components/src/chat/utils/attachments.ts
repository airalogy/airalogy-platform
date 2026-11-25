export const chatFileAccept = "image/*,.pdf,.doc,.docx,text/*,.txt,.md,.markdown,.csv,.tsv,.json,.log,.yaml,.yml,.xml,.toml"

export interface ChatAttachmentPayload {
  name?: string | null
  type?: string | null
  serverId?: string | null
}

type ChatFileType = "image" | "docx" | "pdf" | "text"

export function resolveChatFileType(attachment: ChatAttachmentPayload): ChatFileType | null {
  const mimeType = attachment.type?.toLowerCase() || ""
  const extension = attachment.name?.split(".").pop()?.toLowerCase() || ""

  if (mimeType.startsWith("image/") || ["png", "jpg", "jpeg", "gif", "webp", "bmp", "tif", "tiff"].includes(extension)) {
    return "image"
  }

  if (mimeType === "application/pdf" || extension === "pdf") {
    return "pdf"
  }

  if (
    mimeType === "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    || mimeType === "application/msword" || ["docx", "doc"].includes(extension)
  ) {
    return "docx"
  }

  if (mimeType.startsWith("text/") || ["application/json", "application/xml", "application/yaml", "application/x-yaml"].includes(mimeType)
    || ["txt", "md", "markdown", "csv", "tsv", "json", "log", "yaml", "yml", "xml", "toml"].includes(extension)) {
    return "text"
  }

  return null
}
