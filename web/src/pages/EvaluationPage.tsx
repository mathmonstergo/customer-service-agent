import { useMemo, useState } from 'react'
import { BookOpen, ClipboardCheck, Loader2, Play, Plus, Search, X } from 'lucide-react'
import type { RetrievalEvalCase, RetrievalEvalRun } from '@/api/schemas'
import {
  useRetrievalEvalCases,
  useRunRetrievalEvalCase,
} from '@/api/hooks'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { toast } from '@/components/ui/toast'
import { cn } from '@/lib/cn'
import { AliasPanel } from './evaluation/alias-panel'
import { CaseDrawer } from './evaluation/case-drawer'
import { EvaluationCaseList } from './evaluation/case-list'
import { EvaluationResultPanel } from './evaluation/result-panel'
import { CASE_STATUS_OPTIONS, formatPercent } from './evaluation/helpers'

// 效果验收工作台主页面；对齐智能问答页的左栏宽度和主面板 header 位置。
export default function EvaluationPage() {
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [aliasOpen, setAliasOpen] = useState(false)
  const [editingCase, setEditingCase] = useState<RetrievalEvalCase | null>(null)
  const [runOverrides, setRunOverrides] = useState<Record<string, RetrievalEvalRun>>({})
  const params = useMemo(
    () => ({ status: status || undefined, limit: 100, offset: 0 }),
    [status],
  )
  const casesQuery = useRetrievalEvalCases(params)
  const runCase = useRunRetrievalEvalCase()
  const items = useMemo(() => casesQuery.data?.items || [], [casesQuery.data?.items])

  const filteredItems = useMemo(() => {
    const needle = query.trim().toLowerCase()
    if (!needle) return items
    return items.filter((item) => {
      const tags = (item.tags || []).join(' ').toLowerCase()
      return (
        item.question.toLowerCase().includes(needle) ||
        tags.includes(needle) ||
        (item.intent || '').toLowerCase().includes(needle)
      )
    })
  }, [items, query])

  const effectiveSelectedId =
    selectedId && filteredItems.some((item) => item.id === selectedId)
      ? selectedId
      : filteredItems[0]?.id || null
  const selectedCase = filteredItems.find((item) => item.id === effectiveSelectedId) || null
  const selectedRun = selectedCase ? runOverrides[selectedCase.id] || null : null
  const effectiveRun = selectedRun || selectedCase?.latest_run || null
  const stats = useMemo(() => computeStats(items), [items])
  const runningSelected = runCase.isPending && runCase.variables === selectedCase?.id

  // 打开新建用例抽屉；主页面不固定承载编辑表单。
  const openNewCase = () => {
    setEditingCase(null)
    setDrawerOpen(true)
  }

  // 打开已有用例编辑抽屉，避免右侧常驻编辑栏挤压结果区。
  const openEditCase = (item: RetrievalEvalCase) => {
    setEditingCase(item)
    setDrawerOpen(true)
  }

  // 运行单条评测，并用本地 override 立即刷新详情区的最近运行结果。
  const handleRun = async (caseId: string) => {
    try {
      const run = await runCase.mutateAsync(caseId)
      setRunOverrides((current) => ({ ...current, [caseId]: run }))
      toast.success('评测运行完成')
    } catch (error) {
      toast.error((error as Error).message || '运行评测失败')
    }
  }

  // 保存后选中新用例；列表刷新由 mutation 的 query invalidation 负责。
  const handleSaved = (item: RetrievalEvalCase) => {
    setSelectedId(item.id)
  }

  return (
    <div className="flex h-full min-h-0">
      <aside className="flex h-full w-[240px] shrink-0 flex-col border-r border-(--color-border) bg-(--color-surface)">
        <div className="flex shrink-0 items-center gap-2 border-b border-(--color-border) px-3 py-2.5">
          <ClipboardCheck className="size-4 text-(--color-primary-hi)" />
          <div className="min-w-0 flex-1 text-[13px] font-[540] text-(--color-text)">
            评测用例
          </div>
          <Button variant="primary" size="sm" onClick={openNewCase} className="ml-auto">
            <Plus className="size-3.5" />
            新建
          </Button>
        </div>
        <div className="shrink-0 space-y-2 border-b border-(--color-border) p-2">
          <div className="relative">
            <Search className="absolute left-2 top-1/2 size-3.5 -translate-y-1/2 text-(--color-text-faint)" />
            <Input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜问题 / 标签 / 意图…"
              className="pl-7"
            />
            {query && (
              <button
                type="button"
                onClick={() => setQuery('')}
                className="absolute right-1 top-1/2 inline-flex size-6 -translate-y-1/2 items-center justify-center rounded text-(--color-text-faint) hover:text-(--color-text)"
              >
                <X className="size-3" />
              </button>
            )}
          </div>
          <SegmentedFilter value={status} onChange={setStatus} options={CASE_STATUS_OPTIONS} />
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto scroll-thin">
          <EvaluationCaseList
            items={filteredItems}
            activeId={effectiveSelectedId}
            isPending={casesQuery.isPending}
            isError={casesQuery.isError}
            onRetry={() => void casesQuery.refetch()}
            onSelect={setSelectedId}
            onEdit={openEditCase}
          />
        </div>
        <div className="shrink-0 border-t border-(--color-border) px-3 py-2 text-[11px] text-(--color-text-faint)">
          {filteredItems.length} / {casesQuery.data?.total ?? items.length} 个用例
        </div>
      </aside>

      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex shrink-0 items-center gap-2 border-b border-(--color-border) bg-(--color-surface) px-5 py-3">
          <div className="min-w-0 flex-1">
            <div className="flex min-w-0 items-center gap-2">
              <div className="truncate text-[14px] text-(--color-text)" title={selectedCase?.question}>
                {selectedCase?.question || '效果验收'}
              </div>
              {selectedCase && (
                <Badge tone={selectedCase.status === 'active' ? 'success' : 'muted'}>
                  {selectedCase.status === 'active' ? '启用' : '禁用'}
                </Badge>
              )}
            </div>
            <div className="mt-0.5 truncate text-[11px] text-(--color-text-faint)">
              用例 {casesQuery.data?.total ?? items.length} · 命中率 {formatPercent(stats.averageRecall)} · 待补期望 {stats.missingExpected}
              {effectiveRun?.strategy ? ` · ${effectiveRun.strategy}` : ''}
            </div>
          </div>
          <Button variant="outline" size="sm" onClick={() => setAliasOpen(true)}>
            <BookOpen className="size-3.5" />
            别名词典
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={() => selectedCase && void handleRun(selectedCase.id)}
            disabled={!selectedCase || runningSelected || selectedCase.status !== 'active'}
            title={selectedCase?.status === 'active' ? '运行单条评测' : '禁用用例不可运行'}
          >
            {runningSelected ? <Loader2 className="size-3.5 animate-spin" /> : <Play className="size-3.5" />}
            {runningSelected ? '运行中…' : '运行单条'}
          </Button>
        </header>

        <div className="min-h-0 flex-1">
          <EvaluationResultPanel
            evalCase={selectedCase}
            runOverride={selectedRun}
          />
        </div>
      </main>

      <AliasPanel open={aliasOpen} onOpenChange={setAliasOpen} />

      <CaseDrawer
        open={drawerOpen}
        item={editingCase}
        onOpenChange={setDrawerOpen}
        onSaved={handleSaved}
      />
    </div>
  )
}

