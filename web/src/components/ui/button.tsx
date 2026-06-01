import { Slot } from '@radix-ui/react-slot'
import { cva, type VariantProps } from 'class-variance-authority'
import { forwardRef, type ButtonHTMLAttributes } from 'react'
import { cn } from '@/lib/cn'

const buttonVariants = cva(
  [
    'inline-flex items-center justify-center gap-1.5 whitespace-nowrap select-none',
    'rounded-(--radius-control) text-[13px] font-[500]',
    'transition-[background,border-color,color,transform] duration-[120ms] [transition-timing-function:var(--ease-out)]',
    'active:scale-[0.985]',
    'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-(--color-primary)',
    'disabled:opacity-50 disabled:pointer-events-none',
  ],
  {
    variants: {
      variant: {
        default:
          'bg-(--color-surface-2) text-(--color-text) border border-(--color-border) hover:bg-(--color-surface-3) hover:border-(--color-border)',
        primary:
          'bg-(--color-primary) text-white border border-(--color-primary) hover:bg-(--color-primary-hi) hover:border-(--color-primary-hi)',
        ghost:
          'bg-transparent text-(--color-text-muted) border border-transparent hover:bg-(--color-surface-2) hover:text-(--color-text)',
        outline:
          'bg-transparent text-(--color-text) border border-(--color-border) hover:bg-(--color-surface-2)',
        danger:
          'bg-transparent text-(--color-danger) border border-(--color-danger)/40 hover:bg-(--color-danger-soft) hover:border-(--color-danger)',
        link:
          'bg-transparent text-(--color-primary-hi) border-none hover:underline underline-offset-2',
      },
      size: {
        sm: 'h-7 px-2 text-[12px]',
        default: 'h-8 px-3',
        lg: 'h-10 px-4 text-[14px]',
        icon: 'h-8 w-8',
      },
    },
    defaultVariants: { variant: 'default', size: 'default' },
  },
)

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : 'button'
    return (
      <Comp ref={ref} className={cn(buttonVariants({ variant, size }), className)} {...props} />
    )
  },
)
Button.displayName = 'Button'

export { buttonVariants }
