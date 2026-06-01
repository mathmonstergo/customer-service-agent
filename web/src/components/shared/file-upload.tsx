import { useCallback } from 'react'
import { useDropzone } from 'react-dropzone'
import { Upload } from 'lucide-react'
import { cn } from '@/lib/cn'

interface Props {
  onFiles: (files: File[]) => void
  accept?: Record<string, string[]>
  multiple?: boolean
  hint?: string
  disabled?: boolean
}

export function FileUpload({
  onFiles,
  accept,
  multiple = false,
  hint = '拖文件到此处，或点击选择',
  disabled,
}: Props) {
  const onDrop = useCallback(
    (files: File[]) => {
      if (files.length) onFiles(files)
    },
    [onFiles],
  )
  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept,
    multiple,
    disabled,
  })
  return (
    <div
      {...getRootProps()}
      className={cn(
        'flex flex-col items-center justify-center gap-2 rounded-(--radius-card) border border-dashed px-6 py-10 text-center transition-colors duration-[120ms]',
        'cursor-pointer select-none',
        isDragActive
          ? 'border-(--color-primary) bg-(--color-primary-soft)'
          : 'border-(--color-border) bg-(--color-surface-2) hover:border-(--color-text-faint)',
        disabled && 'opacity-50 pointer-events-none',
      )}
    >
      <input {...getInputProps()} />
      <Upload className="size-5 text-(--color-text-muted)" />
      <div className="text-[13px] text-(--color-text)">
        {isDragActive ? '松手上传' : hint}
      </div>
      {accept && (
        <div className="text-[11px] text-(--color-text-faint)">
          支持：{Object.values(accept).flat().join(' / ')}
        </div>
      )}
    </div>
  )
}
