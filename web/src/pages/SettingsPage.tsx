import { AnimatePresence, motion } from 'framer-motion'
import {
  Bot,
  ChevronDown,
  Database,
  FileCog,
  Gauge,
  KeyRound,
  Layers3,
  Loader2,
  MessageCircle,
  Network,
  RefreshCw,
  RotateCcw,
  Save,
  Search,
  Shield,
  Upload,
  X,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useState, type MouseEvent, type ReactNode } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { toast } from '@/components/ui/toast'
import { useListChatProviderModels, useProbeChatProvider, useSettings, useUpdateSettings } from '@/api/hooks'
import type { SettingsSnapshot } from '@/api/schemas'
import { cn } from '@/lib/cn'
import { dur, ease, spring } from '@/lib/motion'
import {
  PROVIDER_PRESETS,
  providerFingerprint,
  useAssistant,
} from '@/store/assistant'
import {
  buildSettingsPatch,
  configuredSecretSummary,
  kgExtractionConfigSummary,
  providerSummary,
  settingValueSummary,
  type SettingsPatchDraft,
} from './settings/settings-model'

type SettingsCardId =
  | 'chat'
  | 'kg-extraction'
  | 'embedding'
  | 'rerank'
  | 'mineru'
  | 'rag'
  | 'chunking'
  | 'database'
  | 'upload'
  | 'wechat'

type ModalFrame = {
  left: number
  top: number
  width: number
  height: number
}

type SettingsCardDefinition = {
  id: SettingsCardId
  group: '模型服务' | '文档与检索' | '系统连接'
  title: string
  description: string
  icon: ReactNode
  status: string
  statusTone: 'muted' | 'primary' | 'success' | 'warning' | 'danger'
  lines: string[]
}

const CHUNKER_OPTIONS = [
  { value: 'naive', label: 'Naive' },
  { value: 'manual', label: 'Manual' },
  { value: 'qa', label: 'Q/A' },
  { value: 'table', label: 'Table' },
]

