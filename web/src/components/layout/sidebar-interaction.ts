// 主功能区点击策略；关键约束是内部点击只展开，折叠只由外部点击触发。
export function nextSidebarCollapsedForPointerDown({
  isInsideSidebar,
}: {
  isInsideSidebar: boolean
}): boolean {
  return !isInsideSidebar
}
