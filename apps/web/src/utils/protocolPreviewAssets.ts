import type { ObjectDirective } from "vue"

type ResolveAsset = (path: string) => Promise<{ url: string } | null>
const observers = new WeakMap<HTMLElement, MutationObserver>()

// Recorder renders asynchronously. Resolve package-relative links only inside
// the preview and discard late responses after a field, file or page changes.
export const vProtocolPreviewAssets: ObjectDirective<HTMLElement, ResolveAsset> = {
  mounted(root, binding) {
    const pending = new Map<string, Promise<string | undefined>>()
    const attributes = ["src", "poster", "href"]
    function resolve(element: Element) {
      for (const attribute of attributes) {
        const path = element.getAttribute(attribute)
        if (!path || /^(?:[a-z][a-z\d+.\-]*:|\/\/|#)/i.test(path))
          continue
        let url = pending.get(path)
        if (!url) {
          url = binding.value(path).then(result => result?.url).catch(() => undefined)
          pending.set(path, url)
        }
        void url.then((value) => {
          if (value && value !== path && observers.has(root) && root.contains(element) && element.getAttribute(attribute) === path)
            element.setAttribute(attribute, value)
        })
      }
    }
    function scan(node: Node) {
      if (!(node instanceof Element))
        return
      resolve(node)
      node.querySelectorAll("[src],[poster],[href]").forEach(resolve)
    }
    const observer = new MutationObserver((changes) => {
      for (const change of changes) {
        if (change.type === "attributes")
          resolve(change.target as Element)
        else change.addedNodes.forEach(scan)
      }
    })
    observers.set(root, observer)
    observer.observe(root, { childList: true, subtree: true, attributes: true, attributeFilter: attributes })
    scan(root)
  },
  beforeUnmount(root) {
    observers.get(root)?.disconnect()
    observers.delete(root)
  },
}
