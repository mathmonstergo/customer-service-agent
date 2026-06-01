import { motion } from 'framer-motion'
import { CircleAlert, FileText } from 'lucide-react'
import type { ImportFile } from '@/api/schemas'
import { Skeleton } from '@/components/ui/skeleton'
import { StatusDot } from '@/components/ui/status-dot'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/cn'
import { ease, dur } from '@/lib/motion'
import { importFileStatusLabel, tr } from '@/lib/labels'

interface Props {
  items: ImportFile[]
  isPending: boolean
  isError: boolean
  onRetry: () => void
  onSelect: (id: string) => void
}

export function DocumentList({ items, isPending, isError, onRetry, onSelect }: Props) {
  if (isPending) return <ListSkeleton />
  if (isError)
    return (
      <div className="surface rounded-(--radius-card) px-6 py-10 text-center text-[13px] text-(--color-text-muted)">
        加载失败
        <Button className="ml-3" size="sm" onClick={onRetry}>
          重试
        </Button>
      </div>
    )
  if (!items.length)
    return (
      <div className="surface rounded-(--radius-card) px-6 py-12 text-center text-[13px] text-(--color-text-muted)">
        没有文档；点右上「上传文档」开始。
      </div>
    )
  return (
    <motion.div
      initial="initial"
      animate="animate"
      variants={{ animate: { transition: { staggerChildren: 0.025 } } }}
      className="surface overflow-hidden rounded-(--radius-card)"
    >
      <div className="grid grid-cols-[1fr_120px_140px_120px_80px] gap-2 border-b border-(--color-border) bg-(--color-surface-2) px-4 py-2 text-[11px] uppercase tracking-wider text-(--color-text-faint)">
        <div>名称</div>
        <div>状态</div>
        <div>切片 / Embedding</div>
        <div>解析器</div>
        <div className="text-right">禁用</div>
      </div>
      {items.map((f) => (
        <motion.button
          key={f.id}
          variants={{
            initial: { opacity: 0, y: 4 },
            animate: { opacity: 1, y: 0, transition: { duration: dur.base, ease: ease.out } },
          }}
          type="button"
          onClick={() => onSelect(f.id)}
          className={cn(
            'grid w-full grid-cols-[1fr_120px_140px_120px_80px] gap-2 border-b border-(--color-border-soft) px-4 py-3 text-left text-[13px] transition-colors',
            'hover:bg-(--color-surface-2)',
            f.is_disabled && 'opacity-55',
          )}
        >
          <div className="flex min-w-0 items-center gap-2">
            <FileText className="size-4 shrink-0 text-(--color-text-faint)" />
            <div className="min-w-0">
              <div className="truncate text-(--color-text)">{f.original_name}</div>
              <div className="mt-0.5 truncate text-[11px] text-(--color-text-faint)">
                {f.file_type} · {Number(f.message_count) || 0} 条消息
              </div>
            </div>
          </div>
          <StatusDot tone={mapStatus(f.status)} label={tr(importFileStatusLabel, f.status, f.status)} />
          <div className="flex flex-col gap-0.5">
            <span className="text-(--color-text-muted)">
              切片 <span className="text-(--color-text)">{f.chunk_count}</span>
            </span>
            <EmbeddingMini summary={f.embedding_summary} />
          </div>
          <div className="text-(--color-text-muted)">
            <Badge tone="muted">{f.parser}</Badge>
          </div>
          <div className="flex items-center justify-end text-[12px] text-(--color-text-faint)">
            {f.is_disabled ? '已禁' : ''}
            {f.error && <CircleAlert className="ml-1 size-3.5 text-(--color-danger)" />}
          </div>
        </motion.button>
      ))}
    </motion.div>
  )
}

function EmbeddingMini({ summary }: { summary?: ImportFile['embedding_summary'] }) {
  if (!summary) return <span className="text-[11px] text-(--color-text-faint)">—</span>
  const { ready_count = 0, total_chunks = 0, stale_count = 0, failed_count = 0 } = summary
  if (!total_chunks)
    return <span className="text-[11px] text-(--color-text-faint)">未生成</span>
  return (
    <span className="text-[11px] text-(--color-text-muted)">
      <span className="text-(--color-success)">{ready_count}</span>
      <span className="text-(--color-text-faint)"> / {total_chunks}</span>
      {stale_count > 0 && (
        <span className="ml-1.5 text-(--color-warning)">·{stale_count} 过期</span>
      )}
      {failed_count > 0 && (
        <span className="ml-1.5 text-(--color-danger)">·{failed_count} 失败</span>
      )}
    </span>
  )
}

function mapStatus(s: string) {
  if (s === 'completed') return 'ready' as const
  if (s === 'needs_review') return 'warning' as const
  if (s === 'failed') return 'failed' as const
  if (s === 'processing' || s === 'parsing') return 'pending' as const
  return 'muted' as const
}

function ListSkeleton() {
  return (
    <div className="surface space-y-2 rounded-(--radius-card) p-4">
      {Array.from({ length: 6 }).map((_, i) => (
        <Skeleton key={i} className="h-10 w-full" />
      ))}
    </div>
  )
}
