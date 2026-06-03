import { useEffect, useMemo, useState } from 'react'
import { ChevronLeft, ChevronRight, Loader2, Plus, Search, Waypoints, X } from 'lucide-react'
import { useEmbedPendingFaqs, useFaqs } from '@/api/hooks'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { toast } from '@/components/ui/toaster'
import { useUi } from '@/store/ui'
import { cn } from '@/lib/cn'
import { FaqStatsBar } from './faqs/faq-stats-bar'
import { FaqList } from './faqs/faq-list'
import { FaqDrawer } from './faqs/faq-drawer'

const STATUS_OPTIONS = [
  { value: '', label: '全部' },
  { value: 'usable', label: '可用' },
  { value: 'needs_review', label: '待复核' },
  { value: 'disabled', label: '禁用' },
]

const EMBED_OPTIONS = [
  { value: '', label: '全部' },
  { value: 'ready', label: '已索引' },
  { value: 'pending', label: '未索引' },
  { value: 'stale', label: '过期' },
  { value: 'failed', label: '失败' },
]

const PAGE_SIZE = 30

export default function FaqsPage() {
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('')
  const [embedding, setEmbedding] = useState('')
  const [page, setPage] = useState(1)
  const { openFaqId, setOpenFaqId } = useUi()

  // 任一筛选变化都跳回第 1 页，避免页码越界导致空列表。
  useEffect(() => {
    setPage(1)
  }, [query, status, embedding])

  const { data, isPending, isError, isFetching, refetch } = useFaqs({
    query,
    status,
    embedding,
    page,
    pageSize: PAGE_SIZE,
  })
  const items = data?.items || []
  const total = data?.total ?? items.length
  const counts = data?.status_counts || {}
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  const { pendingEmbedding, failedEmbedding } = useMemo(() => {
    let p = 0
    let f = 0
    for (const i of items) {
      if (i.embedding_status === 'failed') f++
      else if (i.embedding_status !== 'ready') p++
    }
    return { pendingEmbedding: p, failedEmbedding: f }
  }, [items])

  // 本页可见的「非绿」FAQ 数（未索引/过期/失败），作为批量 Embedding 的数字提示。
  // 真正处理范围是全库候选（后端一次 ≤200 条），不止当前页。
  const pageNonGreen = pendingEmbedding + failedEmbedding
  const embedPending = useEmbedPendingFaqs()
  const onEmbedPending = async () => {
    try {
      const r = await embedPending.mutateAsync(200)
      toast.success(`已为 ${r?.count ?? 0} 条 FAQ 生成 embedding`)
    } catch (e) {
      toast.error((e as Error).message || '批量 embedding 失败')
    }
  }

  return (
    <div className="flex h-full flex-col">
      {/* 顶部工具栏 */}
      <div className="flex shrink-0 items-center gap-2 border-b border-(--color-border) px-6 py-3">
        <div className="relative max-w-md flex-1">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 size-3.5 text-(--color-text-faint)" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="搜问题 / 答案 / 标签…"
            className="pl-7"
          />
          {query && (
            <button
              type="button"
              onClick={() => setQuery('')}
              className="absolute right-1 top-1/2 -translate-y-1/2 inline-flex size-6 items-center justify-center rounded text-(--color-text-faint) hover:text-(--color-text)"
            >
              <X className="size-3" />
            </button>
          )}
        </div>
        <SegmentedFilter value={status} onChange={setStatus} options={STATUS_OPTIONS} />
        <SegmentedFilter value={embedding} onChange={setEmbedding} options={EMBED_OPTIONS} />
        <div className="ml-auto" />
        <Button
          variant="outline"
          onClick={onEmbedPending}
          disabled={embedPending.isPending}
          title="为所有未索引 / 过期 / 失败的 FAQ 批量生成 embedding（一次最多 200 条）"
        >
          {embedPending.isPending ? (
            <Loader2 className="size-3.5 animate-spin" />
          ) : (
            <Waypoints className="size-3.5" />
          )}
          {embedPending.isPending ? '生成中…' : 'Embedding'}
          {pageNonGreen > 0 && !embedPending.isPending && (
            <span className="ml-0.5 inline-flex h-4 min-w-4 items-center justify-center rounded-(--radius-control) bg-(--color-warning)/20 px-1 font-mono text-[10px] text-(--color-warning)">
              {pageNonGreen}
            </span>
          )}
        </Button>
        <Button variant="primary" onClick={() => setOpenFaqId('new')}>
          <Plus className="size-3.5" />
          新建 FAQ
        </Button>
      </div>

      {/* 知识库脉搏 + 主列表 */}
      <div className="min-h-0 flex-1 overflow-y-auto scroll-thin">
        <FaqStatsBar
          total={total}
          needsReview={Number(counts.needs_review) || 0}
          pendingEmbedding={pendingEmbedding}
          failedEmbedding={failedEmbedding}
        />
        <div className="px-6 py-5">
          <FaqList
            items={items}
            isPending={isPending}
            isError={isError}
            onRetry={() => refetch()}
            activeId={openFaqId}
            onSelect={(id) => setOpenFaqId(id)}
          />
          {total > PAGE_SIZE && (
            <Pagination
              page={page}
              totalPages={totalPages}
              total={total}
              pageSize={PAGE_SIZE}
              loading={isFetching}
              onChange={setPage}
            />
          )}
        </div>
      </div>

      <FaqDrawer
        faqId={openFaqId}
        onClose={() => setOpenFaqId(null)}
        onCreated={(id) => setOpenFaqId(id)}
      />
    </div>
  )
}

