import { useEffect, useRef } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { useQueryClient } from '@tanstack/react-query'
import {
  Download,
  Loader2,
  PowerOff,
  Power,
  RotateCw,
  Sparkles,
  Trash2,
  Wand2,
} from 'lucide-react'
import {
  Drawer,
  DrawerBody,
  DrawerContent,
  DrawerHeader,
  DrawerTitle,
} from '@/components/ui/drawer'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { StatusDot } from '@/components/ui/status-dot'
import { Skeleton } from '@/components/ui/skeleton'
import {
  useDeleteImportFile,
  useEmbedImportFile,
  useFilePendingTasks,
  useGenerateImportFileQuestions,
  useImportFileChunks,
  useImportFileParseStatus,
  useStartImportParseJob,
  useToggleImportFileDisabled,
  type ParseStatusResponse,
} from '@/api/hooks'
import { toast } from '@/components/ui/toaster'
import { importFileStatusLabel, parseStateLabel, tr } from '@/lib/labels'
import { dur, ease } from '@/lib/motion'
import { ChunkBrowser } from './chunk-browser'

interface Props {
  fileId: string | null
  onClose: () => void
}

export function DocumentDrawer({ fileId, onClose }: Props) {
  const open = !!fileId
  return (
    <AnimatePresence>
      {open && (
        <Drawer key={fileId} open={open} onOpenChange={(o) => !o && onClose()}>
          <DrawerContent width={820}>
            <DrawerInner fileId={fileId!} onClose={onClose} />
          </DrawerContent>
        </Drawer>
      )}
    </AnimatePresence>
  )
}