// 设置页主界面：卡片总览负责扫描状态，具体配置统一在卡片弹窗里编辑。
export default function SettingsPage() {
  const settings = useSettings()
  const updateSettings = useUpdateSettings()
  const listModels = useListChatProviderModels()
  const probeChat = useProbeChatProvider()
  const modelsCache = useAssistant((s) => s.modelsCache)
  const cacheModels = useAssistant((s) => s.cacheModels)
  const [selectedId, setSelectedId] = useState<SettingsCardId | null>(null)
  const [originFrame, setOriginFrame] = useState<ModalFrame | null>(null)
  const [targetFrame, setTargetFrame] = useState<ModalFrame | null>(null)
  const [draft, setDraft] = useState<SettingsPatchDraft>({})

  const cards = useMemo(
    () => buildSettingsCards(settings.data),
    [settings.data],
  )
  const selectedCard = cards.find((card) => card.id === selectedId)

  // 关闭弹窗时保留 originFrame 给 exit 动画使用，状态在动画完成后清理。
  const closeModal = useCallback(() => {
    setSelectedId(null)
  }, [])

  useEffect(() => {
    if (!selectedId) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') closeModal()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [selectedId, closeModal])

  // 打开配置弹窗时记录卡片位置，让弹窗从卡片区域连续扩展出来。
  const openCard = (id: SettingsCardId, event: MouseEvent<HTMLElement>) => {
    const rect = event.currentTarget.getBoundingClientRect()
    setOriginFrame({
      left: rect.left,
      top: rect.top,
      width: rect.width,
      height: rect.height,
    })
    setTargetFrame(getModalFrame(id))
    setDraft(buildDraft(id, settings.data))
    setSelectedId(id)
  }

  // 保存当前弹窗配置；敏感字段空值会在 helper 中被剔除，后端也会二次保护。
  const saveCurrentCard = async () => {
    if (!selectedId) return
    const patch = buildSettingsPatch(draft)
    if (Object.keys(patch).length === 0) {
      toast.info('没有需要保存的配置')
      return
    }
    try {
      await updateSettings.mutateAsync(patch)
      toast.success('设置已保存')
      closeModal()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '保存设置失败')
    }
  }

  // 拉取 Chat 模型列表；key 留空时由后端使用已保存 key，前端不读取旧明文。
  const fetchChatModels = async () => {
    const baseUrl = textValue(draft.chat_base_url)
    const apiKey = textValue(draft.chat_api_key)
    if (!baseUrl) {
      toast.error('请输入 Base URL 后再拉取模型')
      return
    }
    try {
      const result = await listModels.mutateAsync({
        chat_base_url: baseUrl,
        ...(apiKey ? { chat_api_key: apiKey } : {}),
      })
      if (result.ok && result.items.length > 0) {
        cacheModels(providerFingerprint(baseUrl, apiKey), result.items)
        toast.success(`拉到 ${result.items.length} 个模型`)
      } else {
        toast.error(result.error || '拉取模型失败')
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '拉取模型失败')
    }
  }

  // 测试 Chat 供应商；key 留空时测试当前已保存 key，输入新 key 时只用于本次请求。
  const testChatProvider = async () => {
    const baseUrl = textValue(draft.chat_base_url)
    const apiKey = textValue(draft.chat_api_key)
    const model = textValue(draft.chat_model)
    if (!baseUrl || !model) {
      toast.error('请输入 Base URL 和模型后再测试')
      return
    }
    try {
      const result = await probeChat.mutateAsync({
        chat_base_url: baseUrl,
        chat_model: model,
        ...(apiKey ? { chat_api_key: apiKey } : {}),
      })
      if (result.ok) {
        toast.success(`连通成功 · ${result.latency_ms}ms`)
      } else {
        toast.error(result.error || '连通失败')
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '测试连接失败')
    }
  }

  const chatFingerprint = providerFingerprint(
    textValue(draft.chat_base_url),
    textValue(draft.chat_api_key),
  )
  const cachedModels = modelsCache[chatFingerprint]?.items.map((item) => item.id) ?? []

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="flex shrink-0 items-start justify-between gap-4 border-b border-(--color-border) px-6 py-5">
        <div>
          <h1 className="text-[18px] text-(--color-text)">设置</h1>
          <p className="mt-1 text-[13px] text-(--color-text-muted)">
            全局 API 与服务配置。智能问答仍可在会话页单独覆盖供应商。
          </p>
        </div>
        {settings.isFetching && (
          <Badge tone="muted" className="mt-1">
            <Loader2 className="size-3 animate-spin" />
            同步中
          </Badge>
        )}
      </div>

      <main className="flex-1 overflow-y-auto scroll-thin px-6 py-5" style={{ scrollbarGutter: 'stable' }}>
        {settings.isLoading ? (
          <SettingsSkeleton />
        ) : settings.isError ? (
          <div className="surface rounded-(--radius-card) px-6 py-10 text-center text-[13px] text-(--color-text-muted)">
            设置加载失败
            <Button className="ml-3" size="sm" onClick={() => settings.refetch()}>
              重试
            </Button>
          </div>
        ) : (
          <div className="flex w-full flex-col gap-7">
            {(['模型服务', '文档与检索', '系统连接'] as const).map((group) => {
              const groupCards = cards.filter((card) => card.group === group)
              return (
                <section key={group} className="border-t border-(--color-border) pt-5">
                  <div className="mb-3">
                    <h2 className="text-[14px] text-(--color-text)">{group}</h2>
                  </div>
                  <div
                    className="grid w-full justify-start gap-3"
                    style={{ gridTemplateColumns: 'repeat(auto-fill, 280px)' }}
                  >
                    {groupCards.map((card) => (
                        <SettingsCard key={card.id} card={card} onOpen={openCard} />
                      ))}
                  </div>
                </section>
              )
            })}
          </div>
        )}
      </main>

      <AnimatePresence
        onExitComplete={() => {
          setOriginFrame(null)
          setTargetFrame(null)
          setDraft({})
        }}
      >
        {selectedId && selectedCard && originFrame && targetFrame && (
          <SettingsModal
            key={selectedId}
            card={selectedCard}
            draft={draft}
            setDraft={setDraft}
            originFrame={originFrame}
            targetFrame={targetFrame}
            settings={settings.data}
            cachedModels={cachedModels}
            isSaving={updateSettings.isPending}
            isFetchingModels={listModels.isPending}
            isTesting={probeChat.isPending}
            onClose={closeModal}
            onSave={saveCurrentCard}
            onFetchModels={fetchChatModels}
            onTest={testChatProvider}
          />
        )}
      </AnimatePresence>
    </div>
  )
}

