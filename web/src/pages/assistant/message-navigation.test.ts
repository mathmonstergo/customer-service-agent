import assert from 'node:assert/strict'
import test from 'node:test'
import {
  buildMessageNavItems,
  selectActiveMessageNavigationId,
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

test('selects the last navigation item when the message stream is already at bottom', () => {
  const items = [
    { id: 'q1', role: 'user' as const, label: '我', summary: '第一问', index: 1 },
    { id: 'q2', role: 'user' as const, label: '我', summary: '第二问', index: 2 },
    { id: 'q3', role: 'user' as const, label: '我', summary: '第三问', index: 3 },
  ]

  assert.equal(
    selectActiveMessageNavigationId({
      items,
      positions: [
        { id: 'q1', offsetTop: 120 },
        { id: 'q2', offsetTop: 900 },
        { id: 'q3', offsetTop: 1540 },
      ],
      scrollTop: 1200,
      clientHeight: 500,
      scrollHeight: 1700,
    }),
    'q3',
  )
})

test('keeps the first navigation item reachable at the top of the message stream', () => {
  const items = [
    { id: 'q1', role: 'user' as const, label: '我', summary: '第一问', index: 1 },
    { id: 'q2', role: 'user' as const, label: '我', summary: '第二问', index: 2 },
    { id: 'q3', role: 'user' as const, label: '我', summary: '第三问', index: 3 },
  ]

  assert.equal(
    selectActiveMessageNavigationId({
      items,
      positions: [
        { id: 'q1', offsetTop: 80 },
        { id: 'q2', offsetTop: 260 },
        { id: 'q3', offsetTop: 900 },
      ],
      scrollTop: 0,
      clientHeight: 500,
      scrollHeight: 1400,
    }),
    'q1',
  )
})

test('advances to the next item only after it reaches the top boundary while scrolling down', () => {
  const items = [
    { id: 'q1', role: 'user' as const, label: '我', summary: '倒数第三问', index: 1 },
    { id: 'q2', role: 'user' as const, label: '我', summary: '倒数第二问', index: 2 },
    { id: 'q3', role: 'user' as const, label: '我', summary: '最后一问', index: 3 },
  ]

  assert.equal(
    selectActiveMessageNavigationId({
      items,
      positions: [
        { id: 'q1', offsetTop: 800 },
        { id: 'q2', offsetTop: 1500 },
        { id: 'q3', offsetTop: 2300 },
      ],
      scrollTop: 1350,
      clientHeight: 700,
      scrollHeight: 2800,
      scrollDirection: 'down',
    }),
    'q1',
  )
})

test('does not skip short questions while scrolling down through dense messages', () => {
  const items = [
    { id: 'q1', role: 'user' as const, label: '我', summary: '短问题一', index: 1 },
    { id: 'q2', role: 'user' as const, label: '我', summary: '短问题二', index: 2 },
    { id: 'q3', role: 'user' as const, label: '我', summary: '短问题三', index: 3 },
  ]

  assert.equal(
    selectActiveMessageNavigationId({
      items,
      positions: [
        { id: 'q1', offsetTop: 20 },
        { id: 'q2', offsetTop: 120 },
        { id: 'q3', offsetTop: 180 },
      ],
      scrollTop: 50,
      clientHeight: 500,
      scrollHeight: 900,
      scrollDirection: 'down',
    }),
    'q1',
  )
})

test('does not jump to older questions while scrolling up from a short final answer', () => {
  const items = [
    { id: 'q1', role: 'user' as const, label: '我', summary: '倒数第三问', index: 1 },
    { id: 'q2', role: 'user' as const, label: '我', summary: '倒数第二问', index: 2 },
    { id: 'q3', role: 'user' as const, label: '我', summary: '最后一问', index: 3 },
  ]

  assert.equal(
    selectActiveMessageNavigationId({
      items,
      positions: [
        { id: 'q1', offsetTop: 800 },
        { id: 'q2', offsetTop: 1500 },
        { id: 'q3', offsetTop: 1900 },
      ],
      scrollTop: 1400,
      clientHeight: 700,
      scrollHeight: 2400,
      scrollDirection: 'up',
    }),
    'q3',
  )
})
