// 供应商配置抽屉：预设下拉 + base_url + api_key + 拉取模型 + 模型选择 + 测试连通。
// 设计要点：
// - 三件套留空 = 走全局默认；填齐 = 当前会话 per-request override。
// - 模型列表按 (base_url, api_key) 指纹缓存到 localStorage，下次同账户立刻可选。
// - 操作必有反馈：拉取/测试都有 inline 状态条 + toast。
import { useEffect, useMemo, useState } from 'react'
import { AnimatePresence } from 'framer-motion'
import {
  CheckCircle2,
  ChevronDown,
  Download,
  Eye,
  EyeOff,
  Loader2,
  Plug,
  XCircle,
} from 'lucide-react'
import {
  Drawer,
  DrawerBody,
  DrawerContent,
  DrawerFooter,
  DrawerHeader,
  DrawerTitle,
} from '@/components/ui/drawer'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { toast } from '@/components/ui/toaster'
import { cn } from '@/lib/cn'
import {
  useAssistantDefaults,
  useListChatProviderModels,
  useProbeChatProvider,
} from '@/api/hooks'
import {
  useAssistant,
  providerFingerprint,
  PROVIDER_PRESETS,
  type ProviderConfig,
} from '@/store/assistant'

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  conversationId: string
}

interface ProbeState {
  status: 'idle' | 'ok' | 'fail'
  message?: string
}

