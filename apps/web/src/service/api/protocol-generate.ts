import type { CodeEditRequest, CodeEditResponse } from "@airalogy/masterbrain-client"
import type { ChatModelConfig } from "@airalogy/shared"
import { request } from "../request"

export interface ExtractedProtocolInstructionFile {
  filename: string
  text: string
  was_trimmed: boolean
  content_type: string
}

export interface EditorCodeEditPayload extends Omit<CodeEditRequest, "model"> {
  model: ChatModelConfig
  syntax_repair?: boolean
}

export interface ProtocolSourceDiagnostic {
  path: string
  message: string
  line: number
  column: number
  code: string
}

export interface ProtocolSourceValidation {
  status: "valid" | "invalid" | "unavailable"
  diagnostics: ProtocolSourceDiagnostic[]
  source_hash: string
  level: "static"
}

export interface ProtocolSourceFile {
  path: string
  content: string
  type: "aimd" | "py" | "toml" | "other"
}

interface GeneratedProtocolDraft {
  content: string
  original_content: string
  validation: ProtocolSourceValidation
  repair_status: "not_needed" | "applied" | "needs_review" | "failed" | "unavailable"
}

export function validateProtocolSources(files: ProtocolSourceFile[]) {
  return request<ProtocolSourceValidation>({
    url: "/editor/validate_sources",
    method: "POST",
    data: { files },
  })
}

export async function extractProtocolInstructionFile(file: File) {
  if (!file) {
    throw new Error("file is required")
  }

  const formData = new FormData()
  formData.append("file", file)

  const { data, error } = await request<ExtractedProtocolInstructionFile>({
    url: "/editor/protocol_instruction_extract",
    method: "POST",
    data: formData,
    timeout: 1000 * 60 * 5,
  })

  return { data, error }
}

/**
 * Generate AIMD file based on user instruction
 * @param payload Request payload
 * @param payload.instruction User input instruction (1-20000 characters)
 * @param payload.model Chat model configuration
 * @returns Generated AIMD file content (plain text)
 */
export async function generateProtocolAimd(payload: {
  instruction: string
  model: ChatModelConfig
}, requestId?: string) {
  const { data, error } = await request<GeneratedProtocolDraft>({
    url: "/editor/protocol_generate_draft",
    method: "POST",
    data: payload,
    timeout: 1000 * 60 * 10, // Includes at most one repair attempt.
    metadata: {
      requestId,
    },
  })

  return { data: data?.content || null, error, validation: data?.validation, repairStatus: data?.repair_status }
}

/**
 * Generate Python model based on AIMD file
 * @param payload Request payload
 * @param payload.protocol_aimd AIMD file content (1-3000 characters)
 * @param payload.model Chat model configuration
 * @returns Generated Python model code (plain text)
 */
export async function generateProtocolModel(payload: {
  protocol_aimd: string
  model: ChatModelConfig
}, requestId?: string) {
  const { data, error } = await request<string>({
    url: "/editor/protocol_generate_model",
    method: "POST",
    data: payload,
    timeout: 1000 * 60 * 5,
    headers: {
      Accept: "text/plain",
    },
    metadata: {
      requestId,
    },
  })

  return { data, error }
}

/**
 * Generate Assigner based on AIMD and Model content
 * @param payload Request payload
 * @param payload.protocol_aimd AIMD file content (1-3000 characters)
 * @param payload.protocol_model Python model code (1-3000 characters)
 * @param payload.model Chat model configuration
 * @returns Generated Assigner code (plain text)
 */
export async function generateProtocolAssigner(payload: {
  protocol_aimd: string
  protocol_model: string
  model: ChatModelConfig
}, requestId?: string) {
  const { data, error } = await request<string>({
    url: "/editor/protocol_generate_assigner",
    method: "POST",
    data: payload,
    timeout: 1000 * 60 * 5,
    headers: {
      Accept: "text/plain",
    },
    metadata: {
      requestId,
    },
  })

  return { data, error }
}

export async function postEditorCodeEdit(payload: EditorCodeEditPayload, requestId?: string) {
  const { data, error } = await request<CodeEditResponse>({
    url: "/editor/code_edit",
    method: "POST",
    data: payload,
    timeout: 1000 * 60 * 5,
    metadata: {
      requestId,
    },
  })

  return { data, error }
}