function DrawerInner({ fileId, onClose }: { fileId: string; onClose: () => void }) {
  const qc = useQueryClient()
  // 单文件数据源：parse-status 接口返回完整 file 记录 + 进度，且能精确轮询
  const statusQ = useImportFileParseStatus(fileId, {
    refetchInterval: (q) =>
      q.state.data?.file?.status === 'processing' ? 1500 : false,
  })
  const status = statusQ.data
  const file = status?.file

  const isParsing = file?.status === 'processing'
  const chunksQ = useImportFileChunks(fileId, {
    refetchInterval: isParsing ? 3000 : undefined,
  })

  // 跨抽屉持久化的"任务在跑"探测：即使抽屉关闭再打开，只要 mutation 还在跑就显示 spinner
  const pending = useFilePendingTasks(fileId)

  // 解析状态从 processing 离开时，主动再拉一次 chunks 拿最终结果（避免错过轮询窗口）
  const prevStatusRef = useRef<string | undefined>(file?.status)
  useEffect(() => {
    const prev = prevStatusRef.current
    const cur = file?.status
    if (prev === 'processing' && cur && cur !== 'processing') {
      qc.invalidateQueries({ queryKey: ['import-chunks', fileId] })
      qc.invalidateQueries({ queryKey: ['import-files'] })
      if (cur === 'failed') {
        toast.error(`解析失败：${file?.error || '未知错误'}`)
      } else {
        toast.success(`「${file?.original_name || ''}」解析完成`)
      }
    }
    prevStatusRef.current = cur
  }, [file?.status, file?.error, file?.original_name, fileId, qc])

  const parseJob = useStartImportParseJob()
  const embed = useEmbedImportFile()
  const generate = useGenerateImportFileQuestions()
  const toggleDisabled = useToggleImportFileDisabled()
  const del = useDeleteImportFile()

  const isParsed = !!file && ['needs_review', 'completed'].includes(file.status)
  // 该文档下有多少切片处于 stale：embed 过但原文被改过，等待重新生成。
  // 用于在"生成 embedding"按钮上显示橙色数字徽章，提醒用户有内容待刷新。
  const staleCount = (chunksQ.data?.items || []).filter(
    (c) => c.embedding_status === 'stale',
  ).length

  const fireMessages = (messages?: string[]) => (messages || []).forEach((m) => toast(m))

  const onParse = async () => {
    try {
      const r = await parseJob.mutateAsync({ id: fileId })
      fireMessages(r.messages?.length ? r.messages : ['已开始解析'])
    } catch (e) {
      toast.error((e as Error).message)
    }
  }
  const onEmbed = async () => {
    try {
      const r = await embed.mutateAsync(fileId)
      toast.success(`已生成 ${r.count || 0} 个切片 embedding`)
    } catch (e) {
      toast.error((e as Error).message)
    }
  }
  const onGenerate = async () => {
    try {
      const r = await generate.mutateAsync({ id: fileId })
      fireMessages(r.messages)
    } catch (e) {
      toast.error((e as Error).message)
    }
  }
  const onToggleDisabled = () => {
    if (!file) return
    toggleDisabled.mutate({ id: fileId, is_disabled: !file.is_disabled })
  }
  const onDelete = async () => {
    if (!confirm(`确认删除「${file?.original_name || fileId}」？`)) return
    try {
      const r = await del.mutateAsync(fileId)
      fireMessages(r.messages)
      onClose()
    } catch (e) {
      toast.error((e as Error).message)
    }
  }

  if (!file) return <DrawerInnerSkeleton />
  return (
    <>
      <DrawerHeader>
        <div className="min-w-0 flex-1">
          <DrawerTitle className="truncate">{file.original_name}</DrawerTitle>
          <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[12px] text-(--color-text-muted)">
            <Badge tone="muted">{file.file_type}</Badge>
            <Badge tone="muted">{file.parser}</Badge>
            <StatusDot tone={mapStatus(file.status)} label={tr(importFileStatusLabel, file.status, file.status)} />
            {file.is_disabled && <Badge tone="danger">已禁用</Badge>}
          </div>
        </div>
      </DrawerHeader>

      {/* 操作按钮组 */}
      <div className="flex shrink-0 flex-wrap gap-2 border-b border-(--color-border) px-6 py-3">
        <Button onClick={onParse} disabled={pending.parse || isParsing}>
          {isParsing || pending.parse ? (
            <Loader2 className="size-3.5 animate-spin" />
          ) : (
            <RotateCw className="size-3.5" />
          )}
          {isParsing ? '解析中…' : pending.parse ? '提交中…' : '开始解析'}
        </Button>
        <Button
          variant="primary"
          onClick={onEmbed}
          disabled={!isParsed || pending.embed}
          title={
            staleCount > 0
              ? `重新生成全部切片向量（${staleCount} 个切片原文已改，待刷新）`
              : '为所有切片生成向量'
          }
        >
          {pending.embed ? (
            <Loader2 className="size-3.5 animate-spin" />
          ) : (
            <Sparkles className="size-3.5" />
          )}
          {pending.embed ? '生成中…' : '生成 embedding'}
          {staleCount > 0 && !pending.embed && (
            <span className="ml-0.5 inline-flex h-4 min-w-4 items-center justify-center rounded-(--radius-control) bg-(--color-warning)/20 px-1 font-mono text-[10px] text-(--color-warning)">
              {staleCount}
            </span>
          )}
        </Button>
        <Button onClick={onGenerate} disabled={!isParsed || pending.questions}>
          {pending.questions ? (
            <Loader2 className="size-3.5 animate-spin" />
          ) : (
            <Wand2 className="size-3.5" />
          )}
          {pending.questions ? '生成中…' : '生成假设问题'}
        </Button>
        <div className="ml-auto" />
        <Button asChild variant="ghost">
          <a
            href={`/api/import/files/${encodeURIComponent(fileId)}/download`}
            target="_blank"
            rel="noreferrer"
          >
            <Download className="size-3.5" />
            下载
          </a>
        </Button>
        <Button variant="ghost" onClick={onToggleDisabled}>
          {file.is_disabled ? <Power className="size-3.5" /> : <PowerOff className="size-3.5" />}
          {file.is_disabled ? '启用' : '禁用'}
        </Button>
        <Button variant="danger" onClick={onDelete}>
          <Trash2 className="size-3.5" />
          删除
        </Button>
      </div>

      {/* 任务区：解析进度条 + 其他后台任务 */}
      <AnimatePresence initial={false}>
        {(isParsing || pending.embed || pending.questions) && status && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: dur.base, ease: ease.out }}
            className="shrink-0 overflow-hidden border-b border-(--color-border)"
          >
            <TaskPanel
              parseStatus={isParsing ? status : null}
              embedPending={pending.embed}
              questionsPending={pending.questions}
            />
          </motion.div>
        )}
      </AnimatePresence>

      <DrawerBody className="!p-0">
        {chunksQ.isPending ? (
          <div className="space-y-2 p-6">
            <Skeleton className="h-6 w-1/3" />
            <Skeleton className="h-32 w-full" />
            <Skeleton className="h-32 w-full" />
          </div>
        ) : (
          <ChunkBrowser fileId={fileId} chunks={chunksQ.data?.items || []} />
        )}
      </DrawerBody>
    </>
  )
}

