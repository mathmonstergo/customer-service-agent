import { motion } from 'framer-motion'
import { Activity, AlertCircle, Database, FileWarning } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { cn } from '@/lib/cn'
import { dur, ease } from '@/lib/motion'

interface Stat {
  label: string
  value: number | string
  hint?: string
  icon: LucideIcon
  tone?: 'default' | 'warning' | 'danger' | 'success'
}

export function FaqStatsBar({
  total,
  needsReview,
  pendingEmbedding,
  failedEmbedding,
}: {
  total: number
  needsReview: number
  pendingEmbedding: number
  failedEmbedding: number
}) {
  const stats: Stat[] = [
    { label: '知识总数', value: total, icon: Database, hint: '正式 FAQ' },
    { label: '待复核', value: needsReview, icon: AlertCircle, tone: needsReview > 0 ? 'warning' : 'default', hint: '需要人工确认' },
    { label: '未索引', value: pendingEmbedding, icon: Activity, hint: '尚未生成向量' },
    { label: '索引失败', value: failedEmbedding, icon: FileWarning, tone: failedEmbedding > 0 ? 'danger' : 'default', hint: '需要重新生成' },
  ]
  return (
    <div className="grid shrink-0 grid-cols-4 gap-2 px-6 pt-4">
      {stats.map((s, i) => (
        <motion.div
          key={s.label}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: dur.base, ease: ease.out, delay: i * 0.04 }}
          className="surface relative overflow-hidden rounded-(--radius-card) px-4 py-3"
        >
          {/* 角落淡色装饰，做点 atmosphere */}
          <s.icon className="pointer-events-none absolute -bottom-3 -right-3 size-16 text-(--color-text-faint) opacity-[0.06]" />
          <div className="flex items-baseline gap-2">
            <span
              className={cn(
                'font-mono text-[26px] leading-none tracking-tight',
                s.tone === 'warning' && 'text-(--color-warning)',
                s.tone === 'danger' && 'text-(--color-danger)',
                s.tone === 'success' && 'text-(--color-success)',
                !s.tone && 'text-(--color-text)',
              )}
            >
              {s.value}
            </span>
          </div>
          <div className="mt-1 text-[11px] uppercase tracking-[0.14em] text-(--color-text-faint)">
            {s.label}
          </div>
          {s.hint && (
            <div className="mt-0.5 text-[11px] text-(--color-text-faint)/70">{s.hint}</div>
          )}
        </motion.div>
      ))}
    </div>
  )
}
