// 中间消息流：仿 ChatGPT/Claude 的极简两栏内会话。
// 用户气泡（右侧灰底）+ 助手回答（左侧无气泡，markdown 渲染）+ 上方 inline 状态行 / 完成后折叠面板。
import { useEffect, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  Copy,
  FileText,
  AlertTriangle,
  Loader2,
  ChevronRight,
  Sparkles,
  CheckCircle2,
} from 'lucide-react'
import { toast } from '@/components/ui/toast'
import { cn } from '@/lib/cn'
import { ease, dur } from '@/lib/motion'
import { confidenceLabel, intentLabel, tr } from '@/lib/labels'
import { useAssistant, type ChatMessage } from '@/store/assistant'
import type { AssistantSource } from '@/api/schemas'
import type { AssistantStepEvent } from '@/lib/sse-assistant'

export function MessageStream({ conversationId }: { conversationId: string }) {
  const messages = useAssistant((s) => s.conversations[conversationId]?.messages ?? [])
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    const last = messages[messages.length - 1]
    if (!last) return
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 160
    if (nearBottom || last.role === 'user') {
      el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
    }
  }, [messages])

  if (messages.length === 0) {
    return <EmptyState />
  }

  return (
    <div ref={scrollRef} className="h-full overflow-y-auto scroll-thin">
      <div className="mx-auto flex max-w-3xl flex-col gap-7 px-6 py-8">
        <AnimatePresence initial={false}>
          {messages.map((m) => (
            <MessageBubble key={m.id} msg={m} />
          ))}
        </AnimatePresence>
      </div>
    </div>
  )
}

function EmptyState() {
  return (
    <div className="flex h-full items-center justify-center px-6">
      <div className="max-w-md text-center">
        <Sparkles className="mx-auto mb-3 size-7 text-(--color-primary-hi)" />
        <div className="text-[15px] text-(--color-text)">从一个问题开始</div>
        <div className="mt-2 text-[12px] leading-relaxed text-(--color-text-faint)">
          助手会先做混合召回（向量 + 关键词）→ 重排 → 流式生成回答
          <br />
          完成后右上角可打开「流程详情」查看每一步耗时与命中切片
        </div>
        <div className="mt-4 inline-flex items-center gap-2 text-[11px] text-(--color-text-faint)">
          <Kbd>Enter</Kbd>
          <span>发送</span>
          <span className="mx-1 text-(--color-border)">·</span>
          <Kbd>Shift</Kbd>+<Kbd>Enter</Kbd>
          <span>换行</span>
          <span className="mx-1 text-(--color-border)">·</span>
          <Kbd>Esc</Kbd>
          <span>停止</span>
        </div>
      </div>
    </div>
  )
}

function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded-(--radius-control) bg-(--color-surface-2) px-1.5 py-0.5 font-mono text-[10px]">
      {children}
    </span>
  )
}

// 把后端 summary 中的英文 intent / confidence 翻译成中文，让 inline 状态条更可读。
// 形如 "sensitive_or_forbidden / high" → "敏感词拦截 / 高"。
function prettySummary(step: AssistantStepEvent | undefined): string {
  if (!step) return ''
  const raw = step.summary || ''
  if (step.step_id === 'intent_detection' && raw.includes('/')) {
    const [intent, conf] = raw.split('/').map((s) => s.trim())
    const intentZh = tr(intentLabel, intent, intent)
    const confZh = tr(confidenceLabel, conf, conf)
    return `${intentZh} · 置信 ${confZh}`
  }
  return raw
}

function MessageBubble({ msg }: { msg: ChatMessage }) {
  if (msg.role === 'user') {
    return (
      <motion.div
        initial={{ opacity: 0, y: 4 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: dur.base, ease: ease.out }}
        className="flex justify-end"
      >
        <div className="max-w-[80%] rounded-2xl bg-(--color-surface-2) px-4 py-2.5 text-[14px] text-(--color-text)">
          <div className="whitespace-pre-wrap break-words leading-[1.7]">{msg.content}</div>
        </div>
      </motion.div>
    )
  }
  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: dur.base, ease: ease.out }}
      className="flex flex-col gap-2"
    >
      {msg.steps && msg.steps.length > 0 && <ThinkingPanel msg={msg} />}
      {msg.content || !msg.streaming ? (
        <div className="text-[14px] leading-[1.75] text-(--color-text)">
          <MarkdownView text={msg.content} streaming={!!msg.streaming} />
        </div>
      ) : (
        <BlinkingDots />
      )}
      {msg.error && (
        <div className="flex items-start gap-1.5 rounded-(--radius-control) border border-(--color-danger)/30 bg-(--color-danger-soft) px-2.5 py-1.5 text-[12px] text-(--color-danger)">
          <AlertTriangle className="mt-px size-3.5 shrink-0" />
          <span>{msg.error}</span>
        </div>
      )}
      {msg.sources && msg.sources.length > 0 && <SourcesPreview sources={msg.sources} />}
      {!msg.streaming && msg.content && <AssistantActions msg={msg} />}
    </motion.div>
  )
}

