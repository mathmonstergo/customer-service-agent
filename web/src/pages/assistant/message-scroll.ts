export type MessageStreamScrollInput = {
  didConversationChange: boolean
  distanceToBottom: number
  lastMessageRole: 'user' | 'assistant'
}

export type MessageStreamScrollPlan = {
  shouldScroll: boolean
  behavior: ScrollBehavior
  followUpFrame: boolean
}

// 判断消息流是否应自动滚到最新，关键约束是切换会话必须重置到底部，但同会话内远离底部阅读时不追随助手流式更新。
export function shouldAutoScrollMessageStream(input: MessageStreamScrollInput): boolean {
  if (input.didConversationChange) return true
  if (input.lastMessageRole === 'user') return true
  return input.distanceToBottom < 160
}

// 生成消息流滚动计划；关键约束是切换会话时下一帧再校正一次，覆盖延迟布局。
export function messageStreamScrollPlan(input: MessageStreamScrollInput): MessageStreamScrollPlan {
  return {
    shouldScroll: shouldAutoScrollMessageStream(input),
    behavior: input.didConversationChange ? 'auto' : 'smooth',
    followUpFrame: input.didConversationChange,
  }
}
