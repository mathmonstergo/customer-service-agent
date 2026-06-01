import { forwardRef, type InputHTMLAttributes } from 'react'
import { cn } from '@/lib/cn'

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={cn(
        'h-8 w-full rounded-(--radius-control) bg-(--color-surface-2) px-2.5 text-[13px] text-(--color-text)',
        'border border-(--color-border)',
        'placeholder:text-(--color-text-faint)',
        'transition-[background,border-color] duration-[120ms] [transition-timing-function:var(--ease-out)]',
        'hover:bg-(--color-surface-3)',
        'focus:outline-none focus:border-(--color-primary)/60 focus:bg-(--color-surface-2)',
        'disabled:opacity-50 disabled:pointer-events-none',
        className,
      )}
      {...props}
    />
  ),
)
Input.displayName = 'Input'
