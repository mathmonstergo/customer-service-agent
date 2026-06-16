import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Clock3,
} from 'lucide-react'
import type { RetrievalEvalCase, RetrievalEvalRun } from '@/api/schemas'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/cn'
import {
  candidateScore,
  formatCount,
  formatDateTime,
  formatMetric,
  formatPercent,
  formatScore,
  isExpectedHit,
} from './helpers'

// 运行结果详情面板；只展示当前用例和最近一次/刚完成的运行结果。
export function EvaluationResultPanel({
  evalCase,
  runOverride,
}: {
  evalCase: RetrievalEvalCase | null
  runOverride: RetrievalEvalRun | null
}) {
  if (!evalCase) {
    return (
      <div className="flex h-full items-center justify-center text-center">
        <div className="-mt-24">
          <Activity className="mx-auto size-7 text-(--color-text-faint)" />
          <div className="mt-3 text-[14px] text-(--color-text-muted)">选择评测用例</div>
          <div className="mt-1 text-[12px] text-(--color-text-faint)">运行后查看指标、轨迹和候选来源</div>
        </div>
      </div>
    )
  }

  const run = runOverride || evalCase.latest_run || null
  const metrics = run?.metrics
  const analysis = run?.analysis
  const items = run?.retrieved_items || []

  return (
    <div className="h-full overflow-y-auto scroll-thin px-5 py-4">
      <div className="mb-3 flex flex-wrap items-center gap-2 text-[12px] text-(--color-text-faint)">
        <span>最近运行：{formatDateTime(run?.created_at)}</span>
        {run?.strategy && <span>策略：{run.strategy}</span>}
      </div>
        <MetricGrid
          recall={metrics?.recall_at_k}
          mrr={metrics?.mrr}
          top1={metrics?.hit_rate_at_1}
          vectorCount={analysis?.vector_count}
          keywordCount={analysis?.keyword_count}
        />
        <TraceBlock run={run} />
        <CandidateTable evalCase={evalCase} items={items} />
    </div>
  )
}

// 指标条保持五列稳定，避免 Recall/MRR/Top1 数值变化导致布局跳动。
function MetricGrid({
  recall,
  mrr,
  top1,
  vectorCount,
  keywordCount,
}: {
  recall?: number
  mrr?: number
  top1?: number
  vectorCount?: number
  keywordCount?: number
}) {
  const metrics = [
    { label: 'Recall@K', value: formatPercent(recall), tone: recall && recall > 0 ? 'success' : 'muted' },
    { label: 'MRR', value: formatMetric(mrr), tone: mrr && mrr > 0 ? 'success' : 'muted' },
    { label: 'Top1 命中', value: formatPercent(top1), tone: top1 && top1 > 0 ? 'success' : 'muted' },
    { label: 'vector_count', value: formatCount(vectorCount), tone: 'muted' },
    { label: 'keyword_count', value: formatCount(keywordCount), tone: 'muted' },
  ] as const

  return (
    <div className="grid grid-cols-5 gap-2">
      {metrics.map((metric) => (
        <div
          key={metric.label}
          className="rounded-(--radius-control) border border-(--color-border) bg-(--color-surface) px-3 py-3"
        >
          <div className="text-[11px] text-(--color-text-faint)">{metric.label}</div>
          <div className="mt-2 flex items-center gap-1.5">
            <span className="font-mono text-[20px] leading-none text-(--color-text)">
              {metric.value}
            </span>
            {metric.tone === 'success' && <CheckCircle2 className="size-3.5 text-(--color-success)" />}
          </div>
        </div>
      ))}
    </div>
  )
}

// 运行轨迹区当前只展示 hybrid retrieval 单步，命名上为后续 agentic trace 预留。
function TraceBlock({ run }: { run: RetrievalEvalRun | null }) {
  const analysis = run?.analysis
  return (
    <section className="mt-4 rounded-(--radius-control) border border-(--color-border) bg-(--color-surface) p-3">
      <div className="mb-3 flex items-center gap-2 text-[12px] font-[540] text-(--color-text)">
        <Activity className="size-3.5 text-(--color-primary-hi)" />
        运行轨迹 / 分析
        {run?.strategy && <Badge tone="primary">{run.strategy}</Badge>}
      </div>
      {!run ? (
        <div className="text-[12px] text-(--color-text-faint)">当前用例尚未运行</div>
      ) : (
        <div className="space-y-3">
          <div className="grid grid-cols-3 gap-2">
            <TraceField label="intent" value={analysis?.intent} />
            <TraceField label="confidence" value={analysis?.confidence} />
            <TraceField label="query_rewrite" value={analysis?.query_rewrite || analysis?.query} />
          </div>
          <div className="flex items-center gap-2 rounded-(--radius-control) border border-(--color-border-soft) bg-(--color-surface-2) px-3 py-2 text-[12px]">
            <span className="inline-flex size-5 items-center justify-center rounded-full bg-(--color-primary-soft) text-[11px] text-(--color-primary-hi)">
              1
            </span>
            <span className="text-(--color-text)">hybrid retrieval</span>
            <span className="ml-auto font-mono text-[10px] text-(--color-text-faint)">
              vector_count {formatCount(analysis?.vector_count)}
            </span>
            <span className="font-mono text-[10px] text-(--color-text-faint)">
              keyword_count {formatCount(analysis?.keyword_count)}
            </span>
            <CheckCircle2 className="size-3.5 text-(--color-success)" />
          </div>
          <div className="flex flex-wrap gap-1">
            {(analysis?.query_terms || []).map((term) => (
              <Badge key={term} tone="muted">
                {term}
              </Badge>
            ))}
          </div>
        </div>
      )}
    </section>
  )
}

