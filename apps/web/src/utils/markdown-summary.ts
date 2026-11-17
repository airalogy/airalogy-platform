import { fromMarkdown } from 'mdast-util-from-markdown'

/** Plain text only: activity previews never inject HTML, links or executable AIMD. */
export function markdownSummary(markdown: string, limit = 360): string {
  const root = fromMarkdown(markdown)
  function text(node: { type: string, value?: string, alt?: string, children?: any[] }): string {
    if (node.type === 'html' || node.type === 'definition')
      return ''
    if (node.type === 'image' || node.type === 'imageReference')
      return node.alt || ''
    if (node.value !== undefined)
      return node.value
    const separator = ['root', 'list', 'listItem', 'blockquote'].includes(node.type) ? ' ' : ''
    return (node.children || []).map(text).join(separator)
  }
  const plain = text(root).replace(/\s+/g, ' ').trim()
  return plain.length > limit ? `${plain.slice(0, limit).trimEnd()}…` : plain
}