function TaskPanel({
  parseStatus,
  embedPending,
  questionsPending,
}: {
  parseStatus: ParseStatusResponse | null
  embedPending: boolean
  questionsPending: boolean
}) {
  return (
    <div className="bg-(--color-surface-2) px-6 py-3 flex flex-col gap-2.5">
      {parseStatus && <ParseProgressRow status={parseStatus} />}
      {embedPending && (
        <TaskRow label="正在生成 embedding" hint="对所有切片向量化，可关闭抽屉，过会儿回来查看" />
      )}
      {questionsPending && (
        <TaskRow label="正在生成假设问题" hint="对每个切片 LLM 生成 3-5 条问题，需要几十秒到几分钟" />
      )}
    </div>
  )
}

function ParseProgressRow({ status }: { status: ParseStatusResponse }) {
  const percent = Math.max(0, Math.min(100, status.percent || 0))
  const stage =
    (status.progress?.stage as string | undefined) ||
    (status.progress?.message as string | undefined) ||
    tr(parseStateLabel, status.state, status.state)
  const current = status.progress?.current as number | undefined
  const total = status.progress?.total as number | undefined
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between text-[12px] text-(--color-text-muted)">
        <div className="flex items-center gap-2">
          <Loader2 className="size-3.5 animate-spin text-(--color-primary-hi)" />
          <span className="text-(--color-text)">解析中</span>
          <span className="text-(--color-text-faint)">· {stage}</span>
          {current !== undefined && total !== undefined && (
            <span className="font-mono text-[11px] text-(--color-text-faint)">
              {current}/{total}
            </span>
          )}
        </div>
        <span className="font-mono text-[11px] text-(--color-text-faint)">{percent}%</span>
      </div>
      <div className="h-1 w-full overflow-hidden rounded-full bg-(--color-surface-3)">
        <motion.div
          className="h-full bg-(--color-primary)"
          initial={false}
          animate={{ width: `${percent}%` }}
          transition={{ duration: dur.base, ease: ease.out }}
        />
      </div>
    </div>
  )
}

function TaskRow({ label, hint }: { label: string; hint: string }) {
  return (
    <div className="flex items-center gap-2 text-[12px] text-(--color-text-muted)">
      <Loader2 className="size-3.5 animate-spin text-(--color-primary-hi)" />
      <span className="text-(--color-text)">{label}</span>
      <span className="text-(--color-text-faint)">· {hint}</span>
    </div>
  )
}

function DrawerInnerSkeleton() {
  return (
    <div className="space-y-3 p-6">
      <Skeleton className="h-6 w-1/3" />
      <Skeleton className="h-4 w-1/2" />
      <div className="space-y-2 pt-4">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-24 w-full" />
      </div>
    </div>
  )
}

function mapStatus(s: string) {
  if (s === 'completed' || s === 'needs_review') return 'ready' as const
  if (s === 'failed') return 'failed' as const
  if (s === 'processing' || s === 'parsing') return 'pending' as const
  return 'muted' as const
}