function BlinkingDots() {
  return (
    <div className="flex items-center gap-1.5 py-1">
      <span className="size-1.5 animate-pulse rounded-full bg-(--color-primary)" />
      <span className="size-1.5 animate-pulse rounded-full bg-(--color-primary) [animation-delay:200ms]" />
      <span className="size-1.5 animate-pulse rounded-full bg-(--color-primary) [animation-delay:400ms]" />
    </div>
  )
}

// 流式期间："步骤链"逐条入场（已完成步骤留在上面淡化，当前步骤高亮 + spinner），
// 这样即使前面几步只用了几十毫秒也能被用户看到。完成后折叠成"已完成 X 步"摘要条，可展开查看。
function StepIcon({ status, isActive }: { status: string; isActive: boolean }) {
  if (status === 'failed') return <AlertTriangle className="size-3.5 shrink-0 text-(--color-danger)" />
  if (isActive) return <Loader2 className="size-3.5 shrink-0 animate-spin text-(--color-primary-hi)" />
  return <CheckCircle2 className="size-3.5 shrink-0 text-(--color-success)" />
}

function ThinkingPanel({ msg }: { msg: ChatMessage }) {
  const steps = msg.steps || []
  const [open, setOpen] = useState(false)
  const running = msg.streaming
  const activeIdx = steps.findIndex((s) => s.status === 'running')

  if (running && steps.length > 0) {
    return (
      <motion.ul layout className="flex flex-col gap-1 text-[12px]">
        <AnimatePresence initial={false}>
          {steps.map((s, i) => {
            // active = 正在跑的那条；如果没有 running 状态（每步发完都 completed），把最后一条视为"进行中等待下一步"
            const isActive =
              s.status === 'running' || (activeIdx < 0 && i === steps.length - 1)
            return (
              <motion.li
                key={s.step_id}
                layout
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                transition={{ duration: dur.base, ease: ease.out }}
                className="flex items-center gap-2"
              >
                <StepIcon status={s.status} isActive={isActive} />
                <span
                  className={cn(
                    'min-w-0 flex-1 truncate',
                    isActive
                      ? 'text-(--color-text)'
                      : 'text-(--color-text-muted) opacity-80',
                  )}
                >
                  <span className={isActive ? 'animate-pulse' : ''}>
                    {s.title || s.step_id}
                    {isActive && '…'}
                  </span>
                  {prettySummary(s) && (
                    <span className="ml-2 text-(--color-text-faint)">
                      {prettySummary(s)}
                    </span>
                  )}
                </span>
                {typeof s.duration_ms === 'number' && s.duration_ms > 0 && !isActive && (
                  <span className="shrink-0 font-mono text-[10px] text-(--color-text-faint)">
                    {s.duration_ms}ms
                  </span>
                )}
              </motion.li>
            )
          })}
        </AnimatePresence>
      </motion.ul>
    )
  }

  // 流式开始但还没收到任何 step：纯文字"准备中…"
  if (running) {
    return (
      <div className="flex items-center gap-2 text-[12px] text-(--color-text-muted)">
        <Loader2 className="size-3.5 animate-spin text-(--color-primary-hi)" />
        <span className="animate-pulse">准备中…</span>
      </div>
    )
  }

  const total = steps.reduce((sum, s) => sum + (s.duration_ms || 0), 0)
  const label = `已完成 ${steps.length} 步 · ${(total / 1000).toFixed(1)}s`

  return (
    <div className="rounded-(--radius-control) border border-(--color-border-soft) bg-(--color-surface)">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={cn(
          'flex w-full items-center gap-2 px-3 py-1.5 text-left text-[12px]',
          'text-(--color-text-muted) hover:text-(--color-text)',
          'transition-colors',
        )}
      >
        <CheckCircle2 className="size-3.5 text-(--color-success)" />
        <span className="flex-1">{label}</span>
        <ChevronRight
          className={cn('size-3.5 transition-transform duration-150', open && 'rotate-90')}
        />
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: dur.base, ease: ease.out }}
            className="overflow-hidden"
          >
            <ol className="flex flex-col gap-0.5 border-t border-(--color-border-soft) px-3 py-2 text-[12px]">
              {steps.map((s, i) => (
                <li key={`${s.step_id}-${i}`} className="flex items-start gap-2 py-1">
                  <span
                    className={cn(
                      'mt-1 inline-block size-1.5 shrink-0 rounded-full',
                      s.status === 'failed'
                        ? 'bg-(--color-danger)'
                        : s.status === 'running'
                          ? 'bg-(--color-primary) animate-pulse'
                          : 'bg-(--color-success)',
                    )}
                  />
                  <span className="min-w-0 flex-1">
                    <span className="text-(--color-text)">{s.title || s.step_id}</span>
                    {prettySummary(s) && (
                      <span className="ml-2 text-(--color-text-muted)">{prettySummary(s)}</span>
                    )}
                  </span>
                  {typeof s.duration_ms === 'number' && (
                    <span className="shrink-0 font-mono text-[10px] text-(--color-text-faint)">
                      {s.duration_ms}ms
                    </span>
                  )}
                </li>
              ))}
            </ol>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

