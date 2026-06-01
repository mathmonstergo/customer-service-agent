import { create } from 'zustand'

interface UiState {
  sidebarCollapsed: boolean
  toggleSidebar: () => void

  // 当前打开的文档抽屉对应 file id（null = 关闭）
  openImportFileId: string | null
  setOpenImportFileId: (id: string | null) => void

  // 当前选中的切片下标（per file 局部）
  currentChunkIndex: number
  setCurrentChunkIndex: (i: number) => void

  // 切片编辑模式
  chunkEditMode: boolean
  setChunkEditMode: (v: boolean) => void

  // 当前编辑的 FAQ id
  openFaqId: string | null
  setOpenFaqId: (id: string | null) => void

  // FAQ 草稿（用于检测未保存）
  faqDirty: boolean
  setFaqDirty: (v: boolean) => void
}

export const useUi = create<UiState>((set) => ({
  sidebarCollapsed: false,
  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),

  openImportFileId: null,
  setOpenImportFileId: (id) => set({ openImportFileId: id, currentChunkIndex: 0, chunkEditMode: false }),

  currentChunkIndex: 0,
  setCurrentChunkIndex: (i) => set({ currentChunkIndex: i, chunkEditMode: false }),

  chunkEditMode: false,
  setChunkEditMode: (v) => set({ chunkEditMode: v }),

  openFaqId: null,
  setOpenFaqId: (id) => set({ openFaqId: id, faqDirty: false }),

  faqDirty: false,
  setFaqDirty: (v) => set({ faqDirty: v }),
}))
