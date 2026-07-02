import type { ReactElement, ReactNode } from 'react'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/cn'

// 文档页统一 hover 提示，关键约束是替代浏览器默认 title 浮层。
export function HoverTooltip({
  content,
  children,
  side = 'bottom',
  className,
}: {
  content: ReactNode
  children: ReactNode
  side?: 'top' | 'right' | 'bottom' | 'left'
  className?: string
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>{children}</TooltipTrigger>
      <TooltipContent side={side} className={cn('max-w-[280px]', className)}>
        {content}
      </TooltipContent>
    </Tooltip>
  )
}

// 按钮类 hover 触发器，关键约束是禁用按钮用外层 span 承接 hover 事件。
export function HoverTooltipTrigger({
  content,
  children,
  disabled = false,
  side = 'bottom',
}: {
  content: ReactNode
  children: ReactElement
  disabled?: boolean
  side?: 'top' | 'right' | 'bottom' | 'left'
}) {
  return (
    <HoverTooltip content={content} side={side}>
      {disabled ? <span className="inline-flex">{children}</span> : children}
    </HoverTooltip>
  )
}
