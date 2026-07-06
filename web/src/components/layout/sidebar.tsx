import { useEffect, useRef } from 'react'
import { NavLink } from 'react-router-dom'
import {
  Activity,
  ChevronRight,
  FileText,
  Network,
  MessageSquare,
  Sparkles,
  Settings,
} from 'lucide-react'
import { cn } from '@/lib/cn'
import { useUi } from '@/store/ui'
import { nextSidebarCollapsedForPointerDown } from './sidebar-interaction'

const NAV_MIGRATED = [
  { path: '/documents', label: '文档管理', icon: FileText },
  { path: '/faqs', label: 'FAQ 管理', icon: Sparkles },
  { path: '/assistant', label: '智能问答', icon: MessageSquare },
  { path: '/knowledge-graph', label: '知识图谱', icon: Network },
  { path: '/evaluation', label: '效果验收', icon: Activity },
  { path: '/settings', label: '设置', icon: Settings },
]

export function Sidebar() {
  const { sidebarCollapsed, setSidebarCollapsed } = useUi()
  const sidebarRef = useRef<HTMLElement>(null)

  useEffect(() => {
    const onPointerDown = (event: PointerEvent) => {
      const sidebar = sidebarRef.current
      const isInsideSidebar =
        !!sidebar && event.target instanceof Node && sidebar.contains(event.target)
      setSidebarCollapsed(nextSidebarCollapsedForPointerDown({ isInsideSidebar }))
    }

    document.addEventListener('pointerdown', onPointerDown, true)
    return () => document.removeEventListener('pointerdown', onPointerDown, true)
  }, [setSidebarCollapsed])

  return (
    <aside
      ref={sidebarRef}
      className={cn(
        'flex h-full shrink-0 flex-col border-r border-(--color-border) bg-(--color-bg) transition-[width] duration-200',
        sidebarCollapsed ? 'w-14' : 'w-56',
      )}
    >
      <div className={cn('flex items-center gap-2 px-4 pt-4 pb-3', sidebarCollapsed && 'justify-center px-0')}>
        <span className="inline-flex size-7 items-center justify-center rounded-(--radius-control) bg-(--color-primary) font-mono text-[11px] font-[580] text-white">
          Cy
        </span>
        {!sidebarCollapsed && (
          <span className="font-[540] text-(--color-text)">Cyclops</span>
        )}
      </div>

      <nav className="mt-2 flex flex-1 flex-col gap-0.5 px-2">
        {!sidebarCollapsed && (
          <div className="px-2 pt-2 pb-1 text-[10px] uppercase tracking-[0.16em] text-(--color-text-faint)">
            工作区
          </div>
        )}
        {NAV_MIGRATED.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            className={({ isActive }) =>
              cn(
                'group flex items-center gap-2.5 rounded-(--radius-control) px-2 py-1.5 text-[13px] transition-colors',
                isActive
                  ? 'bg-(--color-primary-soft) text-(--color-text)'
                  : 'text-(--color-text-muted) hover:bg-(--color-surface-2) hover:text-(--color-text)',
              )
            }
          >
            <item.icon className="size-4 shrink-0" />
            {!sidebarCollapsed && <span>{item.label}</span>}
          </NavLink>
        ))}
      </nav>

      <button
        type="button"
        onClick={() => setSidebarCollapsed(false)}
        aria-label="展开功能区"
        className={cn(
          !sidebarCollapsed && 'hidden',
          'mx-2 mb-3 mt-2 inline-flex items-center justify-center gap-1.5 rounded-(--radius-control) py-1.5 text-[12px] text-(--color-text-faint)',
          'hover:bg-(--color-surface-2) hover:text-(--color-text-muted)',
        )}
      >
        <ChevronRight className="size-3.5" />
      </button>

      {!sidebarCollapsed && (
        <div className="px-3 pb-3 text-[10px] text-(--color-text-faint) leading-[1.6]">
          按 <kbd className="font-mono">⌘K</kbd> 打开命令面板
        </div>
      )}
    </aside>
  )
}
