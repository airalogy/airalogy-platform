import type { VNodeChild } from "vue"
import { useAppStore } from "@/store/modules/app"
import { CRITIC_MARKUP_SUBSTITUTIONS_DATA_KEY, protectAimdInlineTemplates, protectCriticMarkupSubstitutions } from "@airalogy/aimd-core"
import { createHtmlProcessor } from "@airalogy/aimd-renderer"
import { computed, defineComponent, h } from "vue"

type ReaderNode = ReturnType<ReturnType<typeof createHtmlProcessor>["runSync"]>["children"][number]

const textElements = new Set(["p", "strong", "b", "em", "i", "sup", "sub", "span", "ol", "ul", "li", "blockquote", "br", "hr", "pre", "code", "table", "thead", "tbody", "tr", "td", "th", "figure", "figcaption", "details", "summary"])

const elementClasses: Record<string, string> = { ol: "list-decimal pl-6", ul: "list-disc pl-6", pre: "whitespace-pre-wrap", p: "my-2" }

// Use the AIMD parser for step titles, checks and field labels. Only text and
// document structure reach the DOM. Downloads are served separately by publication ID.
function readerNode(node: ReaderNode): VNodeChild {
  if (node.type === "text")
    return node.value
  if (node.type !== "element")
    return ""
  const tag = node.tagName
  if (tag === "img")
    return String(node.properties.alt || "")
  if (["script", "style", "iframe", "object", "svg", "template"].includes(tag))
    return ""
  const children = node.children.map(readerNode)
  if (/^h[1-6]$/.test(tag))
    return h(`h${Math.min(6, Number(tag[1]) + 1)}`, { class: "mt-3 font-semibold" }, children)
  if (!textElements.has(tag))
    return children
  return h(tag, { class: elementClasses[tag] }, children)
}

export default defineComponent({
  props: { body: { type: String, required: true } },
  setup(props) {
    const app = useAppStore()
    const content = computed(() => {
      try {
        const processor = createHtmlProcessor({ math: false, locale: app.locale, assignerVisibility: "hidden" })
        const inline = protectAimdInlineTemplates(props.body)
        const critic = protectCriticMarkupSubstitutions(inline.content)
        const tree = processor.runSync(processor.parse(critic.content), { data: {
          aimdInlineTemplates: inline.templates,
          [CRITIC_MARKUP_SUBSTITUTIONS_DATA_KEY]: critic.substitutions,
        } })
        return tree.children.map(readerNode)
      }
      catch {
        return [h("pre", { class: "whitespace-pre-wrap" }, props.body)]
      }
    })
    return () => h("div", { class: "break-words leading-relaxed" }, content.value)
  },
})
