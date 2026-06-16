import { useLocation } from 'react-router-dom'
import { Command } from 'lucide-react'

const TITLES: Record<string, string> = {
  '/documents': '文档管理',
  '/faqs': 'FAQ 管理',
  '/assistant': '智能问答',
  '/evaluation': '效果验收',
}

// 全局顶栏保持固定高度；标题映射要覆盖所有主路由，避免页面切换时文字位置空跳。
export function Topbar() {
  const { pathname } = useLocation()
  const title = TITLES[pathname] || ''
  return (
    <header className="flex h-12 shrink-0 items-center justify-between border-b border-(--color-border) bg-(--color-bg) px-5">
      <div className="flex items-center gap-2 text-[14px] font-[500] text-(--color-text)">
        {title}
      </div>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => {
            const e = new KeyboardEvent('keydown', { key: 'k', metaKey: true, bubbles: true })
            window.dispatchEvent(e)
          }}
          className="inline-flex items-center gap-1.5 rounded-(--radius-control) border border-(--color-border) bg-(--color-surface-2) px-2 py-1 text-[12px] text-(--color-text-muted) hover:bg-(--color-surface-3) hover:text-(--color-text)"
        >
          <Command className="size-3.5" />
          <span>K</span>
        </button>
      </div>
    </header>
  )
}