function Pagination({
  page,
  totalPages,
  total,
  pageSize,
  loading,
  onChange,
}: {
  page: number
  totalPages: number
  total: number
  pageSize: number
  loading: boolean
  onChange: (p: number) => void
}) {
  const start = (page - 1) * pageSize + 1
  const end = Math.min(page * pageSize, total)
  return (
    <div className="mt-5 flex items-center justify-between gap-3 text-[12px] text-(--color-text-muted)">
      <span>
        <span className={cn(loading && 'animate-pulse')}>
          {start}–{end}
        </span>
        <span className="mx-1 text-(--color-text-faint)">/</span>
        <span>{total}</span>
      </span>
      <div className="flex items-center gap-1">
        <Button
          variant="ghost"
          size="sm"
          disabled={page <= 1 || loading}
          onClick={() => onChange(Math.max(1, page - 1))}
        >
          <ChevronLeft className="size-3.5" />
          上一页
        </Button>
        <PageNumbers page={page} totalPages={totalPages} onChange={onChange} disabled={loading} />
        <Button
          variant="ghost"
          size="sm"
          disabled={page >= totalPages || loading}
          onClick={() => onChange(Math.min(totalPages, page + 1))}
        >
          下一页
          <ChevronRight className="size-3.5" />
        </Button>
      </div>
    </div>
  )
}

// 智能页码：当前页前后各 1 个 + 首尾，用省略号填中间，最多展示 ~7 个槽。
function PageNumbers({
  page,
  totalPages,
  onChange,
  disabled,
}: {
  page: number
  totalPages: number
  onChange: (p: number) => void
  disabled?: boolean
}) {
  const pages: (number | 'ellipsis-l' | 'ellipsis-r')[] = []
  const push = (v: number) => {
    if (!pages.includes(v)) pages.push(v)
  }
  push(1)
  if (page - 1 > 2) pages.push('ellipsis-l')
  for (let p = Math.max(2, page - 1); p <= Math.min(totalPages - 1, page + 1); p++) push(p)
  if (page + 1 < totalPages - 1) pages.push('ellipsis-r')
  if (totalPages > 1) push(totalPages)

  return (
    <div className="flex items-center gap-0.5">
      {pages.map((p, i) =>
        typeof p === 'number' ? (
          <button
            key={`p-${p}`}
            type="button"
            disabled={disabled}
            onClick={() => onChange(p)}
            className={cn(
              'inline-flex h-7 min-w-7 items-center justify-center rounded-(--radius-control) px-1.5 font-mono text-[12px] transition-colors',
              'disabled:pointer-events-none disabled:opacity-50',
              p === page
                ? 'bg-(--color-primary-soft) text-(--color-text)'
                : 'text-(--color-text-muted) hover:bg-(--color-surface-2) hover:text-(--color-text)',
            )}
          >
            {p}
          </button>
        ) : (
          <span
            key={`e-${i}`}
            className="inline-flex h-7 items-center px-1 font-mono text-[12px] text-(--color-text-faint)"
          >
            …
          </span>
        ),
      )}
    </div>
  )
}

function SegmentedFilter({
  value,
  onChange,
  options,
}: {
  value: string
  onChange: (v: string) => void
  options: { value: string; label: string }[]
}) {
  return (
    <div className="flex items-center gap-1 rounded-(--radius-control) bg-(--color-surface-2) border border-(--color-border) p-0.5">
      {options.map((opt) => (
        <button
          key={opt.value}
          type="button"
          onClick={() => onChange(opt.value)}
          className={`rounded-(--radius-control) px-2 py-1 text-[12px] transition-colors ${
            value === opt.value
              ? 'bg-(--color-surface-3) text-(--color-text)'
              : 'text-(--color-text-muted) hover:text-(--color-text)'
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  )
}
