export type DocumentChunkerType = 'naive' | 'manual' | 'qa' | 'table'

export const DOCUMENT_CHUNKER_OPTIONS: {
  value: DocumentChunkerType
  label: string
}[] = [
  { value: 'naive', label: 'Naive' },
  { value: 'manual', label: 'Manual' },
  { value: 'qa', label: 'Q/A' },
  { value: 'table', label: 'Table' },
]

const DOCUMENT_CHUNKER_LABELS: Record<DocumentChunkerType, string> = {
  naive: 'Naive',
  manual: 'Manual',
  qa: 'Q/A',
  table: 'Table',
}

// 规范化后端返回的 chunker 字段；旧数据或未知值在 UI 上按 naive 展示。
export function normalizeDocumentChunkerType(value: unknown): DocumentChunkerType {
  const raw = typeof value === 'string' ? value.trim().toLowerCase() : ''
  if (raw === 'manual' || raw === 'qa' || raw === 'table') return raw
  return 'naive'
}

// 统一列表和抽屉的 chunker 标签，避免同一枚举在多个组件里重复硬编码。
export function documentChunkerLabel(value: unknown): string {
  return DOCUMENT_CHUNKER_LABELS[normalizeDocumentChunkerType(value)]
}
