export interface MessageNavigationSource {
  id: string
  role: 'user' | 'assistant'
  content: string
  createdAt: number
}

export interface MessageNavigationItem {
  id: string
  label: string
  summary: string
  role: 'user' | 'assistant'
  index: number
}

export interface MessageNavigationPosition {
  id: string
  offsetTop: number
}

export interface ActiveMessageNavigationInput {
  items: MessageNavigationItem[]
  positions: MessageNavigationPosition[]
  scrollTop: number
  clientHeight: number
  scrollHeight: number
  bottomThreshold?: number
  scrollDirection?: 'up' | 'down' | 'idle'
}

// 生成右侧定位列表摘要，关键约束是单行、短文本，避免 hover 面板撑宽或换行过多。
export function summarizeMessageContent(
  content: string,
  role: 'user' | 'assistant',
  maxLength = 34,
): string {
  const compact = content.replace(/\s+/g, ' ').trim()
  if (!compact) return role === 'user' ? '空问题' : '助手正在生成回答'
  if (compact.length <= maxLength) return compact
  return `${compact.slice(0, Math.max(0, maxLength - 3))}...`
}

// 将用户提问转成定位项，关键约束是右侧导航只展示用户问题，不暴露 AI 回答内容。
export function buildMessageNavItems(messages: MessageNavigationSource[]): MessageNavigationItem[] {
  return messages
    .filter((message) => message.role === 'user')
    .map((message, index) => ({
      id: message.id,
      role: message.role,
      label: '我',
      summary: summarizeMessageContent(message.content, message.role),
      index: index + 1,
    }))
}

// 从完整消息列表抽样右侧短横线，关键约束是最多 20 个，并保留首尾定位感。
export function selectMessageRailItems(
  items: MessageNavigationItem[],
  maxItems = 20,
): MessageNavigationItem[] {
  if (items.length <= maxItems) return items
  const lastIndex = items.length - 1
  const selected: MessageNavigationItem[] = []
  const used = new Set<string>()
  for (let i = 0; i < maxItems; i += 1) {
    const sourceIndex = Math.round((i * lastIndex) / (maxItems - 1))
    const item = items[sourceIndex]
    if (item && !used.has(item.id)) {
      selected.push(item)
      used.add(item.id)
    }
  }
  return selected
}

// 计算当前高亮的问题定位项；关键约束是按滚动方向使用顶部/底部边界推进，短内容同屏时也不跳过相邻问题。
export function selectActiveMessageNavigationId(
  input: ActiveMessageNavigationInput,
): string | null {
  const first = input.items[0]
  if (!first) return null
  const edgeThreshold = input.bottomThreshold ?? 24
  if (input.scrollTop <= edgeThreshold) return first.id
  const last = input.items.at(-1)
  const distanceToBottom = input.scrollHeight - input.scrollTop - input.clientHeight
  if (last && distanceToBottom <= edgeThreshold) return last.id

  const positionsById = new Map(input.positions.map((position) => [position.id, position.offsetTop]))
  const activationEdge =
    input.scrollDirection === 'up'
      ? input.scrollTop + input.clientHeight - edgeThreshold
      : input.scrollTop + edgeThreshold
  let currentId = first.id
  for (const item of input.items) {
    const offsetTop = positionsById.get(item.id)
    if (offsetTop === undefined) continue
    if (offsetTop <= activationEdge) currentId = item.id
    else break
  }
  return currentId
}
