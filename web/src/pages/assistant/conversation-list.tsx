// 左侧会话列表：仿 ChatGPT 的可折叠 sidebar。
// 展开（默认）240px，收起 48px 仅图标。状态存在父组件，跨刷新不持久化（避免 SSR/水合复杂度）。
import { useState } from 'react'
import { motion } from 'framer-motion'
import {
  MessageSquare,
  Plus,
  Trash2,
  PanelLeftClose,
  PanelLeftOpen,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/cn'
import { useAssistant } from '@/store/assistant'
import { ease, dur } from '@/lib/motion'

export function ConversationSidebar({
  collapsed,
  onToggle,
}: {
  collapsed: boolean
  onToggle: () => void
}) {
  const order = useAssistant((s) => s.conversationOrder)
  const conversations = useAssistant((s) => s.conversations)
  const currentId = useAssistant((s) => s.currentId)
  const newConversation = useAssistant((s) => s.newConversation)
  const selectConversation = useAssistant((s) => s.selectConversation)
  const renameConversation = useAssistant((s) => s.renameConversation)
  const deleteConversation = useAssistant((s) => s.deleteConversation)

  const [editingId, setEditingId] = useState<string | null>(null)
  const [draft, setDraft] = useState('')

  if (collapsed) {
    return (
      <aside className="flex h-full w-12 shrink-0 flex-col items-center gap-2 border-r border-(--color-border) bg-(--color-surface) py-3">
        <Button
          variant="ghost"
          size="icon"
          onClick={onToggle}
          aria-label="展开会话列表"
          title="展开会话列表"
        >
          <PanelLeftOpen className="size-4" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          onClick={() => newConversation()}
          aria-label="新建会话"
          title="新建会话"
        >
          <Plus className="size-4" />
        </Button>
      </aside>
    )
  }

  return (
    <aside className="flex h-full w-[240px] shrink-0 flex-col border-r border-(--color-border) bg-(--color-surface)">
      <div className="flex shrink-0 items-center gap-2 border-b border-(--color-border) px-3 py-2.5">
        <Button
          variant="ghost"
          size="icon"
          onClick={onToggle}
          aria-label="收起会话列表"
          title="收起会话列表"
        >
          <PanelLeftClose className="size-4" />
        </Button>
        <Button
          variant="primary"
          size="sm"
          onClick={() => newConversation()}
          className="ml-auto"
        >
          <Plus className="size-3.5" />
          新建会话
        </Button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto scroll-thin p-2">
        {order.length === 0 ? (
          <div className="px-3 py-6 text-center text-[12px] text-(--color-text-faint)">
            还没有会话
            <br />
            点上方「新建会话」开始
          </div>
        ) : (
          <ul className="flex flex-col gap-0.5">
            {order.map((id) => {
              const conv = conversations[id]
              if (!conv) return null
              const isActive = id === currentId
              const isEditing = id === editingId
              return (
                <motion.li
                  key={id}
                  layout
                  transition={{ duration: dur.base, ease: ease.out }}
                  className={cn(
                    'group flex items-center gap-1 rounded-(--radius-control) px-2 py-1.5',
                    'cursor-pointer border transition-colors',
                    isActive
                      ? 'border-(--color-primary)/30 bg-(--color-primary-soft)'
                      : 'border-transparent hover:bg-(--color-surface-2)',
                  )}
                  onClick={() => !isEditing && selectConversation(id)}
                  onDoubleClick={() => {
                    setEditingId(id)
                    setDraft(conv.title)
                  }}
                >
                  <MessageSquare
                    className={cn(
                      'size-3.5 shrink-0',
                      isActive ? 'text-(--color-primary-hi)' : 'text-(--color-text-faint)',
                    )}
                  />
                  {isEditing ? (
                    <Input
                      autoFocus
                      value={draft}
                      onChange={(e) => setDraft(e.target.value)}
                      onBlur={() => {
                        if (draft.trim() && draft.trim() !== conv.title) {
                          renameConversation(id, draft.trim())
                        }
                        setEditingId(null)
                      }}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') (e.target as HTMLInputElement).blur()
                        if (e.key === 'Escape') setEditingId(null)
                      }}
                      className="h-6 px-1.5 text-[12px]"
                      onClick={(e) => e.stopPropagation()}
                    />
                  ) : (
                    <span
                      className={cn(
                        'min-w-0 flex-1 truncate text-[13px]',
                        isActive ? 'text-(--color-text)' : 'text-(--color-text-muted)',
                      )}
                      title={conv.title}
                    >
                      {conv.title}
                    </span>
                  )}
                  {!isEditing && (
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation()
                        if (window.confirm(`删除「${conv.title}」？`)) {
                          deleteConversation(id)
                        }
                      }}
                      className={cn(
                        'shrink-0 rounded-(--radius-control) p-1 text-(--color-text-faint)',
                        'opacity-0 transition-opacity group-hover:opacity-100',
                        'hover:bg-(--color-danger-soft) hover:text-(--color-danger)',
                      )}
                      aria-label="删除会话"
                    >
                      <Trash2 className="size-3" />
                    </button>
                  )}
                </motion.li>
              )
            })}
          </ul>
        )}
      </div>
      <div className="shrink-0 border-t border-(--color-border) px-3 py-2 text-[11px] text-(--color-text-faint)">
        双击重命名 · 本地存储
      </div>
    </aside>
  )
}
