import assert from 'node:assert/strict'
import test from 'node:test'
import {
  ASSISTANT_CONTEXT_RECENT_TURNS,
  buildAssistantConversationContext,
} from './conversation-context.ts'

test('builds no conversation context when there is no usable history', () => {
  assert.equal(buildAssistantConversationContext([]), undefined)
})

test('keeps the latest five turns as original messages and summarizes older messages', () => {
  const messages = Array.from({ length: 14 }, (_, index) => ({
    id: `m${index + 1}`,
    role: index % 2 === 0 ? 'user' as const : 'assistant' as const,
    content: `第 ${index + 1} 条内容`,
    createdAt: index,
  }))

  const context = buildAssistantConversationContext(messages)

  assert.equal(ASSISTANT_CONTEXT_RECENT_TURNS, 5)
  assert.ok(context)
  assert.equal(context.recent_messages.length, 10)
  assert.equal(context.recent_messages[0]?.content, '第 5 条内容')
  assert.equal(context.recent_messages.at(-1)?.content, '第 14 条内容')
  assert.ok(context.summary?.includes('用户：第 1 条内容'))
  assert.ok(context.summary?.includes('助手：第 4 条内容'))
})

test('skips streaming placeholders and trims long recent messages', () => {
  const context = buildAssistantConversationContext([
    { id: 'u1', role: 'user', content: '  你好  ', createdAt: 1 },
    { id: 'a1', role: 'assistant', content: '', streaming: true, createdAt: 2 },
    { id: 'u2', role: 'user', content: 'x'.repeat(1600), createdAt: 3 },
  ])

  assert.ok(context)
  assert.equal(context.recent_messages.length, 2)
  assert.equal(context.recent_messages[0]?.content, '你好')
  assert.equal(context.recent_messages[1]?.content.length, 1200)
})
