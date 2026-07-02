import assert from 'node:assert/strict'
import test from 'node:test'
import {
  buildMessageNavItems,
  selectMessageRailItems,
  summarizeMessageContent,
} from './message-navigation.ts'

test('summarizes user and assistant messages with readable fallbacks', () => {
  assert.equal(summarizeMessageContent('  你好，帮我查一下政策  ', 'user'), '你好，帮我查一下政策')
  assert.equal(summarizeMessageContent('', 'assistant'), '助手正在生成回答')
  assert.equal(summarizeMessageContent('', 'user'), '空问题')
})

test('summarizes long and multi-line messages into one compact line', () => {
  const text = '第一行\n第二行内容非常长，需要被压缩成一条适合右侧列表展示的摘要'

  assert.equal(
    summarizeMessageContent(text, 'assistant', 18),
    '第一行 第二行内容非常长，需要...',
  )
})

test('builds navigation items and caps rail markers at twenty', () => {
  const messages = Array.from({ length: 45 }, (_, i) => ({
    id: `m${i + 1}`,
    role: i % 2 === 0 ? 'user' as const : 'assistant' as const,
    content: `第 ${i + 1} 条消息`,
    createdAt: i,
  }))
  const items = buildMessageNavItems(messages)
  const rails = selectMessageRailItems(items, 20)

  assert.equal(items.length, 23)
  assert.equal(items[0]?.summary, '第 1 条消息')
  assert.equal(items[1]?.summary, '第 3 条消息')
  assert.equal(rails.length, 20)
  assert.equal(rails[0]?.id, 'm1')
  assert.equal(rails.at(-1)?.id, 'm45')
  assert.ok(new Set(rails.map((item) => item.id)).size === rails.length)
})