// 轨迹字段使用截断展示，完整内容交给 title，避免长 query rewrite 撑开布局。
function TraceField({ label, value }: { label: string; value?: string }) {
  return (
    <div className="rounded-(--radius-control) border border-(--color-border-soft) bg-(--color-surface-2) px-2.5 py-2">
      <div className="text-[10px] text-(--color-text-faint)">{label}</div>
      <div className="mt-1 truncate text-[12px] text-(--color-text-muted)" title={value || '--'}>
        {value || '--'}
      </div>
    </div>
  )
}

// 候选来源表按期望命中做弱标记，帮助定位资料、切块或别名问题。
function CandidateTable({
  evalCase,
  items,
}: {
  evalCase: RetrievalEvalCase
  items: RetrievalEvalRun['retrieved_items']
}) {
  return (
    <section className="mt-4 rounded-(--radius-control) border border-(--color-border) bg-(--color-surface)">
      <div className="flex items-center gap-3 border-b border-(--color-border) px-3 py-3">
        <div className="text-[12px] font-[540] text-(--color-text)">候选来源</div>
        <Badge tone="muted">Top {items.length}</Badge>
        <div className="ml-auto flex items-center gap-3 text-[11px] text-(--color-text-faint)">
          <LegendDot tone="hit" label="命中期望" />
          <LegendDot tone="miss" label="未命中期望" />
        </div>
      </div>
      {items.length === 0 ? (
        <div className="flex items-center justify-center gap-2 px-4 py-10 text-[12px] text-(--color-text-faint)">
          <Clock3 className="size-4" />
          运行后展示候选来源
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-left text-[12px]">
            <thead className="border-b border-(--color-border-soft) text-[10px] uppercase tracking-wide text-(--color-text-faint)">
              <tr>
                <th className="w-12 px-3 py-2 font-[500]">rank</th>
                <th className="w-16 px-3 py-2 font-[500]">命中</th>
                <th className="w-24 px-3 py-2 font-[500]">source_type</th>
                <th className="px-3 py-2 font-[500]">source_id</th>
                <th className="px-3 py-2 font-[500]">chunk_id</th>
                <th className="w-20 px-3 py-2 font-[500]">score</th>
                <th className="px-3 py-2 font-[500]">channels</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item, index) => {
                const hit = isExpectedHit(item, evalCase)
                return (
                  <tr
                    key={`${item.id}-${index}`}
                    className={cn(
                      'border-b border-(--color-border-soft) last:border-0',
                      hit ? 'bg-(--color-success)/[0.035]' : 'hover:bg-(--color-surface-2)',
                    )}
                  >
                    <td className="px-3 py-2 font-mono text-[11px] text-(--color-text-faint)">
                      {index + 1}
                    </td>
                    <td className="px-3 py-2">
                      {hit ? (
                        <CheckCircle2 className="size-3.5 text-(--color-success)" />
                      ) : (
                        <AlertTriangle className="size-3.5 text-(--color-warning)" />
                      )}
                    </td>
                    <td className="px-3 py-2 text-(--color-text-muted)">{item.source_type}</td>
                    <td className="max-w-36 truncate px-3 py-2 font-mono text-[11px] text-(--color-text)">
                      {item.source_id || '--'}
                    </td>
                    <td className="max-w-36 truncate px-3 py-2 font-mono text-[11px] text-(--color-text-muted)">
                      {item.id || '--'}
                    </td>
                    <td className="px-3 py-2 font-mono text-[11px] text-(--color-text)">
                      {formatScore(candidateScore(item))}
                    </td>
                    <td className="px-3 py-2">
                      <div className="flex flex-wrap gap-1">
                        {(item.channels || []).map((channel) => (
                          <Badge key={channel} tone="muted">
                            {channel}
                          </Badge>
                        ))}
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

// 候选表图例，约束只表达命中/未命中两种评测态。
function LegendDot({ tone, label }: { tone: 'hit' | 'miss'; label: string }) {
  return (
    <span className="inline-flex items-center gap-1">
      <span
        className={cn(
          'inline-block size-1.5 rounded-full',
          tone === 'hit' ? 'bg-(--color-success)' : 'bg-(--color-warning)',
        )}
      />
      {label}
    </span>
  )
}