// 构造设置卡片数据，保持卡片尺寸一致，只展示当前配置摘要。
function buildSettingsCards(settings?: SettingsSnapshot): SettingsCardDefinition[] {
  return [
    {
      id: 'chat',
      group: '模型服务',
      title: 'Chat 默认',
      description: 'KG 抽取、FAQ 优化和默认问答模型',
      icon: <Bot className="size-4" />,
      status: settings?.chat_api_key_configured ? '已配置' : '缺少 Key',
      statusTone: settings?.chat_api_key_configured ? 'success' : 'warning',
      lines: [
        providerSummary(settings?.chat_base_url),
        settingValueSummary(settings?.chat_model),
        configuredSecretSummary(settings?.chat_api_key_configured, settings?.chat_api_key),
      ],
    },
    {
      id: 'kg-extraction',
      group: '模型服务',
      title: '实体提取',
      description: '知识图谱实体和关系候选抽取',
      icon: <Network className="size-4" />,
      status: settings?.chat_api_key_configured ? '跟随 Chat' : '缺少 Key',
      statusTone: settings?.chat_api_key_configured ? 'success' : 'warning',
      lines: kgExtractionConfigSummary({
        chat_base_url: settings?.chat_base_url,
        chat_model: settings?.chat_model,
        chat_api_key_configured: settings?.chat_api_key_configured,
        chat_api_key: settings?.chat_api_key,
      }),
    },
    {
      id: 'embedding',
      group: '模型服务',
      title: 'Embedding',
      description: '文档与 FAQ 向量化配置',
      icon: <Layers3 className="size-4" />,
      status: `${settingValueSummary(settings?.embedding_dimensions)} 维`,
      statusTone: 'primary',
      lines: [
        settingValueSummary(settings?.embedding_base_url),
        settingValueSummary(settings?.embedding_model),
        configuredSecretSummary(settings?.embedding_api_key_configured, settings?.embedding_api_key),
      ],
    },
    {
      id: 'rerank',
      group: '模型服务',
      title: 'Rerank',
      description: '可选重排服务，缺省时直接透传召回结果',
      icon: <Shield className="size-4" />,
      status: settings?.rerank_model ? '已启用' : '可选',
      statusTone: settings?.rerank_model ? 'success' : 'muted',
      lines: [
        settingValueSummary(settings?.rerank_base_url),
        settingValueSummary(settings?.rerank_model),
        `Input ${settingValueSummary(settings?.rerank_input_size)}`,
      ],
    },
    {
      id: 'mineru',
      group: '文档与检索',
      title: 'MinerU 解析',
      description: 'PDF / Office 文档解析服务',
      icon: <FileCog className="size-4" />,
      status: settings?.mineru_api_token_configured ? '已配置' : '未配置',
      statusTone: settings?.mineru_api_token_configured ? 'success' : 'warning',
      lines: [
        configuredSecretSummary(settings?.mineru_api_token_configured, settings?.mineru_api_token),
        `超时 ${settingValueSummary(settings?.mineru_parse_timeout_seconds)} 秒`,
        `KB 打包器 ${settingValueSummary(settings?.mineru_use_kb_packager)}`,
      ],
    },
    {
      id: 'rag',
      group: '文档与检索',
      title: 'RAG 检索',
      description: '问答召回阈值和候选数量',
      icon: <Search className="size-4" />,
      status: `Top ${settingValueSummary(settings?.rag_top_k)}`,
      statusTone: 'primary',
      lines: [
        `Top K ${settingValueSummary(settings?.rag_top_k)}`,
        `Min score ${settingValueSummary(settings?.rag_min_score)}`,
        '影响默认 RAG 召回',
      ],
    },
    {
      id: 'chunking',
      group: '文档与检索',
      title: '文档切分',
      description: 'RAGFlow 风格 chunker 参数',
      icon: <Gauge className="size-4" />,
      status: settingValueSummary(settings?.document_chunker_type),
      statusTone: 'muted',
      lines: [
        `${settingValueSummary(settings?.document_chunk_token_num)} token`,
        `Overlap ${settingValueSummary(settings?.document_chunk_overlap_percent)}%`,
        `表格 ${settingValueSummary(settings?.document_table_context_size)} / 图片 ${settingValueSummary(settings?.document_image_context_size)}`,
      ],
    },
    {
      id: 'database',
      group: '系统连接',
      title: '数据库',
      description: 'PostgreSQL + pgvector 连接串',
      icon: <Database className="size-4" />,
      status: settings?.database_url_configured ? '已配置' : '未配置',
      statusTone: settings?.database_url_configured ? 'success' : 'danger',
      lines: [
        settingValueSummary(settings?.database_url),
        '密码已脱敏',
        '留空保存会保留旧连接串',
      ],
    },
    {
      id: 'upload',
      group: '系统连接',
      title: '上传目录',
      description: '文档原件与解析材料的本地路径',
      icon: <Upload className="size-4" />,
      status: '本地路径',
      statusTone: 'muted',
      lines: [
        settingValueSummary(settings?.upload_dir),
        '保存文件原件',
        '影响后续解析任务',
      ],
    },
    {
      id: 'wechat',
      group: '系统连接',
      title: '微信服务',
      description: '微信 token 文件和消息分段',
      icon: <MessageCircle className="size-4" />,
      status: `${settingValueSummary(settings?.wechat_message_chunk_size)} 条`,
      statusTone: 'muted',
      lines: [
        settingValueSummary(settings?.wechat_token_file),
        `分段 ${settingValueSummary(settings?.wechat_message_chunk_size)}`,
        '用于微信消息导入',
      ],
    },
  ]
}