export function ProviderDrawer({ open, onOpenChange, conversationId }: Props) {
  const conv = useAssistant((s) => s.conversations[conversationId])
  const updateProvider = useAssistant((s) => s.updateProvider)
  const modelsCache = useAssistant((s) => s.modelsCache)
  const cacheModels = useAssistant((s) => s.cacheModels)
  const defaults = useAssistantDefaults()
  const listModels = useListChatProviderModels()
  const probe = useProbeChatProvider()

  // 抽屉打开时把会话的配置 copy 到本地 draft，确认保存时再写回。
  const [draft, setDraft] = useState<ProviderConfig>(
    conv?.provider ?? {
      presetId: '',
      chat_base_url: '',
      chat_api_key: '',
      chat_model: '',
    },
  )
  const [revealKey, setRevealKey] = useState(false)
  const [probeState, setProbeState] = useState<ProbeState>({ status: 'idle' })

  useEffect(() => {
    if (open && conv) {
      setDraft(conv.provider)
      setProbeState({ status: 'idle' })
    }
  }, [open, conv])

  const fingerprint = useMemo(
    () => providerFingerprint(draft.chat_base_url, draft.chat_api_key),
    [draft.chat_base_url, draft.chat_api_key],
  )
  const cached = modelsCache[fingerprint]
  const hasCachedModels = !!cached && cached.items.length > 0

  const onChooseProvider = (presetId: string) => {
    const preset = PROVIDER_PRESETS.find((p) => p.id === presetId)
    if (!preset) return
    setDraft((d) => ({
      ...d,
      presetId,
      chat_base_url: preset.base_url || d.chat_base_url,
    }))
    setProbeState({ status: 'idle' })
  }

  const onFetchModels = async () => {
    if (!draft.chat_base_url.trim() || !draft.chat_api_key.trim()) {
      toast.error('请填 base_url 和 api_key 再拉取模型')
      return
    }
    try {
      const res = await listModels.mutateAsync({
        chat_base_url: draft.chat_base_url.trim(),
        chat_api_key: draft.chat_api_key.trim(),
      })
      if (res.ok && res.items.length > 0) {
        cacheModels(fingerprint, res.items)
        toast.success(`拉到 ${res.items.length} 个模型`)
      } else {
        toast.error(res.error || '拉取模型失败：未返回任何模型')
      }
    } catch (e) {
      toast.error((e as Error).message || '拉取模型失败')
    }
  }

  const onTest = async () => {
    if (
      !draft.chat_base_url.trim() ||
      !draft.chat_api_key.trim() ||
      !draft.chat_model.trim()
    ) {
      toast.error('请填齐 base_url、api_key、model 后再测试')
      return
    }
    try {
      const res = await probe.mutateAsync({
        chat_base_url: draft.chat_base_url.trim(),
        chat_api_key: draft.chat_api_key.trim(),
        chat_model: draft.chat_model.trim(),
      })
      if (res.ok) {
        setProbeState({
          status: 'ok',
          message: `延迟 ${res.latency_ms}ms${res.sample ? ` · 示例「${res.sample}」` : ''}`,
        })
        toast.success(`连通成功 · ${res.latency_ms}ms`)
      } else {
        setProbeState({ status: 'fail', message: res.error || '未知错误' })
        toast.error(res.error || '连通失败')
      }
    } catch (e) {
      const msg = (e as Error).message || '请求失败'
      setProbeState({ status: 'fail', message: msg })
      toast.error(msg)
    }
  }

  const onSave = () => {
    updateProvider(conversationId, {
      presetId: draft.presetId,
      chat_base_url: draft.chat_base_url.trim(),
      chat_api_key: draft.chat_api_key.trim(),
      chat_model: draft.chat_model.trim(),
    })
    toast.success(
      draft.chat_base_url.trim() && draft.chat_api_key.trim() && draft.chat_model.trim()
        ? '已应用到当前会话'
        : '已恢复到全局默认',
    )
    onOpenChange(false)
  }

  const onClear = () => {
    setDraft({ presetId: '', chat_base_url: '', chat_api_key: '', chat_model: '' })
    setProbeState({ status: 'idle' })
  }

  const globalLabel = useMemo(() => {
    if (!defaults.data) return '加载中…'
    const m = defaults.data.chat_model || '(未配置)'
    return m
  }, [defaults.data])

  return (
    <Drawer open={open} onOpenChange={onOpenChange}>
      <AnimatePresence>
        {open && (
          <DrawerContent width={520}>
            <DrawerHeader>
              <div>
                <DrawerTitle>会话级供应商</DrawerTitle>
                <p className="mt-1 text-[12px] text-(--color-text-muted)">
                  填齐三项 = 本会话覆盖；留空 = 走全局默认（
                  <span className="font-mono text-(--color-text)">{globalLabel}</span>）
                </p>
              </div>
            </DrawerHeader>
            <DrawerBody>
              <div className="flex flex-col gap-5">
                <Field label="预设">
                  <PresetSelect value={draft.presetId || ''} onChange={onChooseProvider} />
                </Field>

                <Field label="Base URL">
                  <Input
                    value={draft.chat_base_url}
                    onChange={(e) =>
                      setDraft((d) => ({ ...d, chat_base_url: e.target.value }))
                    }
                    placeholder="https://api.openai.com/v1"
                    spellCheck={false}
                  />
                </Field>

                <Field label="API Key">
                  <div className="relative">
                    <Input
                      type={revealKey ? 'text' : 'password'}
                      value={draft.chat_api_key}
                      onChange={(e) =>
                        setDraft((d) => ({ ...d, chat_api_key: e.target.value }))
                      }
                      placeholder="sk-…"
                      autoComplete="off"
                      spellCheck={false}
                      className="pr-8"
                    />
                    <button
                      type="button"
                      onClick={() => setRevealKey((v) => !v)}
                      className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded-(--radius-control) p-1 text-(--color-text-faint) hover:bg-(--color-surface-2) hover:text-(--color-text-muted)"
                      aria-label={revealKey ? '隐藏' : '显示'}
                    >
                      {revealKey ? <EyeOff className="size-3.5" /> : <Eye className="size-3.5" />}
                    </button>
                  </div>
                </Field>

                <Field
                  label="模型"
                  hint={
                    hasCachedModels
                      ? `共 ${cached!.items.length} 个 · 上次拉取 ${formatAge(cached!.fetchedAt)}`
                      : '点右侧"拉取模型"获取列表'
                  }
                >
                  <div className="flex items-center gap-2">
                    <ModelSelect
                      value={draft.chat_model}
                      onChange={(v) => setDraft((d) => ({ ...d, chat_model: v }))}
                      models={cached?.items.map((m) => m.id) || []}
                    />
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={onFetchModels}
                      disabled={listModels.isPending}
                    >
                      {listModels.isPending ? (
                        <Loader2 className="size-3.5 animate-spin" />
                      ) : (
                        <Download className="size-3.5" />
                      )}
                      拉取模型
                    </Button>
                  </div>
                </Field>

                <div className="rounded-(--radius-control) border border-(--color-border-soft) bg-(--color-surface) px-3 py-2.5">
                  <div className="flex items-center gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={onTest}
                      disabled={probe.isPending}
                    >
                      {probe.isPending ? (
                        <Loader2 className="size-3.5 animate-spin" />
                      ) : (
                        <Plug className="size-3.5" />
                      )}
                      测试连通
                    </Button>
                    {probeState.status === 'ok' && (
                      <span className="inline-flex items-center gap-1 text-[12px] text-(--color-success)">
                        <CheckCircle2 className="size-3.5" />
                        {probeState.message}
                      </span>
                    )}
                    {probeState.status === 'fail' && (
                      <span className="inline-flex min-w-0 items-center gap-1 text-[12px] text-(--color-danger)">
                        <XCircle className="size-3.5 shrink-0" />
                        <span className="truncate">{probeState.message}</span>
                      </span>
                    )}
                  </div>
                </div>
              </div>
            </DrawerBody>
            <DrawerFooter>
              <Button variant="ghost" onClick={onClear}>
                清空（走全局）
              </Button>
              <Button variant="ghost" onClick={() => onOpenChange(false)}>
                取消
              </Button>
              <Button variant="primary" onClick={onSave}>
                应用到本会话
              </Button>
            </DrawerFooter>
          </DrawerContent>
        )}
      </AnimatePresence>
    </Drawer>
  )
}

