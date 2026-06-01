// HTML sanitize：限定白名单标签 + 移除危险属性。
// 移植自旧 admin.js 的 sanitizeTableHtml；这里只允许表格相关 + 基础语义标签。

const ALLOWED_TAGS = new Set([
  'TABLE',
  'THEAD',
  'TBODY',
  'TFOOT',
  'TR',
  'TH',
  'TD',
  'CAPTION',
  'COLGROUP',
  'COL',
  'P',
  'SPAN',
  'STRONG',
  'EM',
  'CODE',
  'BR',
])
const ALLOWED_ATTRS = new Set(['colspan', 'rowspan', 'scope'])

export function sanitizeTableHtml(html: string): string {
  if (!html) return ''
  const tpl = document.createElement('template')
  tpl.innerHTML = html
  const walk = (node: Element) => {
    const children = Array.from(node.children)
    for (const child of children) {
      const tag = child.tagName
      if (!ALLOWED_TAGS.has(tag)) {
        // 用文本内容替代被禁止的标签
        const text = document.createTextNode(child.textContent || '')
        child.replaceWith(text)
        continue
      }
      for (const attr of Array.from(child.attributes)) {
        if (!ALLOWED_ATTRS.has(attr.name.toLowerCase())) {
          child.removeAttribute(attr.name)
        }
      }
      walk(child)
    }
  }
  walk(tpl.content as unknown as Element)
  return tpl.innerHTML
}
