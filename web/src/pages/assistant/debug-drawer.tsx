// 右侧 Debug 抽屉：显示当前会话最近一条助手消息的完整流程（step list + 命中切片明细）。
// 默认关闭；从顶栏的「流程详情」按钮或助手气泡上的「查看 N 条来源」唤起。
import { useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  FileText,
  Loader2,
} from 'lucide-react'
import {
  Drawer,
  DrawerBody,
  DrawerContent,
  DrawerHeader,
  DrawerTitle,
} from '@/components/ui/drawer'
import { cn } from '@/lib/cn'
import { confidenceLabel, intentLabel, tr } from '@/lib/labels'
import { dur, ease } from '@/lib/motion'
import { useAssistant, type ChatMessage } from '@/store/assistant'
import type { AssistantSource } from '@/api/schemas'
import type { AssistantStepEvent } from '@/lib/sse-assistant'

export function DebugDrawer({
  open,
  onOpenChange,
  conversationId,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  conversationId: string
}) {
  const conv = useAssistant((s) => s.conversations[conversationId])
  const lastAsst = conv?.messages.slice().reverse().find((m) => m.role === 'assistant')

  return (
    <Drawer open={open} onOpenChange={onOpenChange}>
      <AnimatePresence>
        {open && (
          <DrawerContent width={560}>
            <DrawerHeader>
              <div>
                <DrawerTitle>流程详情</DrawerTitle>
                <p className="mt-1 text-[12px] text-(--color-text-muted)">
                  最近一次回答的 RAG 链路 · 步骤耗时 · 命中切片
                </p>
              </div>
            </DrawerHeader>
            <DrawerBody>
              {!lastAsst ? (
                <EmptyState />
              ) : (
                <div className="flex flex-col gap-6">
                  <StepsBlock msg={lastAsst} />
                  <SourcesBlock sources={lastAsst.sources || []} />
                </div>
              )}
            </DrawerBody>
          </DrawerContent>
        )}
      </AnimatePresence>
    </Drawer>
  )
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-12 text-center">
      <Activity className="size-6 text-(--color-text-faint)" />
      <div className="text-[13px] text-(--color-text-muted)">还没有问答记录</div>
      <div className="text-[11px] text-(--color-text-faint)">发送一个问题后这里会展示完整流程</div>
    </div>
  )
}

function prettySummary(step: AssistantStepEvent): string {
  const raw = step.summary || ''
  if (step.step_id === 'intent_detection' && raw.includes('/')) {
    const [intent, conf] = raw.split('/').map((s) => s.trim())
    return `${tr(intentLabel, intent, intent)} · 置信 ${tr(confidenceLabel, conf, conf)}`
  }
  return raw
}

