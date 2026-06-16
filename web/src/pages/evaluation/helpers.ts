import type { RetrievalEvalCase, RetrievalEvalItem } from '@/api/schemas'

export const CASE_STATUS_OPTIONS: { value: string; label: string }[] = [
  { value: '', label: '全部' },
  { value: 'active', label: '启用' },
  { value: 'disabled', label: '禁用' },
]

export const CASE_FORM_STATUS_OPTIONS: { value: string; label: string }[] = [
  { value: 'active', label: '启用' },
  { value: 'disabled', label: '禁用' },
]

// 将换行或中英文逗号分隔的输入拆成干净数组，用于 source/chunk/tag 字段。
export function splitListInput(value: string): string[] {
  return value
    .split(/[\n,，]+/)
    .map((item) => item.trim())
    .filter(Boolean)
}

// 将数组字段还原为多行输入文本，保持编辑抽屉可读。
export function joinListInput(values: string[] | undefined | null): string {
  return Array.isArray(values) ? values.join('\n') : ''
}

// 格式化百分比指标；未知值统一显示占位，避免误读为 0%。
export function formatPercent(value: number | undefined): string {
  if (typeof value !== 'number' || Number.isNaN(value)) return '--'
  return `${Math.round(value * 100)}%`
}

// 格式化小数指标；MRR 等指标固定两位便于横向比较。
export function formatMetric(value: number | undefined): string {
  if (typeof value !== 'number' || Number.isNaN(value)) return '--'
  return value.toFixed(2)
}

// 格式化数量指标；未知值使用占位以区分真实 0。
export function formatCount(value: number | undefined): string {
  if (typeof value !== 'number' || Number.isNaN(value)) return '--'
  return String(value)
}

// 格式化候选分数；保留三位小数兼顾排序辨识和表格宽度。
export function formatScore(value: number | undefined | null): string {
  if (typeof value !== 'number' || Number.isNaN(value)) return '--'
  return value.toFixed(3)
}

// 格式化运行时间；后端字符串无法解析时原样展示，避免吞掉诊断信息。
export function formatDateTime(value: string | undefined): string {
  if (!value) return '未运行'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

// 选择候选来源的展示分数，优先 fused_score，再退回各召回通道分数。
export function candidateScore(item: RetrievalEvalItem): number | undefined {
  if (typeof item.fused_score === 'number') return item.fused_score
  if (typeof item.vector_score === 'number') return item.vector_score
  if (typeof item.keyword_score === 'number') return item.keyword_score
  return undefined
}

// 判断候选是否命中期望；chunk 期望优先于 source 期望，保持评测口径明确。
export function isExpectedHit(item: RetrievalEvalItem, evalCase: RetrievalEvalCase): boolean {
  const expectedChunkIds = evalCase.expected_chunk_ids || []
  if (expectedChunkIds.length > 0) return expectedChunkIds.includes(item.id)
  return (evalCase.expected_source_ids || []).includes(item.source_id)
}

// 汇总期望标注数量，供列表行用短文案展示。
export function summarizeExpected(evalCase: RetrievalEvalCase): string {
  const chunkCount = evalCase.expected_chunk_ids?.length || 0
  const sourceCount = evalCase.expected_source_ids?.length || 0
  if (chunkCount > 0) return `${chunkCount} 个 chunk`
  if (sourceCount > 0) return `${sourceCount} 个 source`
  return '未标注'
}