function Field({
  label,
  hint,
  children,
}: {
  label: string
  hint?: string
  children: React.ReactNode
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label className="text-[11px] uppercase tracking-wider text-(--color-text-faint)">
        {label}
      </label>
      {children}
      {hint && <span className="text-[11px] text-(--color-text-faint)">{hint}</span>}
    </div>
  )
}

function PresetSelect({
  value,
  onChange,
}: {
  value: string
  onChange: (id: string) => void
}) {
  return (
    <div className="relative">
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={cn(
          'h-8 w-full appearance-none rounded-(--radius-control) bg-(--color-surface-2)',
          'border border-(--color-border) pl-2.5 pr-8 text-[13px] text-(--color-text)',
          'hover:bg-(--color-surface-3) focus:outline-none focus:border-(--color-primary)/60',
        )}
      >
        <option value="">— 选择厂商 —</option>
        {PROVIDER_PRESETS.map((p) => (
          <option key={p.id} value={p.id}>
            {p.label}
          </option>
        ))}
      </select>
      <ChevronDown className="pointer-events-none absolute right-2 top-1/2 size-3.5 -translate-y-1/2 text-(--color-text-faint)" />
    </div>
  )
}

function ModelSelect({
  value,
  onChange,
  models,
}: {
  value: string
  onChange: (v: string) => void
  models: string[]
}) {
  // 若已有缓存模型列表且当前值在其中，渲染 select；否则渲染 Input 允许自由填写。
  const inList = models.includes(value)
  if (models.length > 0) {
    return (
      <div className="relative flex-1">
        <select
          value={inList ? value : ''}
          onChange={(e) => onChange(e.target.value)}
          className={cn(
            'h-8 w-full appearance-none rounded-(--radius-control) bg-(--color-surface-2)',
            'border border-(--color-border) pl-2.5 pr-8 text-[13px] text-(--color-text)',
            'hover:bg-(--color-surface-3) focus:outline-none focus:border-(--color-primary)/60',
          )}
        >
          <option value="">{inList ? '' : value || '— 选择模型 —'}</option>
          {models.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>
        <ChevronDown className="pointer-events-none absolute right-2 top-1/2 size-3.5 -translate-y-1/2 text-(--color-text-faint)" />
      </div>
    )
  }
  return (
    <Input
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder="模型 id（如 gpt-4o-mini）"
      spellCheck={false}
      className="flex-1"
    />
  )
}

function formatAge(ts: number): string {
  const sec = Math.max(0, Math.floor((Date.now() - ts) / 1000))
  if (sec < 60) return `${sec}s 前`
  const min = Math.floor(sec / 60)
  if (min < 60) return `${min}m 前`
  const h = Math.floor(min / 60)
  if (h < 24) return `${h}h 前`
  const d = Math.floor(h / 24)
  return `${d}d 前`
}
