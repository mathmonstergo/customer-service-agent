import { useEffect, useMemo, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import {
  ChevronLeft,
  ChevronRight,
  Edit3,
  EyeOff,
  Eye,
  MessageCircleQuestion,
  RefreshCw,
  Save,
  X,
} from 'lucide-react'
import type { ImportChunk } from '@/api/schemas'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { StatusDot } from '@/components/ui/status-dot'
import { Textarea } from '@/components/ui/textarea'
import { SourceBlockPreview } from '@/components/shared/source-block-preview'
import {
  useEmbedImportChunk,
  useToggleImportChunkDisabled,
  useUpdateImportChunk,
} from '@/api/hooks'
import { toast } from '@/components/ui/toaster'
import { useUi } from '@/store/ui'
import { cn } from '@/lib/cn'
import { ease, dur } from '@/lib/motion'
import { embeddingStatusLabel, tr } from '@/lib/labels'
import { useHorizontalWheelScroll } from '@/lib/use-horizontal-wheel-scroll'

export function ChunkBrowser({ fileId, chunks }: { fileId: string; chunks: ImportChunk[] }) {
  const { currentChunkIndex, setCurrentChunkIndex, chunkEditMode, setChunkEditMode } = useUi()
  const toggleDisabled = useToggleImportChunkDisabled()
  const update = useUpdateImportChunk()
  const [draft, setDraft] = useState('')

  useEffect(() => {
    // 文件切换时复位
    setCurrentChunkIndex(0)
  }, [fileId, setCurrentChunkIndex])

  const safeIdx = Math.min(currentChunkIndex, Math.max(0, chunks.length - 1))
  const chunk = chunks[safeIdx]

  useEffect(() => {
    setDraft(chunk?.source_text || '')
  }, [chunk?.id])

  if (!chunks.length) {
    return (
      <div className="flex h-full items-center justify-center px-6 text-[13px] text-(--color-text-faint)">
        这份文档还没有切片；先点上方「开始解析」。
      </div>
    )
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* 切片导航：横向滚动 chips，与外部按钮组、抽屉头部对齐到 24px 左缘 */}
      <ChunkNav
        chunks={chunks}
        activeIndex={safeIdx}
        onJump={setCurrentChunkIndex}
      />
      {/* 切片元信息与操作 */}
      <ChunkToolbar
        chunk={chunk}
        editMode={chunkEditMode}
        onEditToggle={() => setChunkEditMode(!chunkEditMode)}
        onToggleDisabled={() =>
          toggleDisabled.mutate({ id: chunk.id, is_disabled: !chunk.is_disabled })
        }
      />
      {/* 切片正文：所有内容统一 px-6 与上方对齐 */}
      <div className="min-h-0 flex-1 overflow-y-auto scroll-thin px-6 py-5">
        <motion.div
          key={chunk.id + (chunkEditMode ? '-edit' : '-view')}
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: dur.base, ease: ease.out }}
          className="flex flex-col gap-4"
        >
          {chunk.questions?.length > 0 && <QuestionsBlock questions={chunk.questions} />}
          {chunkEditMode ? (
            <div className="flex flex-col gap-2">
              <Textarea value={draft} onChange={(e) => setDraft(e.target.value)} rows={14} />
              <div className="flex items-center justify-end gap-2">
                <span className="mr-auto text-[11px] text-(--color-text-faint)">
                  保存后切片 embedding 会变 stale，需要重新生成
                </span>
                <Button
                  variant="ghost"
                  onClick={() => {
                    setDraft(chunk.source_text || '')
                    setChunkEditMode(false)
                  }}
                >
                  取消
                </Button>
                <Button
                  variant="primary"
                  disabled={update.isPending || draft === chunk.source_text}
                  onClick={async () => {
                    await update.mutateAsync({ id: chunk.id, source_text: draft })
                    setChunkEditMode(false)
                  }}
                >
                  <Save className="size-3.5" />
                  保存切片
                </Button>
              </div>
            </div>
          ) : chunk.source_blocks?.length ? (
            <SourceBlockPreview blocks={chunk.source_blocks} fileId={fileId} />
          ) : (
            <pre className="whitespace-pre-wrap text-[13px] text-(--color-text)">
              {chunk.source_text}
            </pre>
          )}
        </motion.div>
      </div>
    </div>
  )
}

