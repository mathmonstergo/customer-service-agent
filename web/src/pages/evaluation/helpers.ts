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
  if (chunkCount > 0) return `${chunkCount} 个期望切片`
  if (sourceCount > 0) return `${sourceCount} 个期望来源`
  return '待设置期望命中'
}

// 候选来源标题优先展示业务可读字段，缺失时才退回内部来源 id。
export function candidateSourceLabel(item: RetrievalEvalItem): string {
  const title = String(item.source_title || '').trim()
  if (title) return title
  const question = String(item.question || '').trim()
  if (question) return question
  const metadataTitle = item.metadata?.source_title
  if (typeof metadataTitle === 'string' && metadataTitle.trim()) return metadataTitle.trim()
  return item.source_id || '--'
}

// 候选位置合并页码、章节、审核切片 id，FAQ 则显示来源类型。
export function candidateLocationLabel(item: RetrievalEvalItem): string {
  const parts: string[] = []
  if (item.page_start) {
    parts.push(
      item.page_end && item.page_end !== item.page_start
        ? `页 ${item.page_start}-${item.page_end}`
        : `页 ${item.page_start}`,
    )
  }
  if (item.section_path?.length) parts.push(item.section_path.join(' > '))
  if (item.source_chunk_id) parts.push(`审核切片 ${item.source_chunk_id}`)
  if (item.block_type && item.block_type !== 'faq') parts.push(item.block_type)
  if (parts.length > 0) return parts.join(' · ')
  if (item.source_type === 'faq') return 'FAQ'
  return '--'
}

// 候选摘要优先使用答案/正文；FAQ content 为空时也能展示可读答案。
export function candidateExcerpt(item: RetrievalEvalItem): string {
  const answer = String(item.answer || '').trim()
  if (answer) return answer
  const content = String(item.content || '').trim()
  if (content) return content
  const excerpt = item.metadata?.source_excerpt
  return typeof excerpt === 'string' && excerpt.trim() ? excerpt.trim() : '--'
}

// 将内部 source_type 转成工作台读得懂的短标签。
export function sourceTypeLabel(value: string): string {
  if (value === 'faq') return 'FAQ'
  if (value === 'document') return '文档'
  return value || '--'
}

// 将内部策略名转成中文展示；未知策略保留原值，便于排查。
export function displayStrategyLabel(value: string | undefined | null): string {
  if (!value) return '未运行'
  if (value === 'retrieval_hybrid_v1') return '混合检索 v1'
  return value
}

// 将召回通道短码转成中文徽章，避免候选表暴露 raw channel。
export function retrievalChannelLabel(value: string): string {
  if (value === 'vector') return '向量'
  if (value === 'keyword') return '关键词'
  if (value === 'fused') return '融合'
  return value || '--'
}
