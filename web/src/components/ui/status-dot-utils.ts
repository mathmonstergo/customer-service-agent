export type DotTone = 'pending' | 'ready' | 'warning' | 'stale' | 'failed' | 'muted'

// 导出给横滚轴等紧凑场景复用，保证圆点配色与状态点一致。
// 一色一态：未索引灰 · 已索引绿 · 部分索引黄 · 过期橙 · 失败红 · 禁用灰。
export const TONE_COLOR: Record<DotTone, string> = {
  pending: 'bg-(--color-text-faint)',
  ready: 'bg-(--color-success)',
  warning: 'bg-(--color-warning)',
  stale: 'bg-(--color-stale)',
  failed: 'bg-(--color-danger)',
  muted: 'bg-(--color-text-faint)',
}

// 统一的「embedding 状态 → 圆点色」映射，供切片 / FAQ 各处复用，保证一色一态一致。
// 禁用（文件层 / 切片层 / FAQ）→ 灰并覆盖一切；已索引→绿、过期→橙、失败→红、部分→黄、未索引/未生成→灰。
export function embedDotTone(embeddingStatus: string | undefined, disabled?: boolean): DotTone {
  if (disabled) return 'muted'
  switch (embeddingStatus) {
    case 'ready':
      return 'ready'
    case 'stale':
      return 'stale'
    case 'failed':
      return 'failed'
    case 'partial':
      return 'warning'
    default:
      return 'pending'
  }
}