// 助手回答用 react-markdown 渲染，自带 GFM（表格 / 任务列表 / 删除线 / 自动链接）。
// 流式期间末尾追加一个 1.6em 的脉冲指示点。
function MarkdownView({ text, streaming }: { text: string; streaming: boolean }) {
  return (
    <div className={cn('markdown-body', streaming && 'is-streaming')}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ node: _node, ...props }) => {
            void _node
            return (
              <a
                {...props}
                target="_blank"
                rel="noopener noreferrer"
                className="text-(--color-primary-hi) underline underline-offset-2 hover:text-(--color-primary)"
              />
            )
          },
          code: ({ inline, className, children, ...props }: {
            inline?: boolean
            className?: string
            children?: React.ReactNode
          } & React.HTMLAttributes<HTMLElement>) => {
            if (inline) {
              return (
                <code
                  className="rounded-(--radius-control) bg-(--color-surface-2) px-1 py-0.5 font-mono text-[12px]"
                  {...props}
                >
                  {children}
                </code>
              )
            }
            return (
              <code className={cn('font-mono text-[12.5px]', className)} {...props}>
                {children}
              </code>
            )
          },
          pre: ({ children, ...props }) => (
            <pre
              className="overflow-x-auto scroll-thin rounded-(--radius-control) border border-(--color-border) bg-(--color-surface) p-3"
              {...props}
            >
              {children}
            </pre>
          ),
        }}
      >
        {text}
      </ReactMarkdown>
      {streaming && (
        <span className="ml-1 inline-block size-2 translate-y-[-1px] animate-pulse rounded-full bg-(--color-primary)" />
      )}
    </div>
  )
}

function AssistantActions({ msg }: { msg: ChatMessage }) {
  const setDebugDrawerOpen = useAssistant((s) => s.setDebugDrawerOpen)
  return (
    <div className="flex items-center gap-1 pt-1">
      <button
        type="button"
        onClick={() => {
          navigator.clipboard.writeText(msg.content)
          toast.success('已复制回答')
        }}
        className="inline-flex items-center gap-1 rounded-(--radius-control) px-2 py-1 text-[11px] text-(--color-text-faint) hover:bg-(--color-surface-2) hover:text-(--color-text-muted)"
      >
        <Copy className="size-3" />
        复制
      </button>
      {msg.sources && msg.sources.length > 0 && (
        <button
          type="button"
          onClick={() => setDebugDrawerOpen(true)}
          className="inline-flex items-center gap-1 rounded-(--radius-control) px-2 py-1 text-[11px] text-(--color-text-faint) hover:bg-(--color-surface-2) hover:text-(--color-text-muted)"
        >
          <FileText className="size-3" />
          查看 {msg.sources.length} 条来源
        </button>
      )}
    </div>
  )
}

// 来源 chips：按 source_type 分组——FAQ 全部合并成"FAQ × N"，文档按 source_title 分组成"文件名 × N"。
// parent_context 来源也算在该文档的命中数里（它本质就是被命中切片的父切片，归到同文档）。
function SourcesPreview({ sources }: { sources: AssistantSource[] }) {
  const setDebugDrawerOpen = useAssistant((s) => s.setDebugDrawerOpen)
  if (!sources.length) return null

  // 分组：faq 用单一 key，document 按 source_title 分桶
  const groups = new Map<string, { label: string; isFaq: boolean; count: number }>()
  for (const src of sources) {
    const isFaq = src.source_type === 'faq'
    const key = isFaq ? '__faq__' : src.source_title || src.source_id || '未命名文档'
    const label = isFaq ? 'FAQ' : src.source_title || '未命名文档'
    const existing = groups.get(key)
    if (existing) existing.count += 1
    else groups.set(key, { label, isFaq, count: 1 })
  }
  // 排序：FAQ 在前，文档按命中数从多到少
  const entries = Array.from(groups.values()).sort((a, b) => {
    if (a.isFaq !== b.isFaq) return a.isFaq ? -1 : 1
    return b.count - a.count
  })

  return (
    <div className="flex flex-wrap items-center gap-1 pt-1">
      {entries.map((g) => (
        <button
          key={g.label}
          type="button"
          onClick={() => setDebugDrawerOpen(true)}
          className={cn(
            'inline-flex max-w-[200px] items-center gap-1 rounded-(--radius-control) px-1.5 py-0.5 text-[11px]',
            'transition-colors hover:bg-(--color-surface-3)',
            g.isFaq
              ? 'bg-(--color-primary-soft) text-(--color-primary-hi)'
              : 'bg-(--color-surface-2) text-(--color-text-muted)',
          )}
          title={`${g.label}（${g.count} 条）`}
        >
          <FileText className="size-3 shrink-0 opacity-70" />
          <span className="min-w-0 truncate">{g.label}</span>
          <span className="shrink-0 font-mono opacity-80">×{g.count}</span>
        </button>
      ))}
    </div>
  )
}
