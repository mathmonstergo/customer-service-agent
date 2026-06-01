import { motion } from 'framer-motion'
import type { Faq } from '@/api/schemas'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import { StatusDot } from '@/components/ui/status-dot'
import { cn } from '@/lib/cn'
import { dur, ease } from '@/lib/motion'
import { embeddingStatusLabel, faqStatusLabel, tr } from '@/lib/labels'

interface Props {
  items: Faq[]
  isPending: boolean
  isError: boolean
  onRetry: () => void
  activeId: string | null
  onSelect: (id: string) => void
}

export function FaqList({ items, isPending, isError, onRetry, activeId, onSelect }: Props) {
  if (isPending) return <ListSkeleton />
  if (isError)
    return (
      <Empty>
        加载失败
        <Button className="ml-3" size="sm" onClick={onRetry}>
          重试
        </Button>
      </Empty>
    )
  if (!items.length)
    return <Empty>还没有 FAQ；点右上「新建 FAQ」开始。</Empty>

  return (
    <motion.ul
      initial="initial"
      animate="animate"
      variants={{ animate: { transition: { staggerChildren: 0.025 } } }}
      className="flex flex-col gap-2"
    >
      {items.map((faq) => (
        <FaqRow
          key={faq.id}
          faq={faq}
          active={faq.id === activeId}
          onClick={() => onSelect(faq.id)}
        />
      ))}
    </motion.ul>
  )
}

function FaqRow({ faq, active, onClick }: { faq: Faq; active: boolean; onClick: () => void }) {
  const variantCount = faq.question_variants?.length ?? 0
  const statusTone = mapStatus(faq.status)
  return (
    <motion.li
      variants={{
        initial: { opacity: 0, y: 4 },
        animate: { opacity: 1, y: 0, transition: { duration: dur.base, ease: ease.out } },
      }}
    >
      <button
        type="button"
        onClick={onClick}
        className={cn(
          'group relative w-full overflow-hidden rounded-(--radius-card) text-left',
          'border bg-(--color-surface) transition-[background,border-color,transform] duration-[160ms] [transition-timing-function:var(--ease-out)]',
          'pl-4 pr-4 py-3.5',
          active
            ? 'border-(--color-primary)/40 bg-(--color-primary-soft)'
            : 'border-(--color-border) hover:bg-(--color-surface-2) hover:border-(--color-border)',
        )}
      >
        {/* 左侧状态色条：选中时变 primary，否则按状态分色 */}
        <span
          className={cn(
            'pointer-events-none absolute inset-y-0 left-0 w-[2px] transition-[width,background] duration-[160ms]',
            active
              ? 'w-[3px] bg-(--color-primary)'
              : statusBarClass(statusTone),
            'group-hover:w-[3px]',
          )}
        />

        <div className="flex items-start gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className="font-mono text-[10px] text-(--color-text-faint)">
                {faq.id.slice(0, 8)}
              </span>
              {faq.category && (
                <span className="text-[11px] text-(--color-text-faint)">
                  / {faq.category}
                </span>
              )}
            </div>
            <h3 className="mt-1 text-[14px] font-[500] text-(--color-text) truncate">
              {faq.question || '（未填问题）'}
            </h3>
            <p className="mt-1 line-clamp-1 text-[12px] text-(--color-text-muted)">
              {faq.answer || '（未填答案）'}
            </p>
            {faq.tags?.length > 0 && (
              <div className="mt-1.5 flex flex-wrap gap-1">
                {faq.tags.slice(0, 4).map((t) => (
                  <span
                    key={t}
                    className="rounded-(--radius-control) bg-(--color-surface-2) px-1.5 py-0.5 text-[10px] text-(--color-text-faint)"
                  >
                    {t}
                  </span>
                ))}
                {faq.tags.length > 4 && (
                  <span className="text-[10px] text-(--color-text-faint)">
                    +{faq.tags.length - 4}
                  </span>
                )}
              </div>
            )}
          </div>

          <div className="flex shrink-0 flex-col items-end gap-2 text-[11px]">
            <VariantDots count={variantCount} />
            <span className="text-(--color-text-faint)">
              {tr(faqStatusLabel, faq.status, faq.status)}
            </span>
            <StatusDot
              tone={mapEmbed(faq.embedding_status)}
              label={tr(embeddingStatusLabel, faq.embedding_status, '未索引')}
            />
          </div>
        </div>
      </button>
    </motion.li>
  )
}

function VariantDots({ count }: { count: number }) {
  if (!count) return <span className="text-(--color-text-faint)">无变体</span>
  const shown = Math.min(count, 5)
  return (
    <span className="inline-flex items-center gap-0.5" title={`${count} 个相似问法`}>
      {Array.from({ length: shown }).map((_, i) => (
        <span
          key={i}
          className="inline-block size-1.5 rounded-full bg-(--color-primary)/70"
        />
      ))}
      {count > shown && (
        <span className="ml-0.5 font-mono text-[10px] text-(--color-text-faint)">
          +{count - shown}
        </span>
      )}
    </span>
  )
}

function ListSkeleton() {
  return (
    <div className="flex flex-col gap-2">
      {Array.from({ length: 5 }).map((_, i) => (
        <Skeleton key={i} className="h-20 w-full" />
      ))}
    </div>
  )
}

function Empty({ children }: { children: React.ReactNode }) {
  return (
    <div className="surface rounded-(--radius-card) px-6 py-12 text-center text-[13px] text-(--color-text-muted)">
      {children}
    </div>
  )
}

function mapStatus(s: string): 'success' | 'warning' | 'muted' | 'danger' {
  if (s === 'usable') return 'success'
  if (s === 'needs_review' || s === 'draft') return 'warning'
  if (s === 'archived') return 'muted'
  return 'muted'
}
function statusBarClass(t: ReturnType<typeof mapStatus>) {
  switch (t) {
    case 'success':
      return 'bg-(--color-success)/60'
    case 'warning':
      return 'bg-(--color-warning)/60'
    case 'danger':
      return 'bg-(--color-danger)/60'
    default:
      return 'bg-(--color-border)'
  }
}
function mapEmbed(s?: string) {
  if (s === 'ready') return 'ready' as const
  if (s === 'failed') return 'failed' as const
  if (s === 'stale') return 'stale' as const
  return 'pending' as const
}