// 单张设置卡片；整卡可点击进入配置，卡片尺寸固定避免宽屏拉伸。
function SettingsCard({
  card,
  onOpen,
}: {
  card: SettingsCardDefinition
  onOpen: (id: SettingsCardId, event: MouseEvent<HTMLElement>) => void
}) {
  return (
    <motion.button
      type="button"
      layoutId={`settings-card-${card.id}`}
      onClick={(event) => onOpen(card.id, event)}
      className={cn(
        'group grid h-40 w-[280px] min-w-0 grid-rows-[64px_52px] gap-3 rounded-(--radius-card) border border-(--color-border)',
        'bg-(--color-surface) p-4 text-left shadow-(--shadow-inset-highlight)',
        'transition-[background,border-color,transform] duration-[160ms] [transition-timing-function:var(--ease-out)]',
        'hover:-translate-y-0.5 hover:border-(--color-primary)/45 hover:bg-(--color-surface-2)',
        'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-(--color-primary)',
      )}
    >
      <div className="flex min-h-0 min-w-0 items-start justify-between gap-3 overflow-hidden">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-[13px] font-[580] text-(--color-text)">
            <span className="inline-flex size-7 shrink-0 items-center justify-center rounded-(--radius-control) bg-(--color-surface-2) text-(--color-text-muted) group-hover:text-(--color-primary-hi)">
              {card.icon}
            </span>
            <span className="truncate">{card.title}</span>
          </div>
          <p className="mt-2 line-clamp-2 overflow-hidden text-[12px] leading-5 text-(--color-text-faint)">
            {card.description}
          </p>
        </div>
        <Badge tone={card.statusTone} className="max-w-24 shrink-0 truncate">
          {card.status}
        </Badge>
      </div>
      <div className="min-h-0 space-y-1 overflow-hidden">
        {card.lines.map((line, index) => (
          <div
            key={`${card.id}-${index}`}
            className="h-3.5 truncate text-[11px] leading-3.5 text-(--color-text-muted)"
          >
            {line}
          </div>
        ))}
      </div>
    </motion.button>
  )
}

// 居中设置弹窗；用卡片 rect 作为 initial frame，形成从卡片扩展到弹窗的连续动效。
function SettingsModal({
  card,
  draft,
  setDraft,
  originFrame,
  targetFrame,
  settings,
  cachedModels,
  isSaving,
  isFetchingModels,
  isTesting,
  onClose,
  onSave,
  onFetchModels,
  onTest,
}: {
  card: SettingsCardDefinition
  draft: SettingsPatchDraft
  setDraft: (draft: SettingsPatchDraft | ((next: SettingsPatchDraft) => SettingsPatchDraft)) => void
  originFrame: ModalFrame
  targetFrame: ModalFrame
  settings?: SettingsSnapshot
  cachedModels: string[]
  isSaving: boolean
  isFetchingModels: boolean
  isTesting: boolean
  onClose: () => void
  onSave: () => void
  onFetchModels: () => void
  onTest: () => void
}) {
  return (
    <div className="fixed inset-0 z-50">
      <motion.div
        className="absolute inset-0 bg-black/55"
        initial={{ opacity: 0, backdropFilter: 'blur(0px)' }}
        animate={{ opacity: 1, backdropFilter: 'blur(7px)' }}
        exit={{ opacity: 0, backdropFilter: 'blur(0px)' }}
        transition={{ duration: 0.34, ease: ease.out }}
        onClick={onClose}
      />
      <motion.div
        role="dialog"
        aria-modal="true"
        aria-label={`配置 ${card.title}`}
        layoutId={`settings-card-${card.id}`}
        initial={{
          left: originFrame.left,
          top: originFrame.top,
          width: originFrame.width,
          height: originFrame.height,
          borderRadius: 10,
          opacity: 0.92,
        }}
        animate={{
          left: targetFrame.left,
          top: targetFrame.top,
          width: targetFrame.width,
          height: targetFrame.height,
          borderRadius: 14,
          opacity: 1,
        }}
        exit={{
          left: originFrame.left,
          top: originFrame.top,
          width: originFrame.width,
          height: originFrame.height,
          borderRadius: 10,
          opacity: 0,
        }}
        transition={spring}
        className="surface fixed z-50 flex flex-col overflow-hidden rounded-(--radius-drawer) shadow-(--shadow-elevated)"
      >
        <div className="flex h-14 shrink-0 items-center justify-between border-b border-(--color-border) px-5">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-[14px] font-[580] text-(--color-text)">
              <span className="inline-flex size-7 items-center justify-center rounded-(--radius-control) bg-(--color-surface-2) text-(--color-primary-hi)">
                {card.icon}
              </span>
              <span className="truncate">配置 {card.title}</span>
            </div>
            <p className="mt-0.5 truncate text-[11px] text-(--color-text-faint)">
              密钥类字段留空表示保留当前已配置值
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="inline-flex size-7 items-center justify-center rounded-(--radius-control) text-(--color-text-muted) transition-colors hover:bg-(--color-surface-2) hover:text-(--color-text)"
            aria-label="关闭"
          >
            <X className="size-4" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto scroll-thin px-5 py-4">
          {renderSettingsForm({
            id: card.id,
            draft,
            setDraft,
            settings,
            cachedModels,
            isFetchingModels,
            isTesting,
            onFetchModels,
            onTest,
          })}
        </div>
        <div className="flex h-14 shrink-0 items-center justify-between border-t border-(--color-border) px-5">
          <Button variant="ghost" onClick={() => setDraft(buildDraft(card.id, settings))}>
            <RotateCcw className="size-3.5" />
            还原
          </Button>
          <div className="flex items-center gap-2">
            <Button variant="ghost" onClick={onClose}>
              取消
            </Button>
            <Button variant="primary" onClick={onSave} disabled={isSaving}>
              {isSaving ? <Loader2 className="size-3.5 animate-spin" /> : <Save className="size-3.5" />}
              保存
            </Button>
          </div>
        </div>
      </motion.div>
    </div>
  )
}

