import {
  useIsMutating,
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query'
import { requestJson } from './client'
import type {
  AssistantSettingsSnapshot,
  Faq,
  FaqListResponse,
  ImportChunkListResponse,
  ImportFile,
  ImportListResponse,
  MessagesResponse,
  ProviderModelsResponse,
  ProviderProbeResponse,
  RetrievalAlias,
  RetrievalAliasListResponse,
  RetrievalEvalCase,
  RetrievalEvalCaseListResponse,
  RetrievalEvalRun,
} from './schemas'

// ───── 文档 / Import ─────

export interface ImportListParams {
  query?: string
  status?: string
  limit?: number
  offset?: number
}

export function useImportFiles(
  params: ImportListParams = {},
  options?: {
    refetchInterval?:
      | number
      | false
      | ((q: { state: { data?: ImportListResponse } }) => number | false | undefined)
  },
) {
  return useQuery({
    queryKey: ['import-files', params],
    queryFn: () =>
      requestJson<ImportListResponse>('/api/import/files', {
        query: { ...params, limit: params.limit ?? 100 },
      }),
    staleTime: 10_000,
    refetchInterval: options?.refetchInterval as never,
  })
}

export function useImportFileParseStatus(
  fileId: string | null,
  options?: {
    refetchInterval?:
      | number
      | false
      | ((q: { state: { data?: ParseStatusResponse } }) => number | false | undefined)
  },
) {
  return useQuery({
    queryKey: ['import-parse-status', fileId],
    queryFn: () =>
      requestJson<ParseStatusResponse>(
        `/api/import/files/${encodeURIComponent(fileId!)}/parse-status`,
      ),
    enabled: !!fileId,
    refetchInterval: options?.refetchInterval as never,
    staleTime: 0,
  })
}

export interface ParseStatusResponse {
  file: ImportFile
  status: string
  state: string
  progress: Record<string, unknown> & {
    state?: string
    stage?: string
    message?: string
    current?: number
    total?: number
  }
  percent: number
  error: string | null
}

export function useImportFileChunks(
  fileId: string | null,
  options?: { refetchInterval?: number },
) {
  return useQuery({
    queryKey: ['import-chunks', fileId],
    queryFn: () =>
      requestJson<ImportChunkListResponse>(
        `/api/import/files/${encodeURIComponent(fileId!)}/chunks`,
      ),
    enabled: !!fileId,
    refetchInterval: options?.refetchInterval,
  })
}

export function useDeleteImportFile() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) =>
      requestJson<MessagesResponse>(`/api/import/files/${encodeURIComponent(id)}`, {
        method: 'DELETE',
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['import-files'] }),
  })
}

export function useEmbedImportFile() {
  const qc = useQueryClient()
  return useMutation({
    mutationKey: ['embed-import-file'],
    mutationFn: (id: string) =>
      requestJson<MessagesResponse & { count?: number }>(
        `/api/import/files/${encodeURIComponent(id)}/embed`,
        { method: 'POST', body: {} },
      ),
    onSuccess: (_data, id) => {
      qc.invalidateQueries({ queryKey: ['import-files'] })
      qc.invalidateQueries({ queryKey: ['import-chunks', id] })
      qc.invalidateQueries({ queryKey: ['import-parse-status', id] })
    },
  })
}

export function useGenerateImportFileQuestions() {
  const qc = useQueryClient()
  return useMutation({
    mutationKey: ['generate-questions'],
    mutationFn: ({ id, force }: { id: string; force?: boolean }) =>
      requestJson<MessagesResponse>(
        `/api/import/files/${encodeURIComponent(id)}/generate-questions`,
        { method: 'POST', body: { force: !!force } },
      ),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ['import-chunks', vars.id] })
    },
  })
}

export function useStartImportParseJob() {
  const qc = useQueryClient()
  return useMutation({
    mutationKey: ['start-parse-job'],
    mutationFn: ({ id, chunker_type, parser }: { id: string; chunker_type?: string; parser?: string }) =>
      requestJson<MessagesResponse>(
        `/api/import/files/${encodeURIComponent(id)}/parse-jobs`,
        { method: 'POST', body: { ...(parser ? { parser } : {}), ...(chunker_type ? { chunker_type } : {}) } },
      ),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ['import-files'] })
      qc.invalidateQueries({ queryKey: ['import-parse-status', vars.id] })
      qc.invalidateQueries({ queryKey: ['import-chunks', vars.id] })
    },
  })
}

