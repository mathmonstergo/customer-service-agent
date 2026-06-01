import { useState, useRef, type KeyboardEvent } from 'react'
import { X } from 'lucide-react'
import { cn } from '@/lib/cn'

interface Props {
  value: string[]
  onChange: (next: string[]) => void
  placeholder?: string
  className?: string
}

export function TagInput({ value, onChange, placeholder = '输入后回车或逗号添加', className }: Props) {
  const [draft, setDraft] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const commit = (raw: string) => {
    const text = raw.trim().replace(/,$/, '').trim()
    if (!text) return
    if (value.includes(text)) return
    onChange([...value, text])
    setDraft('')
  }

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault()
      commit(draft)
    } else if (e.key === 'Backspace' && !draft && value.length > 0) {
      onChange(value.slice(0, -1))
    }
  }

  return (
    <div
      className={cn(
        'flex flex-wrap gap-1.5 rounded-(--radius-control) bg-(--color-surface-2) border border-(--color-border) px-2 py-1.5 min-h-9',
        'transition-[border-color,background] duration-[120ms] [transition-timing-function:var(--ease-out)]',
        'hover:bg-(--color-surface-3) focus-within:border-(--color-primary)/60',
        className,
      )}
      onClick={() => inputRef.current?.focus()}
    >
      {value.map((tag, i) => (
        <span
          key={`${tag}-${i}`}
          className="group inline-flex items-center gap-1 rounded-(--radius-control) bg-(--color-primary-soft) border border-(--color-primary)/30 px-1.5 py-0.5 text-[12px] text-(--color-primary-hi)"
        >
          {tag}
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation()
              onChange(value.filter((_, j) => j !== i))
            }}
            className="-mr-0.5 inline-flex size-3.5 items-center justify-center rounded-full opacity-0 group-hover:opacity-100 hover:bg-(--color-primary)/30"
            aria-label="删除"
          >
            <X className="size-2.5" />
          </button>
        </span>
      ))}
      <input
        ref={inputRef}
        value={draft}
        onChange={(e) => {
          const v = e.target.value
          if (v.endsWith(',') || v.endsWith('，')) {
            commit(v)
          } else {
            setDraft(v)
          }
        }}
        onKeyDown={onKeyDown}
        onBlur={() => draft && commit(draft)}
        placeholder={value.length === 0 ? placeholder : ''}
        className="flex-1 min-w-[80px] bg-transparent text-[13px] text-(--color-text) outline-none placeholder:text-(--color-text-faint)"
      />
    </div>
  )
}