// 根据卡片类型渲染弹窗表单，避免把所有字段直接铺在设置总览页。
function renderSettingsForm({
  id,
  draft,
  setDraft,
  settings,
  cachedModels,
  isFetchingModels,
  isTesting,
  onFetchModels,
  onTest,
}: {
  id: SettingsCardId
  draft: SettingsPatchDraft
  setDraft: (draft: SettingsPatchDraft | ((next: SettingsPatchDraft) => SettingsPatchDraft)) => void
  settings?: SettingsSnapshot
  cachedModels: string[]
  isFetchingModels: boolean
  isTesting: boolean
  onFetchModels: () => void
  onTest: () => void
}) {
  const setValue = (key: string, value: string | number | boolean) => {
    setDraft((current) => ({ ...current, [key]: value }))
  }

  if (id === 'chat' || id === 'kg-extraction') {
    return (
      <FormStack>
        {id === 'kg-extraction' && (
          <div className="rounded-(--radius-control) border border-(--color-border-soft) bg-(--color-surface-2) px-3 py-2 text-[12px] leading-5 text-(--color-text-muted)">
            实体提取当前复用全局 Chat 默认配置；保存这里会同步修改 Chat 默认，后续 KG 抽取任务会使用新的模型。
          </div>
        )}
        <DropdownField
          label="供应商预设"
          value={presetIdFromBaseUrl(textValue(draft.chat_base_url))}
          options={PROVIDER_PRESETS.map((preset) => ({
            value: preset.id,
            label: preset.label,
          }))}
          placeholder="自定义"
          onChange={(value) => {
            const preset = PROVIDER_PRESETS.find((item) => item.id === value)
            if (preset) setValue('chat_base_url', preset.base_url)
          }}
        />
        <TextField label="Base URL" value={draft.chat_base_url} onChange={(value) => setValue('chat_base_url', value)} placeholder="https://api.deepseek.com" />
        <SecretField
          label="API Key"
          configured={settings?.chat_api_key_configured}
          masked={settings?.chat_api_key}
          value={draft.chat_api_key}
          onChange={(value) => setValue('chat_api_key', value)}
        />
        {cachedModels.length > 0 ? (
          <DropdownField
            label="模型"
            value={textValue(draft.chat_model)}
            options={cachedModels.map((model) => ({ value: model, label: model }))}
            placeholder="选择模型"
            onChange={(value) => setValue('chat_model', value)}
          />
        ) : (
          <TextField label="模型" value={draft.chat_model} onChange={(value) => setValue('chat_model', value)} placeholder="deepseek-chat" />
        )}
        <div className="flex flex-wrap items-center gap-2 rounded-(--radius-control) border border-(--color-border-soft) bg-(--color-surface-2) p-2.5">
          <Button size="sm" variant="outline" onClick={onFetchModels} disabled={isFetchingModels}>
            {isFetchingModels ? <Loader2 className="size-3.5 animate-spin" /> : <RefreshCw className="size-3.5" />}
            拉取模型
          </Button>
          <Button size="sm" variant="outline" onClick={onTest} disabled={isTesting}>
            {isTesting ? <Loader2 className="size-3.5 animate-spin" /> : <KeyRound className="size-3.5" />}
            测试连接
          </Button>
          <span className="text-[11px] text-(--color-text-faint)">
            Key 留空时使用当前已保存 Key；输入新 Key 仅用于本次拉取/测试和保存覆盖。
          </span>
        </div>
      </FormStack>
    )
  }

  if (id === 'embedding') {
    return (
      <FormGrid>
        <TextField label="Base URL" value={draft.embedding_base_url} onChange={(value) => setValue('embedding_base_url', value)} />
        <TextField label="模型" value={draft.embedding_model} onChange={(value) => setValue('embedding_model', value)} />
        <NumberField label="维度" value={draft.embedding_dimensions} onChange={(value) => setValue('embedding_dimensions', value)} />
        <SecretField label="API Key" configured={settings?.embedding_api_key_configured} masked={settings?.embedding_api_key} value={draft.embedding_api_key} onChange={(value) => setValue('embedding_api_key', value)} />
      </FormGrid>
    )
  }

  if (id === 'rerank') {
    return (
      <FormGrid>
        <TextField label="Base URL" value={draft.rerank_base_url} onChange={(value) => setValue('rerank_base_url', value)} />
        <TextField label="模型" value={draft.rerank_model} onChange={(value) => setValue('rerank_model', value)} />
        <NumberField label="Input Size" value={draft.rerank_input_size} onChange={(value) => setValue('rerank_input_size', value)} />
        <SecretField label="API Key" configured={settings?.rerank_api_key_configured} masked={settings?.rerank_api_key} value={draft.rerank_api_key} onChange={(value) => setValue('rerank_api_key', value)} />
      </FormGrid>
    )
  }

  if (id === 'mineru') {
    return (
      <FormGrid>
        <SecretField label="MinerU API Token" configured={settings?.mineru_api_token_configured} masked={settings?.mineru_api_token} value={draft.mineru_api_token} onChange={(value) => setValue('mineru_api_token', value)} />
        <NumberField label="解析超时秒数" value={draft.mineru_parse_timeout_seconds} onChange={(value) => setValue('mineru_parse_timeout_seconds', value)} />
        <ToggleField label="启用 KB 打包器" value={draft.mineru_use_kb_packager} onChange={(value) => setValue('mineru_use_kb_packager', value)} />
      </FormGrid>
    )
  }

  if (id === 'rag') {
    return (
      <FormGrid>
        <NumberField label="RAG Top K" value={draft.rag_top_k} onChange={(value) => setValue('rag_top_k', value)} />
        <NumberField label="Min Score" value={draft.rag_min_score} onChange={(value) => setValue('rag_min_score', value)} step="0.01" />
      </FormGrid>
    )
  }

  if (id === 'chunking') {
    return (
      <FormGrid>
        <NumberField label="Chunk Token 数" value={draft.document_chunk_token_num} onChange={(value) => setValue('document_chunk_token_num', value)} />
        <DropdownField label="Chunker 类型" value={textValue(draft.document_chunker_type)} options={CHUNKER_OPTIONS} onChange={(value) => setValue('document_chunker_type', value)} />
        <TextField label="切分符" value={draft.document_chunk_delimiter} onChange={(value) => setValue('document_chunk_delimiter', value)} />
        <NumberField label="Overlap 百分比" value={draft.document_chunk_overlap_percent} onChange={(value) => setValue('document_chunk_overlap_percent', value)} />
        <TextField label="子块分隔符" value={draft.document_children_delimiter} onChange={(value) => setValue('document_children_delimiter', value)} />
        <NumberField label="表格上下文" value={draft.document_table_context_size} onChange={(value) => setValue('document_table_context_size', value)} />
        <NumberField label="图片上下文" value={draft.document_image_context_size} onChange={(value) => setValue('document_image_context_size', value)} />
      </FormGrid>
    )
  }

  if (id === 'database') {
    return (
      <FormStack>
        <div className="rounded-(--radius-control) border border-(--color-border-soft) bg-(--color-surface-2) px-3 py-2 text-[12px] text-(--color-text-muted)">
          当前连接：<span className="font-mono text-(--color-text)">{settingValueSummary(settings?.database_url)}</span>
        </div>
        <SecretField
          label="新的 Database URL"
          configured={settings?.database_url_configured}
          masked={settings?.database_url}
          value={draft.database_url}
          onChange={(value) => setValue('database_url', value)}
          placeholder="postgresql://user:password@host:5432/db"
        />
      </FormStack>
    )
  }

  if (id === 'upload') {
    return (
      <FormStack>
        <TextField label="上传目录" value={draft.upload_dir} onChange={(value) => setValue('upload_dir', value)} />
      </FormStack>
    )
  }

  return (
    <FormGrid>
      <TextField label="微信 Token 文件" value={draft.wechat_token_file} onChange={(value) => setValue('wechat_token_file', value)} />
      <NumberField label="消息分段大小" value={draft.wechat_message_chunk_size} onChange={(value) => setValue('wechat_message_chunk_size', value)} />
    </FormGrid>
  )
}

