// 最近活跃会话排序工具；关键约束是只移动已存在会话，避免脏 id 污染列表。
export function moveConversationIdToFront(order: string[], id: string): string[] {
  if (!order.includes(id)) return order
  return [id, ...order.filter((item) => item !== id)]
}
