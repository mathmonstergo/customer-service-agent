import { NavLink } from 'react-router-dom'
import {
  Activity,
  ChevronLeft,
  ChevronRight,
  FileText,
  MessageSquare,
  Sparkles,
} from 'lucide-react'
import { cn } from '@/lib/cn'
import { useUi } from '@/store/ui'

const NAV_MIGRATED = [
  { path: '/documents', label: '文档管理', icon: FileText },
  { path: '/faqs', label: 'FAQ 管理', icon: Sparkles },
  { path: '/assistant', label: '智能问答', icon: MessageSquare },
  { path: '/evaluation', label: '效果验收', icon: Activity },
]

export function Sidebar() {
  const { sidebarCollapsed, toggleSidebar } = useUi()
  return (
    <aside
      className={cn(
        'flex h-full shrink-0 flex-col border-r border-(--color-border) bg-(--color-bg) transition-[width] duration-200',
        sidebarCollapsed ? 'w-14' : 'w-56',
      )}
    >
      <div className={cn('flex items-center gap-2 px-4 pt-4 pb-3', sidebarCollapsed && 'justify-center px-0')}>
        <span className="inline-flex size-7 items-center justify-center rounded-(--radius-control) bg-(--color-primary) font-mono text-[11px] font-[580] text-white">
          CS
        </span>
        {!sidebarCollapsed && (
          <span className="font-[540] text-(--color-text)">客服助手</span>
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
        onClick={toggleSidebar}
        className={cn(
          'mx-2 mb-3 mt-2 inline-flex items-center justify-center gap-1.5 rounded-(--radius-control) py-1.5 text-[12px] text-(--color-text-faint)',
          'hover:bg-(--color-surface-2) hover:text-(--color-text-muted)',
        )}
      >
        {sidebarCollapsed ? <ChevronRight className="size-3.5" /> : <ChevronLeft className="size-3.5" />}
        {!sidebarCollapsed && <span>折叠</span>}
      </button>

      {!sidebarCollapsed && (
        <div className="px-3 pb-3 text-[10px] text-(--color-text-faint) leading-[1.6]">
          按 <kbd className="font-mono">⌘K</kbd> 打开命令面板
        </div>
      )}
    </aside>
  )
}
