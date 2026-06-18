import * as PopoverPrimitive from '@radix-ui/react-popover'
import { forwardRef } from 'react'
import { cn } from '@/lib/cn'

export function Popover(props: React.ComponentPropsWithoutRef<typeof PopoverPrimitive.Root>) {
  return <PopoverPrimitive.Root {...props} />
}

export function PopoverTrigger(props: React.ComponentPropsWithoutRef<typeof PopoverPrimitive.Trigger>) {
  return <PopoverPrimitive.Trigger {...props} />
}

export function PopoverAnchor(props: React.ComponentPropsWithoutRef<typeof PopoverPrimitive.Anchor>) {
  return <PopoverPrimitive.Anchor {...props} />
}

export const PopoverContent = forwardRef<
  HTMLDivElement,
  React.ComponentPropsWithoutRef<typeof PopoverPrimitive.Content>
>(({ className, sideOffset = 6, align = 'end', ...props }, ref) => (
  <PopoverPrimitive.Portal>
    <PopoverPrimitive.Content
      ref={ref}
      sideOffset={sideOffset}
      align={align}
      className={cn(
        'z-[60] surface rounded-(--radius-control) p-1 text-[13px] text-(--color-text)',
        'shadow-(--shadow-elevated)',
        'data-[state=open]:animate-in data-[state=closed]:animate-out fade-in-0 fade-out-0',
        className,
      )}
      {...props}
    />
  </PopoverPrimitive.Portal>
))
PopoverContent.displayName = 'PopoverContent'