function StepsBlock({ msg }: { msg: ChatMessage }) {
  const steps = msg.steps || []
  return (
    <section>
      <SectionTitle title="处理步骤" count={steps.length} />
      {steps.length === 0 ? (
        <div className="text-[12px] text-(--color-text-faint)">尚无步骤</div>
      ) : (
        <ol className="flex flex-col gap-2">
          {steps.map((s, i) => (
            <li
              key={`${s.step_id}-${i}`}
              className="rounded-(--radius-control) border border-(--color-border-soft) bg-(--color-surface) px-3 py-2"
            >
              <div className="flex items-center gap-2 text-[12px]">
                {s.status === 'failed' ? (
                  <AlertTriangle className="size-3.5 text-(--color-danger)" />
                ) : s.status === 'running' ? (
                  <Loader2 className="size-3.5 animate-spin text-(--color-primary-hi)" />
                ) : (
                  <CheckCircle2 className="size-3.5 text-(--color-success)" />
                )}
                <span className="text-(--color-text)">{s.title || s.step_id}</span>
                <span className="ml-auto font-mono text-[10px] text-(--color-text-faint)">
                  {typeof s.duration_ms === 'number' ? `${s.duration_ms}ms` : ''}
                </span>
              </div>
              {prettySummary(s) && (
                <div className="mt-1 text-[12px] text-(--color-text-muted)">{prettySummary(s)}</div>
              )}
              <ExtraTags step={s} />
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}

function ExtraTags({ step }: { step: AssistantStepEvent }) {
  const tags: string[] = []
  if (step.analysis && typeof step.analysis === 'object') {
    const intentRaw = (step.analysis as { intent?: string }).intent
    const conf = (step.analysis as { confidence?: number | string }).confidence
    if (intentRaw) tags.push(`意图=${tr(intentLabel, intentRaw, intentRaw)}`)
    if (conf !== undefined) {
      const confZh = typeof conf === 'string' ? tr(confidenceLabel, conf, String(conf)) : String(conf)
      tags.push(`置信=${confZh}`)
    }
    const rewrite = (step.analysis as { query_rewrite?: string }).query_rewrite
    if (rewrite) tags.push(`改写="${rewrite}"`)
  }
  if (Array.isArray(step.documents) && step.documents.length > 0) {
    tags.push(`命中=${step.documents.length}`)
  }
  if (typeof step.top_k === 'number') tags.push(`top_k=${step.top_k}`)
  if (typeof step.vector_count === 'number') tags.push(`向量=${step.vector_count}`)
  if (typeof step.keyword_count === 'number') tags.push(`关键词=${step.keyword_count}`)
  if (typeof step.dimensions === 'number') tags.push(`维度=${step.dimensions}`)
  if (tags.length === 0) return null
  return (
    <div className="mt-1.5 flex flex-wrap gap-1">
      {tags.map((t) => (
        <span
          key={t}
          className="rounded-(--radius-control) bg-(--color-surface-2) px-1.5 py-0.5 font-mono text-[10px] text-(--color-text-muted)"
        >
          {t}
        </span>
      ))}
    </div>
  )
}

function SourcesBlock({ sources }: { sources: AssistantSource[] }) {
  return (
    <section>
      <SectionTitle title="命中切片" count={sources.length} />
      {sources.length === 0 ? (
        <div className="text-[12px] text-(--color-text-faint)">未检索到来源</div>
      ) : (
        <div className="flex flex-col gap-2">
          {sources.map((src, i) => (
            <SourceCard key={(src.chunk_id as string) || i} src={src} index={i} />
          ))}
        </div>
      )}
    </section>
  )
}

function SourceCard({ src, index }: { src: AssistantSource; index: number }) {
  const [expanded, setExpanded] = useState(false)
  const isFaq = src.source_type === 'faq'
  // 标题：FAQ 显示 question；文档显示 source_title（文件名）
  const title =
    src.source_title ||
    src.title ||
    (isFaq ? src.question : undefined) ||
    `来源 ${index + 1}`
  // 正文：document 用 content，FAQ 用 answer（fallback content / text）
  const fullText =
    (isFaq ? src.answer : undefined) ||
    src.content ||
    src.text ||
    ''
  const parentText = (src.metadata?.parent_content as string | undefined) || ''
  const score = typeof src.score === 'number' ? src.score : undefined
  const channels = Array.isArray(src.retrieval_channels) ? src.retrieval_channels : []
  const page =
    typeof src.page_start === 'number'
      ? src.page_start
      : (src.metadata?.page_start as number | undefined)
  const hasMore = fullText.length > 200 || !!parentText

  return (
    <article
      className={cn(
        'rounded-(--radius-control) border border-(--color-border) bg-(--color-surface)',
        'transition-colors',
        hasMore && 'cursor-pointer hover:border-(--color-primary)/30',
      )}
      onClick={() => hasMore && setExpanded((v) => !v)}
    >
      <div className="flex items-center gap-1.5 px-3 py-2 text-[12px]">
        {channels.map((c) => (
          <span
            key={c}
            className={cn(
              'shrink-0 rounded-(--radius-control) px-1.5 py-0.5 font-mono text-[10px]',
              c === 'parent_context'
                ? 'bg-(--color-warning)/15 text-(--color-warning)'
                : 'bg-(--color-surface-2) text-(--color-text-muted)',
            )}
          >
            {c}
          </span>
        ))}
        <span
          className={cn(
            'shrink-0 rounded-(--radius-control) px-1.5 py-0.5 font-mono text-[10px]',
            isFaq
              ? 'bg-(--color-primary-soft) text-(--color-primary-hi)'
              : 'bg-(--color-surface-2) text-(--color-text-muted)',
          )}
        >
          {isFaq ? 'FAQ' : '文档'}
        </span>
        <FileText className="size-3.5 shrink-0 text-(--color-text-faint)" />
        <span className="min-w-0 flex-1 truncate text-(--color-text)" title={title}>
          {title}
        </span>
        {typeof page === 'number' && (
          <span className="shrink-0 font-mono text-[10px] text-(--color-text-faint)">
            p.{page}
          </span>
        )}
        {score !== undefined && (
          <span className="shrink-0 font-mono text-[10px] text-(--color-text-faint)">
            {score.toFixed(3)}
          </span>
        )}
        {hasMore && (
          <ChevronDown
            className={cn(
              'size-3.5 shrink-0 text-(--color-text-faint) transition-transform',
              expanded && 'rotate-180',
            )}
          />
        )}
      </div>
      {(fullText || parentText) && (
        <AnimatePresence initial={false} mode="wait">
          {expanded ? (
            <motion.div
              key="full"
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: dur.base, ease: ease.out }}
              className="overflow-hidden"
            >
              {isFaq && src.question && (
                <div className="border-t border-(--color-border-soft) px-3 py-2 text-[12px] leading-[1.7]">
                  <div className="mb-1 text-[10px] uppercase tracking-wider text-(--color-text-faint)">
                    问题
                  </div>
                  <div className="text-(--color-text) whitespace-pre-wrap break-words">
                    {src.question}
                  </div>
                </div>
              )}
              {fullText && (
                <div className="border-t border-(--color-border-soft) px-3 py-2 text-[12px] leading-[1.7]">
                  {isFaq && (
                    <div className="mb-1 text-[10px] uppercase tracking-wider text-(--color-text-faint)">
                      答案
                    </div>
                  )}
                  <div className="text-(--color-text-muted) whitespace-pre-wrap break-words">
                    {fullText}
                  </div>
                </div>
              )}
              {parentText && (
                <div className="border-t border-(--color-border-soft) px-3 py-2 text-[12px] leading-[1.7]">
                  <div className="mb-1 text-[10px] uppercase tracking-wider text-(--color-text-faint)">
                    父切片上下文
                  </div>
                  <div className="text-(--color-text-faint) whitespace-pre-wrap break-words">
                    {parentText}
                  </div>
                </div>
              )}
            </motion.div>
          ) : (
            <div
              key="preview"
              className="line-clamp-3 px-3 pb-2 text-[12px] leading-[1.6] text-(--color-text-muted)"
            >
              {fullText || parentText}
            </div>
          )}
        </AnimatePresence>
      )}
    </article>
  )
}

function SectionTitle({ title, count }: { title: string; count: number }) {
  return (
    <h3 className="mb-2 flex items-center gap-2 text-[11px] uppercase tracking-wider text-(--color-text-faint)">
      <span>{title}</span>
      <span className="rounded-(--radius-control) bg-(--color-surface-2) px-1.5 py-0.5 font-mono text-[10px] text-(--color-text-muted)">
        {count}
      </span>
    </h3>
  )
}
