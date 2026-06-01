import { useState } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { FileUpload } from '@/components/shared/file-upload'
import { Button } from '@/components/ui/button'

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  uploading: boolean
  onUpload: (file: File) => Promise<void> | void
}

const ACCEPT = {
  'application/pdf': ['.pdf'],
  'text/markdown': ['.md'],
  'text/plain': ['.txt'],
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
}

export function UploadDialog({ open, onOpenChange, uploading, onUpload }: Props) {
  const [picked, setPicked] = useState<File | null>(null)
  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) setPicked(null)
        onOpenChange(o)
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>上传文档</DialogTitle>
          <p className="text-[12px] text-(--color-text-muted)">
            上传后默认不立即解析；进入文档抽屉手动触发解析。
          </p>
        </DialogHeader>
        {picked ? (
          <div className="surface flex items-center justify-between gap-3 rounded-(--radius-control) px-3 py-2.5">
            <div className="min-w-0">
              <div className="truncate text-[13px]">{picked.name}</div>
              <div className="text-[11px] text-(--color-text-faint)">
                {(picked.size / 1024).toFixed(1)} KB
              </div>
            </div>
            <Button variant="ghost" size="sm" onClick={() => setPicked(null)}>
              换一个
            </Button>
          </div>
        ) : (
          <FileUpload accept={ACCEPT} onFiles={(files) => setPicked(files[0])} hint="拖文档到此处，或点击选择" />
        )}
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={uploading}>
            取消
          </Button>
          <Button
            variant="primary"
            disabled={!picked || uploading}
            onClick={() => picked && onUpload(picked)}
          >
            {uploading ? '上传中…' : '上传'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
