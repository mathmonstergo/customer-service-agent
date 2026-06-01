import { cn } from '@/lib/cn'

export type DotTone = 'pending' | 'ready' | 'warning' | 'stale' | 'failed' | 'muted'

const TONE_COLOR: Record<DotTone, string> = {
  pending: 'bg-(--color-warning)',
  ready: 'bg-(--color-success)',
  warning: 'bg-(--color-warning)',
  stale: 'bg-(--color-text-faint)',
  failed: 'bg-(--color-danger)',
  muted: 'bg-(--color-text-faint)',
}

const ANIMATED: DotTone[] = ['pending']

export function StatusDot({
  tone,
  className,
  label,
}: {
  tone: DotTone
  className?: string
  label?: string
}) {
  return (
    <span className={cn('inline-flex items-center gap-1.5 text-[12px] text-(--color-text-muted)', className)}>
      <span
        className={cn(
          'inline-block size-1.5 rounded-full',
          TONE_COLOR[tone],
          ANIMATED.includes(tone) && 'pulse-dot',
        )}
      />
      {label}
    </span>
  )
}
