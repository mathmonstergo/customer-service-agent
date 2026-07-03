export type MessageStreamScrollInput = {
  didConversationChange: boolean
  distanceToBottom: number
  lastMessageRole: 'user' | 'assistant'
}

// 判断消息流是否应自动滚到最新，关键约束是切换会话必须重置到底部，但同会话内远离底部阅读时不追随助手流式更新。
export function shouldAutoScrollMessageStream(input: MessageStreamScrollInput): boolean {
  if (input.didConversationChange) return true
  if (input.lastMessageRole === 'user') return true
  return input.distanceToBottom < 160
}
