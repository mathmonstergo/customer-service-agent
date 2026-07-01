import { kgReviewStatusLabelMap } from '../../lib/labels.ts'
import type { KgEvidence, KgRelation } from '../../api/schemas.ts'

// 将 KG 审核状态翻译成客服后台可读文案；未知值保留原样方便排查后端新状态。
export function kgReviewStatusLabel(status: string | null | undefined): string {
  if (!status) return ''
  return kgReviewStatusLabelMap[status] || status
}

// 将模型置信度稳定显示为百分比；缺失时不伪造数值。
export function confidencePercent(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '未标注'
  return `${Math.round(Math.max(0, Math.min(1, value)) * 100)}%`
}

// 整理证据来源摘要；关键约束是保留文件、章节、页码的追溯信息。
export function evidenceSummary(evidence: Pick<KgEvidence, 'source_title' | 'section_path' | 'page_start' | 'page_end'>): string {
  const parts: string[] = []
  if (evidence.source_title) parts.push(evidence.source_title)
  for (const section of evidence.section_path || []) {
    if (section) parts.push(section)
  }
  if (evidence.page_start && evidence.page_end && evidence.page_start !== evidence.page_end) {
    parts.push(`第 ${evidence.page_start}-${evidence.page_end} 页`)
  } else if (evidence.page_start) {
    parts.push(`第 ${evidence.page_start} 页`)
  }
  return parts.join(' / ') || '未标注来源'
}

// 组合关系标题；关键约束是头实体、关系类型、尾实体缺一不可时仍给出稳定占位。
export function relationTitle(
  relation: Pick<KgRelation, 'head_entity_name' | 'relation_type' | 'tail_entity_name'>,
): string {
  const head = relation.head_entity_name || '未知实体'
  const type = relation.relation_type || '关联'
  const tail = relation.tail_entity_name || '未知实体'
  return `${head} - ${type} - ${tail}`
}

// 根据审核状态给 Badge 选择固定色系，避免页面各处状态颜色漂移。
export function kgStatusTone(status: string): 'success' | 'warning' | 'muted' | 'danger' {
  if (status === 'usable') return 'success'
  if (status === 'needs_review') return 'warning'
  if (status === 'disabled') return 'muted'
  return 'muted'
}

// 判断实体是否匹配当前前端搜索词；后端 MVP 暂无搜索参数，因此只筛当前页。
export function entityMatchesQuery(
  entity: { name: string; entity_type: string; aliases?: string[]; description?: string | null },
  query: string,
): boolean {
  const q = query.trim().toLowerCase()
  if (!q) return true
  return [entity.name, entity.entity_type, entity.description || '', ...(entity.aliases || [])]
    .join(' ')
    .toLowerCase()
    .includes(q)
}

// 判断关系是否匹配当前前端搜索词；用于同一页内快速缩小候选范围。
export function relationMatchesQuery(
  relation: Pick<KgRelation, 'head_entity_name' | 'head_entity_type' | 'relation_type' | 'tail_entity_name' | 'tail_entity_type' | 'description'>,
  query: string,
): boolean {
  const q = query.trim().toLowerCase()
  if (!q) return true
  return [
    relation.head_entity_name,
    relation.head_entity_type,
    relation.relation_type,
    relation.tail_entity_name,
    relation.tail_entity_type,
    relation.description || '',
  ]
    .join(' ')
    .toLowerCase()
    .includes(q)
}