// 根据当前设置初始化弹窗草稿；敏感值不回填旧明文，只留空等待用户输入新值。
function buildDraft(id: SettingsCardId, settings?: SettingsSnapshot): SettingsPatchDraft {
  if (!settings) return {}
  if (id === 'chat' || id === 'kg-extraction') {
    return {
      chat_base_url: settings.chat_base_url ?? '',
      chat_api_key: '',
      chat_model: settings.chat_model ?? '',
    }
  }
  if (id === 'embedding') {
    return {
      embedding_base_url: settings.embedding_base_url ?? '',
      embedding_api_key: '',
      embedding_model: settings.embedding_model ?? '',
      embedding_dimensions: settings.embedding_dimensions ?? 1024,
    }
  }
  if (id === 'rerank') {
    return {
      rerank_base_url: settings.rerank_base_url ?? '',
      rerank_api_key: '',
      rerank_model: settings.rerank_model ?? '',
      rerank_input_size: settings.rerank_input_size ?? 50,
    }
  }
  if (id === 'mineru') {
    return {
      mineru_api_token: '',
      mineru_parse_timeout_seconds: settings.mineru_parse_timeout_seconds ?? 600,
      mineru_use_kb_packager: settings.mineru_use_kb_packager ?? true,
    }
  }
  if (id === 'rag') {
    return {
      rag_top_k: settings.rag_top_k ?? 5,
      rag_min_score: settings.rag_min_score ?? 0.35,
    }
  }
  if (id === 'chunking') {
    return {
      document_chunk_token_num: settings.document_chunk_token_num ?? 512,
      document_chunker_type: settings.document_chunker_type ?? 'naive',
      document_chunk_delimiter: settings.document_chunk_delimiter ?? '\n。；！？',
      document_chunk_overlap_percent: settings.document_chunk_overlap_percent ?? 0,
      document_children_delimiter: settings.document_children_delimiter ?? '',
      document_table_context_size: settings.document_table_context_size ?? 0,
      document_image_context_size: settings.document_image_context_size ?? 0,
    }
  }
  if (id === 'database') {
    return { database_url: '' }
  }
  if (id === 'upload') {
    return { upload_dir: settings.upload_dir ?? '' }
  }
  return {
    wechat_token_file: settings.wechat_token_file ?? '',
    wechat_message_chunk_size: settings.wechat_message_chunk_size ?? 1800,
  }
}

