import { useEffect, type RefObject } from 'react'

// 鼠标垂直滚轮 → 横向滚动。仅当容器有横向溢出且事件不会越界时劫持，
// 边界处或纯水平触控板手势放行，避免吞掉外层垂直滚动。
export function useHorizontalWheelScroll<T extends HTMLElement>(
  ref: RefObject<T | null>,
) {
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const onWheel = (e: WheelEvent) => {
      if (Math.abs(e.deltaX) > Math.abs(e.deltaY)) return
      if (e.deltaY === 0) return
      const max = el.scrollWidth - el.clientWidth
      if (max <= 0) return
      if (e.deltaY < 0 && el.scrollLeft <= 0) return
      if (e.deltaY > 0 && el.scrollLeft >= max) return
      e.preventDefault()
      el.scrollLeft = Math.max(0, Math.min(max, el.scrollLeft + e.deltaY))
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  }, [ref])
}