function ChunkNav({
  chunks,
  activeIndex,
  onJump,
}: {
  chunks: ImportChunk[]
  activeIndex: number
  onJump: (i: number) => void
}) {
  const scrollerRef = useRef<HTMLDivElement>(null)
  const activeRef = useRef<HTMLButtonElement>(null)
  useHorizontalWheelScroll(scrollerRef)

  // 当前 chip 滚动到可视区
  useEffect(() => {
    const el = activeRef.current
    if (!el || !scrollerRef.current) return
    el.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' })
  }, [activeIndex])

  return (
    <div className="flex shrink-0 items-center gap-1.5 border-b border-(--color-border) px-6 py-2">
      <span className="shrink-0 text-[11px] uppercase tracking-wider text-(--color-text-faint)">
        切片 <span className="text-(--color-text-muted)">{chunks.length}</span>
      </span>
      <Button
        variant="ghost"
        size="icon"
        className="size-6"
        disabled={activeIndex <= 0}
        onClick={() => onJump(Math.max(0, activeIndex - 1))}
      >
        <ChevronLeft className="size-3.5" />
      </Button>
      <div
        ref={scrollerRef}
        className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto scroll-thin scroll-smooth pb-0.5"
      >
        {chunks.map((c, i) => {
          const isActive = i === activeIndex
          // 橙点严格语义：embed 过、原文被改后被标 stale、还没重做。
          // failed 是另一类"上次 embed 出错"问题，已经在切片工具栏的 StatusDot 用红色文字标出，不再用小点重复提示。
          const isStale = c.embedding_status === 'stale'
          const hasQuestions = c.questions_status === 'ready' && c.questions?.length > 0
          return (
            <button
              key={c.id}
              ref={isActive ? activeRef : undefined}
              type="button"
              onClick={() => onJump(i)}
              className={cn(
                'group inline-flex shrink-0 items-center gap-1 rounded-(--radius-control) border px-2 py-1 text-[11px] transition-colors',
                isActive
                  ? 'border-(--color-primary)/40 bg-(--color-primary-soft) text-(--color-text)'
                  : 'border-transparent text-(--color-text-muted) hover:bg-(--color-surface-2) hover:text-(--color-text)',
                c.is_disabled && 'opacity-50',
              )}
              title={[
                c.section_path?.join(' > ') || c.block_type || '',
                isStale && '原文已改，向量待刷新',
                hasQuestions && `${c.questions.length} 条假设问题`,
              ]
                .filter(Boolean)
                .join(' · ')}
            >
              <span className="font-mono text-(--color-text-faint) group-hover:text-(--color-text-muted)">
                #{i + 1}
              </span>
              {(isStale || hasQuestions) && (
                <span className="inline-flex items-center gap-0.5">
                  {isStale && <span className="size-1 rounded-full bg-(--color-warning)" />}
                  {hasQuestions && <span className="size-1 rounded-full bg-(--color-primary)" />}
                </span>
              )}
            </button>
          )
        })}
      </div>
      <Button
        variant="ghost"
        size="icon"
        className="size-6"
        disabled={activeIndex >= chunks.length - 1}
        onClick={() => onJump(Math.min(chunks.length - 1, activeIndex + 1))}
      >
        <ChevronRight className="size-3.5" />
      </Button>
    </div>
  )
}

