import { Command } from 'cmdk'
import { motion } from 'framer-motion'
import { FileText, MessageSquare, Sparkles, Search } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { cn } from '@/lib/cn'
import { spring } from '@/lib/motion'

export function CommandPalette() {
  const [open, setOpen] = useState(false)
  const navigate = useNavigate()

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        setOpen((v) => !v)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  const go = (path: string) => {
    setOpen(false)
    navigate(path)
  }

  if (!open) return null
  return (
    <>
      <div
        className="fixed inset-0 z-50 bg-black/60 backdrop-blur-[6px]"
        onClick={() => setOpen(false)}
      />
      <motion.div
        initial={{ opacity: 0, scale: 0.97, y: -8 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        transition={spring}
        className="fixed left-1/2 top-[18%] z-50 -translate-x-1/2 w-full max-w-xl surface rounded-(--radius-drawer) shadow-(--shadow-elevated) overflow-hidden"
      >
        <Command label="命令面板" className="[&_[cmdk-input]]:outline-none">
          <div className="flex items-center gap-2 px-4 py-3 border-b border-(--color-border)">
            <Search className="size-4 text-(--color-text-faint)" />
            <Command.Input
              placeholder="搜文档 / 跳页面 / 运行操作…"
              className="flex-1 bg-transparent text-[14px] text-(--color-text) placeholder:text-(--color-text-faint) outline-none"
              autoFocus
            />
            <kbd className="font-mono text-[10px] text-(--color-text-faint) bg-(--color-surface-2) border border-(--color-border) rounded px-1.5 py-0.5">
              ESC
            </kbd>
          </div>
          <Command.List className="max-h-[320px] overflow-y-auto scroll-thin p-1.5">
            <Command.Empty className="px-3 py-6 text-center text-[12px] text-(--color-text-faint)">
              没有匹配项
            </Command.Empty>
            <Command.Group heading="跳转" className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-[11px] [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wider [&_[cmdk-group-heading]]:text-(--color-text-faint)">
              <Item icon={<FileText className="size-4" />} onSelect={() => go('/documents')}>
                文档管理
              </Item>
              <Item icon={<Sparkles className="size-4" />} onSelect={() => go('/faqs')}>
                FAQ 管理
              </Item>
              <Item icon={<MessageSquare className="size-4" />} onSelect={() => go('/assistant')}>
                智能问答
              </Item>
            </Command.Group>
          </Command.List>
        </Command>
      </motion.div>
    </>
  )
}

function Item({
  children,
  icon,
  onSelect,
}: {
  children: React.ReactNode
  icon?: React.ReactNode
  onSelect: () => void
}) {
  return (
    <Command.Item
      onSelect={onSelect}
      className={cn(
        'flex items-center gap-2.5 rounded-(--radius-control) px-2.5 py-2 text-[13px] text-(--color-text)',
        'cursor-pointer',
        'data-[selected=true]:bg-(--color-surface-2)',
        'aria-selected:bg-(--color-surface-2)',
      )}
    >
      {icon && <span className="text-(--color-text-muted)">{icon}</span>}
      {children}
    </Command.Item>
  )
}
