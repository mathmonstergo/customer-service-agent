// 发送/停止 SSE 流的钩子。
// 关键约束：
// 1) delta 文本合批写入 store，避免每个 token 触发一次重渲染（用 requestAnimationFrame）；
// 2) 暴露 abort()，让"停止生成"按钮通过 AbortController 中止 fetch，把已收到的内容保留下来。
// 3) 用户没填会话级供应商时，发送 payload 里不带 chat_* 字段，让后端走全局默认。
import { useCallback, useRef, useState } from 'react'
import { toast } from '@/components/ui/toast'
import { streamAssistantChat, type AssistantStepEvent } from '@/lib/sse-assistant'
import type { AssistantSource, AssistantStreamPayload } from '@/api/schemas'
import { useAssistant, type ChatMessage, type ProviderConfig } from '@/store/assistant'

function genId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID()
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
}

function buildPayload(question: string, provider: ProviderConfig): AssistantStreamPayload {
  const payload: AssistantStreamPayload = { question }
  const base_url = provider.chat_base_url.trim()
  const api_key = provider.chat_api_key.trim()
  const model = provider.chat_model.trim()
  if (base_url && api_key && model) {
    payload.chat_base_url = base_url
    payload.chat_api_key = api_key
    payload.chat_model = model
  }
  return payload
}

export function useChatStream() {
  const abortRef = useRef<AbortController | null>(null)
  const [isStreaming, setIsStreaming] = useState(false)

  const send = useCallback(async (conversationId: string, question: string) => {
    const trimmed = question.trim()
    if (!trimmed || isStreaming) return

    const store = useAssistant.getState()
    const conv = store.conversations[conversationId]
    if (!conv) return

    // 用户气泡 + 助手占位气泡（streaming=true，呈现脉冲点）
    const userMsg: ChatMessage = {
      id: genId(),
      role: 'user',
      content: trimmed,
      createdAt: Date.now(),
    }
    const asstId = genId()
    const asstMsg: ChatMessage = {
      id: asstId,
      role: 'assistant',
      content: '',
      streaming: true,
      steps: [],
      createdAt: Date.now(),
    }
    store.appendMessage(conversationId, userMsg)
    store.appendMessage(conversationId, asstMsg)
    // 自动用首问做会话标题（30 字以内）
    if (conv.messages.length === 0 || conv.title === '新会话') {
      store.renameConversation(
        conversationId,
        trimmed.length > 30 ? trimmed.slice(0, 30) + '…' : trimmed,
      )
    }

    const controller = new AbortController()
    abortRef.current = controller
    setIsStreaming(true)

    // delta 合批：每帧 flush 一次，避免 token 级 setState 风暴。
    let buffered = ''
    let rafId: number | null = null
    const flush = () => {
      rafId = null
      if (!buffered) return
      const chunk = buffered
      buffered = ''
      const cur = useAssistant.getState().conversations[conversationId]
      const msg = cur?.messages.find((m) => m.id === asstId)
      if (!msg) return
      useAssistant.getState().patchMessage(conversationId, asstId, {
        content: msg.content + chunk,
      })
    }
    const enqueueDelta = (text: string) => {
      buffered += text
      if (rafId == null) rafId = requestAnimationFrame(flush)
    }

    const steps: AssistantStepEvent[] = []

    try {
      await streamAssistantChat({
        payload: buildPayload(trimmed, conv.provider),
        signal: controller.signal,
        onEvent: (e) => {
          if (e.type === 'delta') {
            enqueueDelta(e.text)
          } else if (e.type === 'step') {
            // 按 step_id 去重更新而非 append：同一节点的 running→completed
            // 状态切换会替换原有条目，避免出现两个"生成回答"卡片（一个 running 一个 completed）。
            const idx = steps.findIndex((s) => s.step_id === e.step_id)
            if (idx >= 0) steps[idx] = e
            else steps.push(e)
            useAssistant.getState().patchMessage(conversationId, asstId, { steps: [...steps] })
          } else if (e.type === 'done') {
            // 用 done.answer_draft 兜底（兜住 delta 全为空的边界）
            if (rafId != null) {
              cancelAnimationFrame(rafId)
              rafId = null
            }
            const remain = buffered
            buffered = ''
            const cur = useAssistant.getState().conversations[conversationId]
            const existing = cur?.messages.find((m) => m.id === asstId)?.content ?? ''
            const finalText = existing + remain || e.answer_draft || ''
            useAssistant.getState().patchMessage(conversationId, asstId, {
              content: finalText,
              sources: (e.documents as AssistantSource[]) ?? [],
              streaming: false,
            })
          } else if (e.type === 'error') {
            const msg = e.error || e.message || '生成失败'
            useAssistant.getState().patchMessage(conversationId, asstId, {
              streaming: false,
              error: String(msg),
            })
            toast.error(`生成失败：${msg}`)
          }
        },
      })
    } catch (err) {
      const aborted = (err as { name?: string } | null)?.name === 'AbortError'
      if (rafId != null) {
        cancelAnimationFrame(rafId)
        rafId = null
      }
      const remain = buffered
      buffered = ''
      const cur = useAssistant.getState().conversations[conversationId]
      const existing = cur?.messages.find((m) => m.id === asstId)?.content ?? ''
      if (aborted) {
        useAssistant.getState().patchMessage(conversationId, asstId, {
          content: existing + remain,
          streaming: false,
          error: '已停止生成',
        })
        toast('已停止生成')
      } else {
        const msg = (err as Error)?.message || '请求失败'
        useAssistant.getState().patchMessage(conversationId, asstId, {
          content: existing + remain,
          streaming: false,
          error: msg,
        })
        toast.error(msg)
      }
    } finally {
      setIsStreaming(false)
      abortRef.current = null
    }
  }, [isStreaming])

  const abort = useCallback(() => {
    abortRef.current?.abort()
  }, [])

  return { send, abort, isStreaming }
}
