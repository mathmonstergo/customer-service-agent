import * as DialogPrimitive from '@radix-ui/react-dialog'
import { motion } from 'framer-motion'
import { X } from 'lucide-react'
import { forwardRef, type ReactNode } from 'react'
import { cn } from '@/lib/cn'
import { spring } from '@/lib/motion'

export const Dialog = DialogPrimitive.Root
export const DialogTrigger = DialogPrimitive.Trigger
export const DialogPortal = DialogPrimitive.Portal
export const DialogClose = DialogPrimitive.Close

const Overlay = forwardRef<
  HTMLDivElement,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Overlay>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Overlay
    ref={ref}
    className={cn(
      'fixed inset-0 z-40 bg-black/60 backdrop-blur-[6px]',
      'data-[state=open]:animate-in data-[state=closed]:animate-out',
      'data-[state=open]:fade-in-0 data-[state=closed]:fade-out-0',
      className,
    )}
    {...props}
  />
))
Overlay.displayName = 'DialogOverlay'
export const DialogOverlay = Overlay

interface DialogContentProps extends React.ComponentPropsWithoutRef<typeof DialogPrimitive.Content> {
  closeOnEscape?: boolean
}

export const DialogContent = forwardRef<HTMLDivElement, DialogContentProps>(
  ({ className, children, ...props }, ref) => (
    <DialogPortal>
      <DialogOverlay />
      {/* aria-describedby={undefined}：对话框默认不提供 Radix Description，显式关掉"缺 Description"提示；
          放在 {...props} 前，消费方仍可自行传 aria-describedby 关联描述 */}
      <DialogPrimitive.Content ref={ref} asChild aria-describedby={undefined} {...props}>
        <motion.div
          initial={{ opacity: 0, scale: 0.96, y: 8 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.96, y: 8 }}
          transition={spring}
          className={cn(
            'fixed left-1/2 top-1/2 z-50 -translate-x-1/2 -translate-y-1/2',
            'w-full max-w-lg surface rounded-(--radius-drawer) p-6',
            'shadow-(--shadow-elevated)',
            className,
          )}
        >
          {children}
          <DialogPrimitive.Close
            className="absolute right-3 top-3 size-7 inline-flex items-center justify-center rounded-(--radius-control) text-(--color-text-muted) hover:bg-(--color-surface-2) hover:text-(--color-text) transition-colors"
            aria-label="关闭"
          >
            <X className="size-4" />
          </DialogPrimitive.Close>
        </motion.div>
      </DialogPrimitive.Content>
    </DialogPortal>
  ),
)
DialogContent.displayName = 'DialogContent'

export function DialogHeader({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn('mb-4 flex flex-col gap-1.5', className)}>{children}</div>
}
export function DialogTitle({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <DialogPrimitive.Title className={cn('text-[18px] leading-tight', className)}>
      {children}
    </DialogPrimitive.Title>
  )
}
export function DialogDescription({
  children,
  className,
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <DialogPrimitive.Description className={cn('text-[13px] text-(--color-text-muted)', className)}>
      {children}
    </DialogPrimitive.Description>
  )
}
export function DialogFooter({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn('mt-6 flex justify-end gap-2', className)}>{children}</div>
}
