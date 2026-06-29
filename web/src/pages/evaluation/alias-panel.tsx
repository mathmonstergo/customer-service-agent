import { useState } from 'react'
import { BookOpen, Pencil, Plus, Save, Trash2 } from 'lucide-react'
import type { RetrievalAlias } from '@/api/schemas'
import { useRetrievalAliases, useSaveRetrievalAlias } from '@/api/hooks'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Drawer,
  DrawerBody,
  DrawerContent,
  DrawerHeader,
  DrawerTitle,
} from '@/components/ui/drawer'
import { DRAWER_WIDTH_COMPACT } from '@/components/ui/drawer-constants'
import { Input } from '@/components/ui/input'
import { toast } from '@/components/ui/toast'
import { cn } from '@/lib/cn'
import { joinListInput, splitListInput } from './helpers'

interface AliasFormState {
  id: string
  canonical: string
  aliases: string
  tags: string
  status: string
}

const EMPTY_ALIAS_FORM: AliasFormState = {
  id: '',
  canonical: '',
  aliases: '',
  tags: '',
  status: 'active',
}

// 别名词典以抽屉承载，避免评测主工作区出现不一致的常驻右栏宽度。
export function AliasPanel({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const { data, isPending, isError } = useRetrievalAliases()
  const saveAlias = useSaveRetrievalAlias()
  const [form, setForm] = useState<AliasFormState>(EMPTY_ALIAS_FORM)
  const items = data?.items || []

  // 把已有词条映射为抽屉底部表单状态，便于原地编辑。
  const edit = (item: RetrievalAlias) => {
    setForm({
      id: item.id,
      canonical: item.canonical,
      aliases: joinListInput(item.aliases),
      tags: joinListInput(item.tags),
      status: item.status || 'active',
    })
  }

  // 清空表单并回到新增模式，避免上一条编辑状态污染下一次创建。
  const clear = () => setForm(EMPTY_ALIAS_FORM)

  // 单字段更新表单状态；所有输入保持为字符串，提交时再做列表拆分。
  const update = (key: keyof AliasFormState, value: string) => {
    setForm((current) => ({ ...current, [key]: value }))
  }

  // 保存别名词条；后端负责 upsert，前端只做必要的空标准词禁用。
  const submit = async () => {
    try {
      await saveAlias.mutateAsync({
        id: form.id || undefined,
        canonical: form.canonical,
        aliases: splitListInput(form.aliases),
        tags: splitListInput(form.tags),
        status: form.status,
      })
      toast.success('别名已保存')
      clear()
    } catch (error) {
      toast.error((error as Error).message || '保存别名失败')
    }
  }

  return (
    <Drawer open={open} onOpenChange={onOpenChange}>
      <DrawerContent width={DRAWER_WIDTH_COMPACT}>
        <DrawerHeader>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <BookOpen className="size-4 text-(--color-primary-hi)" />
              <DrawerTitle>别名词典</DrawerTitle>
              <Badge tone="muted">{items.length}</Badge>
            </div>
            <p className="mt-1 text-[12px] leading-[1.6] text-(--color-text-muted)">
              用于关键词扩展，保存后影响后续单条评测运行。
            </p>
          </div>
        </DrawerHeader>

        <DrawerBody className="flex flex-col gap-4">
          <section className="min-h-0 flex-1">
            {isPending && <AliasSkeleton />}
            {isError && <div className="px-2 py-8 text-[12px] text-(--color-danger)">别名加载失败</div>}
            {!isPending && !isError && (
              <div className="space-y-1">
                {items.slice(0, 16).map((item) => (
                  <div
                    key={item.id}
                    className="rounded-(--radius-control) border border-(--color-border-soft) bg-(--color-surface) px-3 py-2"
                  >
                    <div className="flex items-center gap-2">
                      <div className="min-w-0 flex-1 truncate text-[12px] text-(--color-text)">
                        {item.canonical}
                      </div>
                      <Badge tone={item.status === 'active' ? 'success' : 'muted'}>
                        {item.status === 'active' ? '启用' : '禁用'}
                      </Badge>
                      <button
                        type="button"
                        onClick={() => edit(item)}
                        className="inline-flex size-6 items-center justify-center rounded-(--radius-control) text-(--color-text-faint) hover:bg-(--color-surface-2) hover:text-(--color-text)"
                        title="编辑别名"
                      >
                        <Pencil className="size-3.5" />
                      </button>
                    </div>
                    <div className="mt-1 truncate text-[11px] text-(--color-text-faint)">
                      {(item.aliases || []).join('、') || '无别名'}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className="shrink-0 rounded-(--radius-control) border border-(--color-border) bg-(--color-surface) p-3">
            <div className="mb-2 flex items-center justify-between text-[12px] text-(--color-text-muted)">
              <span>{form.id ? '编辑别名' : '新增别名'}</span>
              {form.id ? (
                <button
                  type="button"
                  onClick={clear}
                  className="inline-flex items-center gap-1 text-(--color-text-faint) hover:text-(--color-text)"
                >
                  <Plus className="size-3" />
                  新增
                </button>
              ) : null}
            </div>
            <div className="space-y-2">
              <Input
                value={form.canonical}
                onChange={(event) => update('canonical', event.target.value)}
                placeholder="标准词，例如：报告"
              />
              <Input
                value={form.aliases}
                onChange={(event) => update('aliases', event.target.value)}
                placeholder="别名，用逗号分隔"
              />
              <div className="grid grid-cols-[1fr_auto] gap-2">
                <select
                  value={form.status}
                  onChange={(event) => update('status', event.target.value)}
                  className="h-8 rounded-(--radius-control) border border-(--color-border) bg-(--color-surface-2) px-2 text-[12px] text-(--color-text) focus:border-(--color-primary)/60 focus:outline-none"
                >
                  <option value="active">启用</option>
                  <option value="disabled">禁用</option>
                </select>
                <Button
                  variant="primary"
                  size="sm"
                  onClick={submit}
                  disabled={saveAlias.isPending || !form.canonical.trim()}
                >
                  <Save className="size-3.5" />
                  保存
                </Button>
              </div>
              {form.id && (
                <button
                  type="button"
                  onClick={() => update('status', 'disabled')}
                  className={cn(
                    'inline-flex items-center gap-1 text-[11px] text-(--color-danger)',
                    form.status === 'disabled' && 'opacity-50',
                  )}
                >
                  <Trash2 className="size-3" />
                  标记禁用
                </button>
              )}
            </div>
          </section>
        </DrawerBody>
      </DrawerContent>
    </Drawer>
  )
}

// 别名列表骨架屏；仅用于初次加载，避免抽屉内容跳动。
function AliasSkeleton() {
  return (
    <div className="space-y-2">
      {Array.from({ length: 5 }).map((_, index) => (
        <div key={index} className="skeleton h-14" />
      ))}
    </div>
  )
}
