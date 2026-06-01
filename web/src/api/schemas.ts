// 前端 TS 类型：从 admin_server.py 的 normalize_*_payload / DB rows 字段提炼。
// 只覆盖 3 个迁移页面用到的字段；未列出的字段仍可通过 `[key: string]: unknown` 兼容。

export interface ImportFile {
  id: string
  original_name: string
  file_type: string
  parser: string
  status:
    | 'pending'
    | 'processing'
    | 'needs_review'
    | 'completed'
    | 'failed'
    | string
  message_count: number
  chunk_count: number
  candidate_count: number
  error: string | null
  is_disabled: boolean
  parse_progress: Record<string, unknown>
  embedding_summary?: EmbeddingSummary
  created_at: string
  updated_at: string
  [key: string]: unknown
}

export interface ImportChunk {
  id: string
  file_id: string
  chunk_index: number
  source_text: string
  parent_content?: string
  section_path: string[]
  page_start: number | null
  page_end: number | null
  block_type: string | null
  source_offsets: Record<string, unknown>
  source_blocks: SourceBlock[]
  status: string
  is_disabled: boolean
  questions: string[]
  questions_status: 'pending' | 'ready' | 'failed' | 'skipped' | string
  questions_model: string | null
  questions_updated_at: string | null
  questions_error: string | null
  embedding_status: 'pending' | 'ready' | 'stale' | 'failed' | string
  keywords?: string[]
  [key: string]: unknown
}

export interface SourceBlock {
  text: string
  block_type: string
  page_number?: number | null
  section_title?: string | null
  evidence?: {
    asset_paths?: {
      img_path?: string
      table_img_path?: string
      equation_img_path?: string
    }
    table_html?: string
    [key: string]: unknown
  }
  html?: string
  [key: string]: unknown
}

export interface EmbeddingSummary {
  status: string
  total_chunks: number
  knowledge_count: number
  ready_count: number
  stale_count: number
  failed_count: number
  pending_count: number
  missing_count: number
}

export interface ImportListResponse {
  items: ImportFile[]
  status_counts?: Record<string, number>
  total?: number
}

export interface ImportChunkListResponse {
  items: ImportChunk[]
  file?: ImportFile
}

export interface MessagesResponse {
  messages?: string[]
  [key: string]: unknown
}

// FAQ

export interface Faq {
  id: string
  question: string
  answer: string
  question_variants: string[]
  tags: string[]
  category: string | null
  status: string
  confidence: string | null
  embedding_status: string
  embedding_model: string | null
  embedding_dimensions: number | null
  embedding_updated_at: string | null
  created_at: string
  updated_at: string
  [key: string]: unknown
}

export interface FaqListResponse {
  items: Faq[]
  total: number
  status_counts?: Record<string, number>
}

// Assistant

export interface AssistantSource {
  id?: string
  source_id?: string
  source_type?: 'document' | 'faq' | string
  source_chunk_id?: string
  parent_chunk_id?: string
  chunk_level?: 'parent' | 'child' | 'chunk' | string
  chunk_id?: string
  source_title?: string
  title?: string
  // 正文：document 切片时是切片文本；FAQ 时是 answer。
  content?: string
  text?: string
  question?: string
  answer?: string
  category?: string | null
  tags?: string[]
  score?: number
  retrieval_channels?: string[]
  metadata?: Record<string, unknown> & { parent_content?: string; file_name?: string }
  [key: string]: unknown
}

export interface AssistantStreamPayload {
  question: string
  conversation_id?: string
  system_prompt?: string
  // 单次请求覆盖供应商；三件套齐了后端会临时构造 ChatClient，否则走全局默认。
  chat_base_url?: string
  chat_api_key?: string
  chat_model?: string
}

export interface AssistantSettingsSnapshot {
  chat_base_url?: string
  chat_api_key?: string
  chat_model?: string
  [key: string]: unknown
}

export interface ProviderProbeResponse {
  ok: boolean
  latency_ms?: number
  model?: string
  sample?: string
  error?: string
}

export interface ProviderModel {
  id: string
  owned_by?: string
}

export interface ProviderModelsResponse {
  ok: boolean
  items: ProviderModel[]
  error?: string
}
