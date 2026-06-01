import { cva, type VariantProps } from 'class-variance-authority'
import type { HTMLAttributes } from 'react'
import { cn } from '@/lib/cn'

const badgeVariants = cva(
  'inline-flex items-center gap-1 rounded-(--radius-control) px-1.5 py-0.5 text-[11px] font-[500] leading-none tracking-wide',
  {
    variants: {
      tone: {
        muted: 'bg-(--color-surface-2) text-(--color-text-muted) border border-(--color-border)',
        primary: 'bg-(--color-primary-soft) text-(--color-primary-hi) border border-(--color-primary)/30',
        success: 'bg-(--color-success)/12 text-(--color-success) border border-(--color-success)/30',
        warning: 'bg-(--color-warning)/12 text-(--color-warning) border border-(--color-warning)/30',
        danger: 'bg-(--color-danger-soft) text-(--color-danger) border border-(--color-danger)/30',
      },
    },
    defaultVariants: { tone: 'muted' },
  },
)

export interface BadgeProps
  extends HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, tone, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ tone }), className)} {...props} />
}