export function useToggleImportFileDisabled() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, is_disabled }: { id: string; is_disabled: boolean }) =>
      requestJson(`/api/import/files/${encodeURIComponent(id)}/disabled`, {
        method: 'POST',
        body: { is_disabled },
      }),
    onMutate: async ({ id, is_disabled }) => {
      await qc.cancelQueries({ queryKey: ['import-files'] })
      const snapshots = qc.getQueriesData<ImportListResponse>({ queryKey: ['import-files'] })
      snapshots.forEach(([key, data]) => {
        if (!data) return
        qc.setQueryData(key, {
          ...data,
          items: data.items.map((f) => (f.id === id ? { ...f, is_disabled } : f)),
        })
      })
      return { snapshots }
    },
    onError: (_err, _vars, ctx) => {
      ctx?.snapshots.forEach(([key, data]) => qc.setQueryData(key, data))
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ['import-files'] }),
  })
}

export function useToggleImportChunkDisabled() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, is_disabled }: { id: string; is_disabled: boolean }) =>
      requestJson(`/api/import/chunks/${encodeURIComponent(id)}/disabled`, {
        method: 'POST',
        body: { is_disabled },
      }),
    onMutate: async ({ id, is_disabled }) => {
      const snapshots = qc.getQueriesData<ImportChunkListResponse>({
        queryKey: ['import-chunks'],
      })
      snapshots.forEach(([key, data]) => {
        if (!data) return
        qc.setQueryData(key, {
          ...data,
          items: data.items.map((c) => (c.id === id ? { ...c, is_disabled } : c)),
        })
      })
      return { snapshots }
    },
    onError: (_err, _vars, ctx) => {
      ctx?.snapshots.forEach(([key, data]) => qc.setQueryData(key, data))
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ['import-chunks'] }),
  })
}

export function useUpdateImportChunk() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, source_text }: { id: string; source_text: string }) =>
      requestJson(`/api/import/chunks/${encodeURIComponent(id)}`, {
        method: 'POST',
        body: { source_text },
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['import-chunks'] }),
  })
}

// 单切片重新生成向量。典型场景：编辑切片原文后 embedding 被标记 stale，用户单独刷新这一片。
export function useEmbedImportChunk() {
  const qc = useQueryClient()
  return useMutation({
    mutationKey: ['embed-import-chunk'],
    mutationFn: (id: string) =>
      requestJson<MessagesResponse & { count?: number; file_id?: string }>(
        `/api/import/chunks/${encodeURIComponent(id)}/embed`,
        { method: 'POST', body: {} },
      ),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['import-files'] })
      if (data?.file_id) {
        qc.invalidateQueries({ queryKey: ['import-chunks', data.file_id] })
        qc.invalidateQueries({ queryKey: ['import-parse-status', data.file_id] })
      } else {
        qc.invalidateQueries({ queryKey: ['import-chunks'] })
      }
    },
  })
}

export function useUploadImportFile() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ file, parse }: { file: File; parse?: boolean }) => {
      const form = new FormData()
      form.append('file', file)
      const query = parse ? '' : '?parse=false'
      return requestJson<ImportFile>(`/api/import/files${query}`, {
        method: 'POST',
        body: form,
      })
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['import-files'] }),
  })
}

// 全局检测某个 fileId 上是否还有任何后台任务（embedding / 假设问题 / 解析 job 提交）在跑。
// 即使抽屉关闭再打开，只要任务没结束，按钮状态就还是 pending。
export function useFilePendingTasks(fileId: string | null) {
  const embedPending = useIsMutating({
    mutationKey: ['embed-import-file'],
    predicate: (m) => m.state.variables === fileId,
  })
  const questionsPending = useIsMutating({
    mutationKey: ['generate-questions'],
    predicate: (m) => (m.state.variables as { id?: string } | undefined)?.id === fileId,
  })
  const parsePending = useIsMutating({
    mutationKey: ['start-parse-job'],
    predicate: (m) => (m.state.variables as { id?: string } | undefined)?.id === fileId,
  })
  return {
    embed: embedPending > 0,
    questions: questionsPending > 0,
    parse: parsePending > 0,
    any: embedPending + questionsPending + parsePending > 0,
  }
}

// ───── FAQ ─────

export interface FaqListParams {
  page?: number
  pageSize?: number
  query?: string
  status?: string
  embedding?: string
}

export function useFaqs(params: FaqListParams = {}) {
  const page = params.page ?? 1
  const pageSize = params.pageSize ?? 30
  return useQuery({
    queryKey: ['faqs', { ...params, page, pageSize }],
    queryFn: () =>
      // 后端用 snake_case `page_size`，不能传驼峰。
      requestJson<FaqListResponse>('/api/faqs', {
        query: {
          query: params.query,
          status: params.status,
          embedding: params.embedding,
          page,
          page_size: pageSize,
        },
      }),
    staleTime: 10_000,
    placeholderData: (prev) => prev,
  })
}

export function useFaq(id: string | null) {
  return useQuery({
    queryKey: ['faq', id],
    queryFn: () => requestJson<Faq>(`/api/faqs/${encodeURIComponent(id!)}`),
    enabled: !!id,
  })
}

