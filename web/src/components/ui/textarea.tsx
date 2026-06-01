import { forwardRef, type TextareaHTMLAttributes } from 'react'
import { cn } from '@/lib/cn'

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, ...props }, ref) => (
    <textarea
      ref={ref}
      className={cn(
        'w-full rounded-(--radius-control) bg-(--color-surface-2) px-3 py-2 text-[13px] text-(--color-text)',
        'border border-(--color-border) min-h-24 resize-y',
        'placeholder:text-(--color-text-faint)',
        'transition-[background,border-color] duration-[120ms] [transition-timing-function:var(--ease-out)]',
        'hover:bg-(--color-surface-3)',
        'focus:outline-none focus:border-(--color-primary)/60',
        'font-mono',
        className,
      )}
      {...props}
    />
  ),
)
Textarea.displayName = 'Textarea'