function ChunkToolbar({
  chunk,
  editMode,
  onEditToggle,
  onToggleDisabled,
}: {
  chunk: ImportChunk
  editMode: boolean
  onEditToggle: () => void
  onToggleDisabled: () => void
}) {
  const embedChunk = useEmbedImportChunk()
  const isEmbedding =
    embedChunk.isPending && embedChunk.variables === chunk.id
  // 切片向量需要刷新的两种状态：编辑后被自动标 stale；上次生成失败。
  const needsEmbed = chunk.embedding_status === 'stale' || chunk.embedding_status === 'failed'

  const meta: string[] = []
  if (chunk.page_start) {
    meta.push(
      chunk.page_end && chunk.page_end !== chunk.page_start
        ? `页 ${chunk.page_start}–${chunk.page_end}`
        : `页 ${chunk.page_start}`,
    )
  }
  if (chunk.block_type) meta.push(chunk.block_type)
  const sectionLeaf = chunk.section_path?.length
    ? chunk.section_path[chunk.section_path.length - 1]
    : null
  return (
    <div className="flex shrink-0 items-center justify-between gap-2 border-b border-(--color-border-soft) bg-(--color-surface) px-6 py-2.5">
      <div className="flex min-w-0 flex-1 items-center gap-2 text-[12px] text-(--color-text-muted)">
        {sectionLeaf && (
          <span className="truncate text-(--color-text)" title={chunk.section_path?.join(' > ')}>
            {sectionLeaf}
          </span>
        )}
        {chunk.is_disabled && <Badge tone="danger">已禁</Badge>}
        {chunk.questions_status === 'ready' && chunk.questions?.length > 0 && (
          <Badge tone="primary">
            <MessageCircleQuestion className="size-3" />
            {chunk.questions.length} 问
          </Badge>
        )}
        <StatusDot
          tone={mapEmbed(chunk.embedding_status)}
          label={tr(embeddingStatusLabel, chunk.embedding_status, '未索引')}
        />
        {meta.length > 0 && (
          <span className="text-(--color-text-faint)">· {meta.join(' · ')}</span>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-1.5">
        <Button
          variant={needsEmbed ? 'primary' : 'ghost'}
          size="sm"
          disabled={isEmbedding || editMode}
          onClick={async () => {
            try {
              const res = await embedChunk.mutateAsync(chunk.id)
              const count = res?.count ?? 0
              toast.success(`已重新生成切片向量（${count} 条）`)
            } catch (e) {
              toast.error((e as Error).message || '重新生成失败')
            }
          }}
          title={needsEmbed ? '切片原文有改动，向量已 stale' : '重新生成该切片向量'}
        >
          <RefreshCw className={isEmbedding ? 'size-3.5 animate-spin' : 'size-3.5'} />
          {isEmbedding ? '生成中' : '重新向量'}
        </Button>
        <Button
          variant={chunk.is_disabled ? 'default' : 'ghost'}
          size="sm"
          onClick={onToggleDisabled}
        >
          {chunk.is_disabled ? <Eye className="size-3.5" /> : <EyeOff className="size-3.5" />}
          {chunk.is_disabled ? '启用' : '禁用'}
        </Button>
        <Button variant={editMode ? 'primary' : 'ghost'} size="sm" onClick={onEditToggle}>
          {editMode ? <X className="size-3.5" /> : <Edit3 className="size-3.5" />}
          {editMode ? '退出编辑' : '编辑原文'}
        </Button>
      </div>
    </div>
  )
}

function QuestionsBlock({ questions }: { questions: string[] }) {
  const list = useMemo(() => questions.filter(Boolean), [questions])
  if (!list.length) return null
  return (
    <details open className="surface rounded-(--radius-control) px-3 py-2 text-[13px]">
      <summary className="cursor-pointer select-none text-(--color-text-muted) [&::-webkit-details-marker]:hidden">
        <MessageCircleQuestion className="mr-1.5 inline size-3.5 -translate-y-px" />
        假设问题 <span className="text-(--color-text-faint)">({list.length})</span>
      </summary>
      <ul className="mt-2 ml-5 list-disc space-y-1 text-(--color-text)">
        {list.map((q, i) => (
          <li key={i}>{q}</li>
        ))}
      </ul>
    </details>
  )
}

function mapEmbed(s?: string) {
  if (s === 'ready') return 'ready' as const
  if (s === 'failed') return 'failed' as const
  if (s === 'stale') return 'stale' as const
  return 'pending' as const
}
