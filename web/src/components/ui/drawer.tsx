import * as DialogPrimitive from '@radix-ui/react-dialog'
import { motion } from 'framer-motion'
import { X } from 'lucide-react'
import { forwardRef, type ReactNode } from 'react'
import { cn } from '@/lib/cn'
import { spring } from '@/lib/motion'

export const Drawer = DialogPrimitive.Root
export const DrawerTrigger = DialogPrimitive.Trigger
export const DrawerClose = DialogPrimitive.Close

interface DrawerContentProps extends React.ComponentPropsWithoutRef<typeof DialogPrimitive.Content> {
  width?: number | string
}

export const DrawerContent = forwardRef<HTMLDivElement, DrawerContentProps>(
  ({ className, children, width = 720, ...props }, ref) => (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-black/60 backdrop-blur-[6px] data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=open]:fade-in-0 data-[state=closed]:fade-out-0" />
      <DialogPrimitive.Content ref={ref} asChild {...props}>
        <motion.div
          initial={{ x: 20, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          exit={{ x: 20, opacity: 0 }}
          transition={spring}
          style={{ width }}
          className={cn(
            'fixed right-3 top-3 bottom-3 z-50 max-w-[calc(100vw-1.5rem)]',
            'surface rounded-(--radius-drawer) shadow-(--shadow-elevated)',
            'flex flex-col overflow-hidden',
            className,
          )}
        >
          {children}
          <DialogPrimitive.Close
            className="absolute right-4 top-4 size-7 inline-flex items-center justify-center rounded-(--radius-control) text-(--color-text-muted) hover:bg-(--color-surface-2) hover:text-(--color-text) transition-colors"
            aria-label="关闭"
          >
            <X className="size-4" />
          </DialogPrimitive.Close>
        </motion.div>
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  ),
)
DrawerContent.displayName = 'DrawerContent'

export function DrawerHeader({
  children,
  className,
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <div
      className={cn(
        'flex shrink-0 items-start justify-between gap-4 border-b border-(--color-border) px-6 py-5',
        className,
      )}
    >
      {children}
    </div>
  )
}
export function DrawerTitle({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <DialogPrimitive.Title className={cn('text-[16px] leading-tight', className)}>
      {children}
    </DialogPrimitive.Title>
  )
}
export function DrawerBody({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn('flex-1 overflow-y-auto scroll-thin px-6 py-5', className)}>{children}</div>
  )
}
export function DrawerFooter({
  children,
  className,
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <div
      className={cn(
        'flex shrink-0 items-center justify-end gap-2 border-t border-(--color-border) px-6 py-4',
        className,
      )}
    >
      {children}
    </div>
  )
}
