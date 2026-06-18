import { cn } from '@/lib/cn'
import { TONE_COLOR, type DotTone } from './status-dot-utils'

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

export type { DotTone }
