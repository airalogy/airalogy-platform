import { findAimdInlineTemplates } from "@airalogy/aimd-core/parser"
import { parseAndExtract } from "@airalogy/aimd-renderer"
import { fromMarkdown } from "mdast-util-from-markdown"

type RootContent = ReturnType<typeof fromMarkdown>["children"][number]
type Code = Extract<RootContent, { type: "code" }>

function markdownCode(source: string) {
  const blocks: Code[] = []
  const excluded: { start: number, end: number }[] = []
  function collect(nodes: RootContent[]) {
    for (const node of nodes) {
      if (node.type === "code" || node.type === "inlineCode" || node.type === "html") {
        if (node.position)
          excluded.push({ start: node.position.start.offset!, end: node.position.end.offset! })
        if (node.type === "code")
          blocks.push(node)
      }
      else if ("children" in node) {
        collect(node.children)
      }
    }
  }
  collect(fromMarkdown(source).children)
  return { blocks, excluded }
}

// The host schedules the complete dependency graph across the sidebar, Aira,
// and inline edits. Exclude its executable blocks from the second SDK instance.
export function hostedRecorderContent(content: string) {
  if (!content.toLowerCase().includes("assigner"))
    return content
  let result = content
  for (const block of markdownCode(content).blocks.reverse()) {
    if (block.lang?.toLowerCase() !== "assigner" || !block.meta)
      continue
    const start = block.position!.start.offset!
    const end = block.position!.end.offset!
    if (parseAndExtract(content.slice(start, end)).client_assigner.length)
      result = result.slice(0, start) + result.slice(end)
  }
  return result
}

// The published visual editor drops fence metadata when serializing Markdown.
// Preserve annotations of surviving blocks; source edits pass through unchanged.
export function preserveVisualFenceMetadata(previous: string, next: string) {
  if (previous === next)
    return next
  const oldBlocks = markdownCode(previous).blocks
  if (!oldBlocks.some(block => block.meta))
    return next
  const { blocks } = markdownCode(next)
  const unmatched = new Set(oldBlocks)
  const pairs = new Map<Code, Code>()
  for (const [index, block] of blocks.entries()) {
    const matches = [...unmatched].filter(old => old.lang === block.lang && old.value === block.value)
    const match = matches.includes(oldBlocks[index]) ? oldBlocks[index] : matches.length === 1 ? matches[0] : undefined
    if (match) {
      pairs.set(block, match)
      unmatched.delete(match)
    }
  }
  let result = next
  for (const block of [...blocks].reverse()) {
    if (block.meta || !block.lang)
      continue
    let old = pairs.get(block)
    if (!old) {
      const remaining = [...unmatched].filter(item => item.lang === block.lang)
      if (!remaining.some(item => item.meta))
        continue
      // Editing the body of one surviving fenced block must retain its arguments.
      // If a paste rewrites several such blocks at once, let the author use source.
      if (remaining.length !== 1 || blocks.filter(item => !pairs.has(item) && item.lang === block.lang).length !== 1)
        throw new Error("Ambiguous fenced-block metadata")
      old = remaining[0]
    }
    if (!old.meta)
      continue
    const start = block.position!.start.offset!
    const fence = /^(?:`{3,}|~{3,})[^\S\r\n]*[^\s`~]+/.exec(next.slice(start))
    if (fence) {
      const offset = start + fence[0].length
      result = `${result.slice(0, offset)} ${old.meta}${result.slice(offset)}`
    }
  }
  return result
}

// A compact, editable field list uses the same declarations as the inline form.
// Ignore code examples when collecting original declarations for the drawer.
export function recorderVariableList(content: string, names: string[]) {
  const { excluded } = markdownCode(content)
  const fields = new Map<string, string>()
  for (const match of findAimdInlineTemplates(content)) {
    if (match.type !== "var" || excluded.some(pos => match.start >= pos.start && match.start < pos.end))
      continue
    const name = match.content.split(/[:,=]/, 1)[0].trim()
    if (name && !fields.has(name))
      fields.set(name, match.raw)
  }
  return names.filter(id => /^[\p{L}\p{N}_-]+$/u.test(id)).map(id => fields.get(id) || `{{var|${id}}}`).join("\n\n")
}