// 统计顶部工具栏指标；只读用例快照，不在这里触发数据请求。
function computeStats(items: RetrievalEvalCase[]): {
  averageRecall?: number
  missingExpected: number
} {
  let recallSum = 0
  let recallCount = 0
  let missingExpected = 0
  for (const item of items) {
    if ((item.expected_source_ids?.length || 0) === 0 && (item.expected_chunk_ids?.length || 0) === 0) {
      missingExpected += 1
    }
    const recall = item.latest_run?.metrics?.recall_at_k
    if (typeof recall === 'number') {
      recallSum += recall
      recallCount += 1
    }
  }
  return {
    averageRecall: recallCount > 0 ? recallSum / recallCount : undefined,
    missingExpected,
  }
}

// 状态筛选分段控件；约束为单选，宽度按 240px 左栏收敛。
function SegmentedFilter({
  value,
  onChange,
  options,
}: {
  value: string
  onChange: (value: string) => void
  options: { value: string; label: string }[]
}) {
  return (
    <div className="grid grid-cols-3 gap-1 rounded-(--radius-control) border border-(--color-border) bg-(--color-surface-2) p-0.5">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          onClick={() => onChange(option.value)}
          className={cn(
            'rounded-(--radius-control) px-2.5 py-1 text-[12px] transition-colors',
            value === option.value
              ? 'bg-(--color-primary) text-white'
              : 'text-(--color-text-muted) hover:text-(--color-text)',
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}
