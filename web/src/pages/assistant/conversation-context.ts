import type { ChatMessage } from '@/store/assistant'
import type { AssistantConversationContext } from '@/api/schemas'

export const ASSISTANT_CONTEXT_RECENT_TURNS = 5
const ASSISTANT_CONTEXT_RECENT_MESSAGE_LIMIT = 1200
const ASSISTANT_CONTEXT_SUMMARY_ITEM_LIMIT = 120
const ASSISTANT_CONTEXT_SUMMARY_LIMIT = 1200

type ConversationContextMessage = NonNullable<
  AssistantConversationContext['recent_messages']
>[number]

// 压缩文本空白，关键约束是只整理格式，不改变用户或助手原意。
function compactText(value: string): string {
  return value.replace(/\s+/g, ' ').trim()
}

// 截断上下文文本，关键约束是控制 payload 大小并显式标记被截断。
function truncateText(value: string, maxLength: number): string {
  const compact = compactText(value)
  if (compact.length <= maxLength) return compact
  return `${compact.slice(0, Math.max(0, maxLength - 3)).trimEnd()}...`
}

// 将历史消息整理成可发送给后端的简版上下文，关键约束是最近 5 轮保留原文，更早消息只保留摘要。
export function buildAssistantConversationContext(
  messages: ChatMessage[],
): AssistantConversationContext | undefined {
  const usableMessages = messages
    .filter((message) => !message.streaming)
    .map((message) => ({
      role: message.role,
      content: compactText(message.content),
      createdAt: message.createdAt,
    }))
    .filter((message) => message.content.length > 0)
    .sort((a, b) => a.createdAt - b.createdAt)

  if (usableMessages.length === 0) return undefined

  const recentLimit = ASSISTANT_CONTEXT_RECENT_TURNS * 2
  const olderMessages = usableMessages.slice(0, Math.max(0, usableMessages.length - recentLimit))
  const recentMessages = usableMessages.slice(-recentLimit)

  const recent: ConversationContextMessage[] = recentMessages.map((message) => ({
    role: message.role,
    content: truncateText(message.content, ASSISTANT_CONTEXT_RECENT_MESSAGE_LIMIT),
  }))

  const summary = olderMessages
    .map((message) => {
      const label = message.role === 'user' ? '用户' : '助手'
      return `${label}：${truncateText(message.content, ASSISTANT_CONTEXT_SUMMARY_ITEM_LIMIT)}`
    })
    .join('；')

  const context: AssistantConversationContext = { recent_messages: recent }
  const truncatedSummary = truncateText(summary, ASSISTANT_CONTEXT_SUMMARY_LIMIT)
  if (truncatedSummary) context.summary = truncatedSummary
  return context
}