// 计算目标弹窗尺寸，让动画使用固定数值；高度按配置字段数量分档，避免少字段弹窗空旷。
function getModalFrame(cardId: SettingsCardId): ModalFrame {
  const width = Math.min(620, window.innerWidth - 32)
  const preferredHeight = modalPreferredHeight(cardId)
  const height = Math.min(preferredHeight, window.innerHeight - 48)
  return {
    left: Math.max(16, (window.innerWidth - width) / 2),
    top: Math.max(24, (window.innerHeight - height) / 2),
    width,
    height,
  }
}

// 根据弹窗内字段数量给出目标高度；超过视口时由 getModalFrame 截断并启用内部滚动。
function modalPreferredHeight(cardId: SettingsCardId): number {
  const headerAndFooter = 112
  const bodyPadding = 28
  const formRowHeight = 46
  const rowGap = 14
  const rows = modalFormRows(cardId)
  const contentHeight = rows * formRowHeight + Math.max(0, rows - 1) * rowGap
  return Math.max(280, headerAndFooter + bodyPadding + contentHeight)
}

// 估算弹窗主体需要的表单行数；两列表单按行计，说明块和操作条各算一行。
function modalFormRows(cardId: SettingsCardId): number {
  switch (cardId) {
    case 'rag':
    case 'upload':
      return 1
    case 'database':
      return 2
    case 'embedding':
    case 'rerank':
    case 'mineru':
    case 'wechat':
      return 2
    case 'chunking':
      return 4
    case 'chat':
      return 5
    case 'kg-extraction':
      return 6
  }
}

// 将设置值转成输入框字符串。
function textValue(value: unknown): string {
  return typeof value === 'string' ? value.trim() : value === null || value === undefined ? '' : String(value)
}

// 根据 Base URL 反推供应商预设，仅用于表单显示。
function presetIdFromBaseUrl(baseUrl: string): string {
  const preset = PROVIDER_PRESETS.find((item) => item.base_url === baseUrl)
  return preset?.id ?? ''
}

// 紧凑表单容器，适合弹窗内的单列配置。
function FormStack({ children }: { children: ReactNode }) {
  return <div className="flex flex-col gap-4">{children}</div>
}


// 双列表单容器，窄屏自动退成单列。
function FormGrid({ children }: { children: ReactNode }) {
  return <div className="grid grid-cols-1 gap-4 md:grid-cols-2">{children}</div>
}

// 普通文本字段，沿用项目统一 Input 控件。
function TextField({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string
  value: unknown
  onChange: (value: string) => void
  placeholder?: string
}) {
  return (
    <FieldShell label={label}>
      <Input
        value={textValue(value)}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        spellCheck={false}
      />
    </FieldShell>
  )
}

// 数字字段仍以字符串草稿保存，后端 Settings 会做最终类型校验。
function NumberField({
  label,
  value,
  onChange,
  step,
}: {
  label: string
  value: unknown
  onChange: (value: string) => void
  step?: string
}) {
  return (
    <FieldShell label={label}>
      <Input
        type="number"
        step={step}
        value={textValue(value)}
        onChange={(event) => onChange(event.target.value)}
      />
    </FieldShell>
  )
}

