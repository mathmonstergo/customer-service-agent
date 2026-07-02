import { Copy } from 'lucide-react'
import { toast } from '@/components/ui/toast'
import { cn } from '@/lib/cn'
import { HoverTooltip } from './hover-tooltip'

// 文件/切片 ID 复制按钮，关键约束是界面只显示短动作，hover 和 toast 给出完整 ID。
export function CopyIdButton({
  label,
  value,
  className,
}: {
  label: string
  value: string
  className?: string
}) {
  const clean = value.trim()
  if (!clean) return null
  return (
    <HoverTooltip
      content={
        <span className="flex min-w-0 items-center gap-1.5">
          <span>复制{label}</span>
          <span className="max-w-[180px] truncate font-mono text-(--color-text-muted)">
            {clean}
          </span>
        </span>
      }
    >
      <button
        type="button"
        onClick={() => void copyIdText(clean, label)}
        className={cn(
          'inline-flex h-5 shrink-0 cursor-pointer items-center gap-1 rounded-(--radius-control) px-1.5',
          'text-[11px] text-(--color-text-faint) transition-colors',
          'hover:bg-(--color-surface-2) hover:text-(--color-text)',
          className,
        )}
        aria-label={`复制${label}`}
      >
        <Copy className="size-3" />
        复制ID
      </button>
    </HoverTooltip>
  )
}

// 复制完整 ID 到剪贴板，关键约束是失败时给用户显式反馈。
async function copyIdText(value: string, label: string): Promise<void> {
  try {
    if (!navigator.clipboard?.writeText) throw new Error('clipboard unavailable')
    await navigator.clipboard.writeText(value)
    toast.success(`已复制${label} ${value}`)
  } catch {
    toast.error(`复制${label}失败`)
  }
}