export function useSaveFaq() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: Partial<Faq>) =>
      requestJson<Faq>('/api/faqs', { method: 'POST', body: payload }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['faqs'] })
    },
  })
}

export function useEmbedFaq() {
  const qc = useQueryClient()
  return useMutation({
    mutationKey: ['embed-faq'],
    mutationFn: (id: string) =>
      requestJson(`/api/faqs/${encodeURIComponent(id)}/embed`, {
        method: 'POST',
        body: {},
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['faqs'] }),
  })
}

// 批量为所有「非绿」(pending/stale/failed) FAQ 生成 embedding；后端按候选表一次处理（≤200 条）。
export function useEmbedPendingFaqs() {
  const qc = useQueryClient()
  return useMutation({
    mutationKey: ['embed-pending-faqs'],
    mutationFn: (limit: number) =>
      requestJson<{ count?: number; items?: unknown[] }>('/api/faqs/embed-pending', {
        method: 'POST',
        body: { limit },
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['faqs'] }),
  })
}

export interface OptimizeResponse {
  question?: string
  answer?: string
  tags?: string[]
  question_variants?: string[]
  reasoning?: string
  [key: string]: unknown
}

export function useOptimizeFaq() {
  return useMutation({
    mutationKey: ['optimize-faq'],
    mutationFn: (payload: { question: string; answer: string }) =>
      requestJson<OptimizeResponse>('/api/ai/optimize', {
        method: 'POST',
        body: payload,
      }),
  })
}

// ───── Assistant ─────

// 拉取后端 settings 快照，作为会话级供应商表单的"默认值"。
export function useAssistantDefaults() {
  return useQuery({
    queryKey: ['assistant-defaults'],
    queryFn: () => requestJson<AssistantSettingsSnapshot>('/api/settings'),
    staleTime: 60_000,
  })
}

export function useProbeChatProvider() {
  return useMutation({
    mutationKey: ['probe-chat-provider'],
    mutationFn: (body: { chat_base_url: string; chat_api_key: string; chat_model: string }) =>
      requestJson<ProviderProbeResponse>('/api/assistant/probe', {
        method: 'POST',
        body,
      }),
  })
}

export function useListChatProviderModels() {
  return useMutation({
    mutationKey: ['list-chat-provider-models'],
    mutationFn: (body: { chat_base_url: string; chat_api_key: string }) =>
      requestJson<ProviderModelsResponse>('/api/assistant/models', {
        method: 'POST',
        body,
      }),
  })
}

// ───── Retrieval Evaluation ─────

export interface RetrievalEvalCaseListParams {
  status?: string
  limit?: number
  offset?: number
}

// 拉取评测用例列表；queryKey 必须包含筛选参数，避免状态筛选复用旧缓存。
export function useRetrievalEvalCases(params: RetrievalEvalCaseListParams = {}) {
  return useQuery({
    queryKey: ['retrieval-eval-cases', params],
    queryFn: () =>
      requestJson<RetrievalEvalCaseListResponse>('/api/retrieval/eval-cases', {
        query: {
          status: params.status,
          limit: params.limit ?? 100,
          offset: params.offset ?? 0,
        },
      }),
    staleTime: 10_000,
    placeholderData: (prev) => prev,
  })
}

// 保存评测用例；成功后刷新全部评测列表，让 latest_run 和状态保持一致。
export function useSaveRetrievalEvalCase() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: Partial<RetrievalEvalCase>) =>
      requestJson<RetrievalEvalCase>('/api/retrieval/eval-cases', {
        method: 'POST',
        body: payload,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['retrieval-eval-cases'] })
    },
  })
}

// 运行单条评测；成功后刷新用例列表，同时调用方可用返回值即时更新详情区。
export function useRunRetrievalEvalCase() {
  const qc = useQueryClient()
  return useMutation({
    mutationKey: ['run-retrieval-eval-case'],
    mutationFn: (caseId: string) =>
      requestJson<RetrievalEvalRun>(
        `/api/retrieval/eval-cases/${encodeURIComponent(caseId)}/run`,
        { method: 'POST', body: {} },
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['retrieval-eval-cases'] })
    },
  })
}

// 拉取别名词典；当前后端只返回启用词条，用于页面维护和关键词扩展展示。
export function useRetrievalAliases() {
  return useQuery({
    queryKey: ['retrieval-aliases'],
    queryFn: () => requestJson<RetrievalAliasListResponse>('/api/retrieval/aliases'),
    staleTime: 10_000,
  })
}

// 保存别名词条；成功后刷新词典列表，后续评测运行会读取最新启用别名。
export function useSaveRetrievalAlias() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: Partial<RetrievalAlias>) =>
      requestJson<RetrievalAlias>('/api/retrieval/aliases', {
        method: 'POST',
        body: payload,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['retrieval-aliases'] })
    },
  })
}
