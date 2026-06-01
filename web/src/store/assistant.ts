// 智能问答 store：会话/消息/供应商配置/模型列表缓存/调试抽屉开关，全部走 zustand persist 落 localStorage。
// 设计原则：会话级供应商 override 可以留空，留空则发送时不附带 chat_base_url/chat_api_key/chat_model，后端回退到全局默认。
import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { ProviderModel, AssistantSource } from '@/api/schemas'
import type { AssistantStepEvent } from '@/lib/sse-assistant'

export interface ProviderConfig {
  presetId?: string
  chat_base_url: string
  chat_api_key: string
  chat_model: string
}

export const EMPTY_PROVIDER: ProviderConfig = {
  presetId: '',
  chat_base_url: '',
  chat_api_key: '',
  chat_model: '',
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  streaming?: boolean
  sources?: AssistantSource[]
  steps?: AssistantStepEvent[]
  error?: string
  createdAt: number
}

export interface Conversation {
  id: string
  title: string
  provider: ProviderConfig
  messages: ChatMessage[]
  createdAt: number
  updatedAt: number
}

// 把同一对 base_url+api_key 看成同一个供应商账户，模型列表按此缓存复用。
export function providerFingerprint(base_url: string, api_key: string): string {
  return `${base_url.trim()}::${api_key.trim()}`
}

interface AssistantState {
  conversations: Record<string, Conversation>
  conversationOrder: string[]
  currentId: string | null
  modelsCache: Record<string, { items: ProviderModel[]; fetchedAt: number }>
  debugDrawerOpen: boolean

  newConversation: (provider?: Partial<ProviderConfig>) => string
  selectConversation: (id: string) => void
  renameConversation: (id: string, title: string) => void
  deleteConversation: (id: string) => void
  updateProvider: (id: string, patch: Partial<ProviderConfig>) => void
  appendMessage: (id: string, msg: ChatMessage) => void
  patchMessage: (id: string, msgId: string, patch: Partial<ChatMessage>) => void
  setMessageStreaming: (id: string, msgId: string, streaming: boolean) => void
  cacheModels: (fingerprint: string, items: ProviderModel[]) => void
  toggleDebugDrawer: () => void
  setDebugDrawerOpen: (open: boolean) => void
}

function genId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID()
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
}

export const useAssistant = create<AssistantState>()(
  persist(
    (set, get) => ({
      conversations: {},
      conversationOrder: [],
      currentId: null,
      modelsCache: {},
      debugDrawerOpen: false,

      newConversation: (provider) => {
        const id = genId()
        const now = Date.now()
        const conv: Conversation = {
          id,
          title: '新会话',
          provider: { ...EMPTY_PROVIDER, ...(provider || {}) },
          messages: [],
          createdAt: now,
          updatedAt: now,
        }
        set((s) => ({
          conversations: { ...s.conversations, [id]: conv },
          conversationOrder: [id, ...s.conversationOrder.filter((x) => x !== id)],
          currentId: id,
        }))
        return id
      },

      selectConversation: (id) => set({ currentId: id }),

      renameConversation: (id, title) =>
        set((s) => {
          const conv = s.conversations[id]
          if (!conv) return s
          return {
            conversations: {
              ...s.conversations,
              [id]: { ...conv, title, updatedAt: Date.now() },
            },
          }
        }),

      deleteConversation: (id) =>
        set((s) => {
          const next = { ...s.conversations }
          delete next[id]
          const order = s.conversationOrder.filter((x) => x !== id)
          const currentId = s.currentId === id ? (order[0] ?? null) : s.currentId
          return { conversations: next, conversationOrder: order, currentId }
        }),

      updateProvider: (id, patch) =>
        set((s) => {
          const conv = s.conversations[id]
          if (!conv) return s
          return {
            conversations: {
              ...s.conversations,
              [id]: {
                ...conv,
                provider: { ...conv.provider, ...patch },
                updatedAt: Date.now(),
              },
            },
          }
        }),

      appendMessage: (id, msg) =>
        set((s) => {
          const conv = s.conversations[id]
          if (!conv) return s
          return {
            conversations: {
              ...s.conversations,
              [id]: {
                ...conv,
                messages: [...conv.messages, msg],
                updatedAt: Date.now(),
              },
            },
            conversationOrder: [id, ...s.conversationOrder.filter((x) => x !== id)],
          }
        }),

      patchMessage: (id, msgId, patch) =>
        set((s) => {
          const conv = s.conversations[id]
          if (!conv) return s
          return {
            conversations: {
              ...s.conversations,
              [id]: {
                ...conv,
                messages: conv.messages.map((m) =>
                  m.id === msgId ? { ...m, ...patch } : m,
                ),
                updatedAt: Date.now(),
              },
            },
          }
        }),

      setMessageStreaming: (id, msgId, streaming) =>
        get().patchMessage(id, msgId, { streaming }),

      cacheModels: (fingerprint, items) =>
        set((s) => ({
          modelsCache: {
            ...s.modelsCache,
            [fingerprint]: { items, fetchedAt: Date.now() },
          },
        })),

      toggleDebugDrawer: () => set((s) => ({ debugDrawerOpen: !s.debugDrawerOpen })),
      setDebugDrawerOpen: (open) => set({ debugDrawerOpen: open }),
    }),
    {
      name: 'cs-assistant-v1',
      version: 1,
      // 调试抽屉的状态不持久化（每次刷新默认关闭，避免视觉惊讶）。
      partialize: (s) => ({
        conversations: s.conversations,
        conversationOrder: s.conversationOrder,
        currentId: s.currentId,
        modelsCache: s.modelsCache,
      }),
    },
  ),
)

// 厂商预设。新增预设只需在此追加。`base_url` 留空表示纯自定义。
export interface ProviderPreset {
  id: string
  label: string
  base_url: string
  hint?: string
}

export const PROVIDER_PRESETS: ProviderPreset[] = [
  { id: 'openai', label: 'OpenAI', base_url: 'https://api.openai.com/v1' },
  { id: 'deepseek', label: 'DeepSeek', base_url: 'https://api.deepseek.com/v1' },
  { id: 'moonshot', label: 'Moonshot Kimi', base_url: 'https://api.moonshot.cn/v1' },
  {
    id: 'qwen',
    label: '通义千问（DashScope 兼容）',
    base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
  },
  { id: 'zhipu', label: '智谱 GLM', base_url: 'https://open.bigmodel.cn/api/paas/v4' },
  { id: 'custom', label: '自定义', base_url: '', hint: '手动填写 base_url' },
]
