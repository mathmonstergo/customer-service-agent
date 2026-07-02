interface KgExtractionCounts {
  entity_count?: number | null
  relation_count?: number | null
}

// 整理 KG 抽取完成提示，关键约束是直接显示后端返回的实体/关系计数。
export function formatKgExtractionResult(result: KgExtractionCounts): string {
  return `KG 候选已生成：${result.entity_count ?? 0} 个实体，${result.relation_count ?? 0} 条关系`
}

// 缩短文档和切片 ID 的展示文本，关键约束是复制时仍使用完整 ID。
export function shortDocumentId(value: string | null | undefined): string {
  const clean = String(value || '').trim()
  if (clean.length <= 14) return clean
  return `${clean.slice(0, 12)}...`
}
