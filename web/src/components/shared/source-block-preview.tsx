import { useMemo } from 'react'
import { cn } from '@/lib/cn'
import { sanitizeTableHtml } from '@/lib/sanitize'
import type { SourceBlock } from '@/api/schemas'

function assetUrl(fileId: string, relpath?: string) {
  if (!fileId || !relpath) return ''
  const encoded = String(relpath)
    .split('/')
    .map(encodeURIComponent)
    .join('/')
  return `/api/import/files/${encodeURIComponent(fileId)}/assets/${encoded}`
}

interface Props {
  blocks: SourceBlock[]
  fileId: string
  className?: string
}

// 单个汉字/假名/谚文(用于识别竖排标题里的逐字行)
const SINGLE_CJK = /^[㐀-鿿豈-﫿぀-ヿ가-힯]$/

/**
 * 还原 MinerU 封面竖排标题。
 *
 * PDF 封面里"用 户 使 用 手 册"这类竖排/疏排标题会被解析成单字之间夹空行的文本
 * (如 "用\n\n户\n\n使…"),再用 whitespace-pre-wrap 渲染就变成了每字一行。
 * 这里只把"连续 ≥2 个单字行(可被空行隔开)"的片段横向合并成一行,普通段落、目录等原样保留。
 * 纯展示层处理,不改动已存储的 source_text 与向量,不改变文字内容本身。
 */
function deverticalizeCjk(text?: string | null): string {
  const raw = text || ''
  if (!raw.includes('\n')) return raw
  const lines = raw.split('\n')
  const out: string[] = []
  let i = 0
  while (i < lines.length) {
    // 从 i 起尝试收集一段"单字行(中间可夹空行)"的竖排串
    const run: string[] = []
    let last = i
    let j = i
    while (j < lines.length) {
      const t = lines[j].trim()
      if (t === '') {
        j++ // 跳过竖排串内部的空行
        continue
      }
      if (SINGLE_CJK.test(t)) {
        run.push(t)
        last = j
        j++
        continue
      }
      break
    }
    if (run.length >= 2) {
      out.push(run.join('')) // 竖排串合并成正常一行
      i = last + 1
    } else {
      out.push(lines[i]) // 普通行原样保留
      i++
    }
  }
  return out.join('\n')
}

export function SourceBlockPreview({ blocks, fileId, className }: Props) {
  return (
    <div className={cn('flex flex-col gap-4 text-[14px] leading-[1.65]', className)}>
      {blocks.map((block, i) => (
        <SourceBlockRender key={i} block={block} fileId={fileId} />
      ))}
    </div>
  )
}

function SourceBlockRender({ block, fileId }: { block: SourceBlock; fileId: string }) {
  const type = String(block.block_type || '').toLowerCase()
  const assetPaths = block.evidence?.asset_paths || {}

  if (type === 'image' || type === 'figure') {
    const src = assetUrl(fileId, assetPaths.img_path)
    if (!src) return <p>{block.text}</p>
    return (
      <figure className="flex flex-col gap-1.5">
        <img
          src={src}
          alt={block.text || '图片'}
          loading="lazy"
          className="max-w-full rounded-(--radius-control) border border-(--color-border)"
        />
        {block.text && (
          <figcaption className="text-[12px] text-(--color-text-muted)">{block.text}</figcaption>
        )}
      </figure>
    )
  }

  if (type === 'table') {
    return <TableBlock block={block} fileId={fileId} />
  }

  if (type === 'equation' || type === 'formula') {
    const src = assetUrl(fileId, assetPaths.equation_img_path)
    if (src) {
      return (
        <figure className="flex justify-center">
          <img src={src} alt="公式" loading="lazy" className="max-w-full" />
        </figure>
      )
    }
    return <p className="font-mono text-(--color-text-muted)">{block.text}</p>
  }

  if (type === 'title') {
    return <h3 className="text-[15px] text-(--color-text)">{deverticalizeCjk(block.text)}</h3>
  }

  return <p className="whitespace-pre-wrap text-(--color-text)">{deverticalizeCjk(block.text)}</p>
}

function TableBlock({ block, fileId }: { block: SourceBlock; fileId: string }) {
  const html = block.html || block.evidence?.table_html || ''
  const sanitized = useMemo(() => (html ? sanitizeTableHtml(html) : ''), [html])
  if (sanitized && /<table/i.test(sanitized)) {
    return (
      <div className="overflow-x-auto rounded-(--radius-control) border border-(--color-border)">
        <div
          className="[&_table]:w-full [&_table]:border-collapse [&_th]:bg-(--color-surface-2) [&_th]:p-2 [&_th]:text-left [&_th]:text-[12px] [&_th]:text-(--color-text-muted) [&_th]:border-b [&_th]:border-(--color-border) [&_td]:p-2 [&_td]:text-[13px] [&_td]:border-b [&_td]:border-(--color-border-soft)"
          dangerouslySetInnerHTML={{ __html: sanitized }}
        />
      </div>
    )
  }
  const tableImg = assetUrl(fileId, block.evidence?.asset_paths?.table_img_path)
  if (tableImg) {
    return (
      <figure>
        <img
          src={tableImg}
          alt="表格"
          loading="lazy"
          className="max-w-full rounded-(--radius-control) border border-(--color-border)"
        />
      </figure>
    )
  }
  return <pre className="whitespace-pre-wrap text-[13px]">{block.text}</pre>
}