// 敏感字段只允许输入新值，当前值只展示后端返回的脱敏摘要。
function SecretField({
  label,
  configured,
  masked,
  value,
  onChange,
  placeholder = '输入新值才会覆盖当前配置',
}: {
  label: string
  configured?: boolean
  masked?: string
  value: unknown
  onChange: (value: string) => void
  placeholder?: string
}) {
  return (
    <FieldShell
      label={label}
      hint={configuredSecretSummary(configured, masked)}
    >
      <Input
        type="password"
        value={textValue(value)}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        autoComplete="off"
        spellCheck={false}
      />
    </FieldShell>
  )
}

// 布尔设置使用开关式按钮，避免 checkbox 默认样式混入页面。
function ToggleField({
  label,
  value,
  onChange,
}: {
  label: string
  value: unknown
  onChange: (value: boolean) => void
}) {
  const checked = value === true || value === 'true'
  return (
    <FieldShell label={label}>
      <button
        type="button"
        onClick={() => onChange(!checked)}
        className={cn(
          'flex h-8 items-center justify-between rounded-(--radius-control) border px-2.5 text-[13px] transition-colors',
          checked
            ? 'border-(--color-primary)/50 bg-(--color-primary-soft) text-(--color-text)'
            : 'border-(--color-border) bg-(--color-surface-2) text-(--color-text-muted)',
        )}
      >
        <span>{checked ? '开启' : '关闭'}</span>
        <span
          className={cn(
            'h-4 w-7 rounded-full border transition-colors',
            checked ? 'border-(--color-primary) bg-(--color-primary)' : 'border-(--color-border) bg-(--color-surface-3)',
          )}
        />
      </button>
    </FieldShell>
  )
}

// 统一风格下拉菜单，替代原生 select 以避免浏览器默认弹层样式。
function DropdownField({
  label,
  value,
  options,
  onChange,
  placeholder = '选择',
}: {
  label: string
  value: string
  options: { value: string; label: string }[]
  onChange: (value: string) => void
  placeholder?: string
}) {
  const selected = options.find((option) => option.value === value)
  const [open, setOpen] = useState(false)
  return (
    <FieldShell label={label}>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <button
            type="button"
            className="flex h-8 w-full items-center justify-between rounded-(--radius-control) border border-(--color-border) bg-(--color-surface-2) px-2.5 text-left text-[13px] text-(--color-text) transition-colors hover:bg-(--color-surface-3) focus:outline-none focus:border-(--color-primary)/60"
          >
            <span className={cn('truncate', !selected && 'text-(--color-text-faint)')}>
              {selected?.label ?? placeholder}
            </span>
            <ChevronDown className="size-3.5 shrink-0 text-(--color-text-faint)" />
          </button>
        </PopoverTrigger>
        <PopoverContent align="start" className="min-w-[var(--radix-popover-trigger-width)]">
          {options.map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => {
                onChange(option.value)
                setOpen(false)
              }}
              className={cn(
                'flex h-8 w-full items-center rounded-(--radius-control) px-2 text-left text-[13px] transition-colors',
                option.value === value
                  ? 'bg-(--color-primary-soft) text-(--color-text)'
                  : 'text-(--color-text-muted) hover:bg-(--color-surface-2) hover:text-(--color-text)',
              )}
            >
              {option.label}
            </button>
          ))}
        </PopoverContent>
      </Popover>
    </FieldShell>
  )
}

// 表单字段外壳统一 label / hint 排版，保证弹窗里的控件高度稳定。
function FieldShell({
  label,
  hint,
  children,
}: {
  label: string
  hint?: string
  children: ReactNode
}) {
  return (
    <label className="flex min-w-0 flex-col gap-1.5">
      <span className="text-[11px] uppercase tracking-[0.12em] text-(--color-text-faint)">
        {label}
      </span>
      {children}
      {hint && <span className="truncate text-[11px] text-(--color-text-faint)">{hint}</span>}
    </label>
  )
}

// 设置页初次加载骨架，保持与最终卡片网格同等尺寸。
function SettingsSkeleton() {
  return (
    <div
      className="grid w-full justify-start gap-3"
      style={{ gridTemplateColumns: 'repeat(auto-fill, 280px)' }}
    >
      {Array.from({ length: 9 }).map((_, index) => (
        <div
          key={index}
          className="h-40 w-[280px] rounded-(--radius-card) border border-(--color-border) bg-(--color-surface)"
        >
          <motion.div
            className="h-full rounded-(--radius-card)"
            initial={{ opacity: 0.35 }}
            animate={{ opacity: 0.75 }}
            transition={{ repeat: Infinity, repeatType: 'reverse', duration: dur.slow, ease: ease.inOut }}
          />
        </div>
      ))}
    </div>
  )
}
