import { useState } from 'react'
import { Search, Upload, X } from 'lucide-react'
import { useImportFiles, useUploadImportFile } from '@/api/hooks'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { toast } from '@/components/ui/toast'
import { useUi } from '@/store/ui'
import { DocumentList } from './documents/document-list'
import { DocumentDrawer } from './documents/document-drawer'
import { UploadDialog } from './documents/upload-dialog'

const STATUS_OPTIONS: { value: string; label: string }[] = [
  { value: '', label: '全部' },
  { value: 'pending', label: '待解析' },
  { value: 'processing', label: '解析中' },
  { value: 'needs_review', label: '待复核' },
  { value: 'completed', label: '已完成' },
  { value: 'failed', label: '失败' },
]

export default function DocumentsPage() {
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('')
  const [uploadOpen, setUploadOpen] = useState(false)
  const { openImportFileId, setOpenImportFileId } = useUi()
  const { data, isPending, isError, refetch } = useImportFiles(
    { query, status },
    {
      // 有 parsing 才轮询，没事不打扰
      refetchInterval: (q) =>
        q.state.data?.items?.some((f) => f.status === 'processing') ? 2000 : false,
    },
  )
  const items = data?.items || []
  const hasParsing = items.some((f) => f.status === 'processing')
  const upload = useUploadImportFile()

  return (
    <div className="flex h-full flex-col">
      {/* 顶部工具栏 */}
      <div className="flex shrink-0 items-center gap-2 border-b border-(--color-border) px-6 py-3">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 size-3.5 text-(--color-text-faint)" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="搜文件名…"
            className="pl-7"
          />
          {query && (
            <button
              type="button"
              onClick={() => setQuery('')}
              className="absolute right-1 top-1/2 -translate-y-1/2 inline-flex size-6 items-center justify-center rounded text-(--color-text-faint) hover:text-(--color-text)"
            >
              <X className="size-3" />
            </button>
          )}
        </div>
        <StatusFilter value={status} onChange={setStatus} />
        <div className="ml-auto" />
        {hasParsing && (
          <span className="text-[11px] text-(--color-text-faint)">实时同步中…</span>
        )}
        <Button variant="primary" onClick={() => setUploadOpen(true)}>
          <Upload className="size-3.5" />
          上传文档
        </Button>
      </div>

      {/* 主列表 */}
      <div className="min-h-0 flex-1 overflow-y-auto scroll-thin px-6 py-4">
        <DocumentList
          items={items}
          isPending={isPending}
          isError={isError}
          onRetry={() => refetch()}
          onSelect={(id) => setOpenImportFileId(id)}
        />
      </div>

      <UploadDialog
        open={uploadOpen}
        onOpenChange={setUploadOpen}
        uploading={upload.isPending}
        onUpload={async (file) => {
          try {
            const uploaded = await upload.mutateAsync({ file })
            toast.success(`已上传「${uploaded.original_name}」`)
            setUploadOpen(false)
            // 自动打开新文档抽屉，方便用户接着触发解析
            if (uploaded.id) setOpenImportFileId(uploaded.id)
          } catch (e) {
            toast.error((e as Error).message)
          }
        }}
      />

      <DocumentDrawer
        fileId={openImportFileId}
        onClose={() => setOpenImportFileId(null)}
      />
    </div>
  )
}

function StatusFilter({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <div className="flex items-center gap-1 rounded-(--radius-control) bg-(--color-surface-2) border border-(--color-border) p-0.5">
      {STATUS_OPTIONS.map((opt) => (
        <button
          key={opt.value}
          type="button"
          onClick={() => onChange(opt.value)}
          className={`rounded-(--radius-control) px-2 py-1 text-[12px] transition-colors ${
            value === opt.value
              ? 'bg-(--color-surface-3) text-(--color-text)'
              : 'text-(--color-text-muted) hover:text-(--color-text)'
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  )
}
