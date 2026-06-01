// 智能问答页面。两栏布局 + 双抽屉。
// - 左侧：会话列表 sidebar（可折叠）
// - 中央：顶栏（标题 + 供应商按钮 + 流程详情按钮）→ 消息流 → 输入框
// - 右侧抽屉：流程详情（按需）
// - 弹层抽屉：会话级供应商配置
import { useEffect, useState } from 'react'
import { Settings2, Activity } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useAssistant, PROVIDER_PRESETS } from '@/store/assistant'
import { ConversationSidebar } from './assistant/conversation-list'
import { MessageStream } from './assistant/message-stream'
import { Composer } from './assistant/composer'
import { ProviderDrawer } from './assistant/provider-drawer'
import { DebugDrawer } from './assistant/debug-drawer'
import { useChatStream } from './assistant/use-chat-stream'

export default function AssistantPage() {
  const order = useAssistant((s) => s.conversationOrder)
  const currentId = useAssistant((s) => s.currentId)
  const conversations = useAssistant((s) => s.conversations)
  const newConversation = useAssistant((s) => s.newConversation)
  const debugOpen = useAssistant((s) => s.debugDrawerOpen)
  const setDebugOpen = useAssistant((s) => s.setDebugDrawerOpen)

  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [providerOpen, setProviderOpen] = useState(false)
  const [draft, setDraft] = useState('')
  const { send, abort, isStreaming } = useChatStream()

  // 进页面没有会话就建一个
  useEffect(() => {
    if (order.length === 0) {
      newConversation()
    }
  }, [order.length, newConversation])

  const conv = currentId ? conversations[currentId] : undefined
  const providerLabel = computeProviderLabel(conv?.provider)

  const onSend = () => {
    if (!currentId) return
    const q = draft
    setDraft('')
    void send(currentId, q)
  }

  return (
    <div className="flex h-full min-h-0">
      <ConversationSidebar
        collapsed={sidebarCollapsed}
        onToggle={() => setSidebarCollapsed((v) => !v)}
      />

      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex shrink-0 items-center gap-2 border-b border-(--color-border) bg-(--color-surface) px-5 py-3">
          <div className="min-w-0 flex-1">
            <div className="truncate text-[14px] text-(--color-text)" title={conv?.title}>
              {conv?.title || '新会话'}
            </div>
            <div className="mt-0.5 text-[11px] text-(--color-text-faint)">
              基于本地知识库 · 混合召回 + 流式生成
            </div>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setProviderOpen(true)}
            title="切换 / 配置供应商"
          >
            <Settings2 className="size-3.5" />
            <span className="max-w-[180px] truncate">{providerLabel}</span>
          </Button>
          <Button
            variant={debugOpen ? 'primary' : 'ghost'}
            size="sm"
            onClick={() => setDebugOpen(!debugOpen)}
            title="流程详情"
          >
            <Activity className="size-3.5" />
            流程详情
          </Button>
        </header>

        <div className="min-h-0 flex-1">
          {currentId ? (
            <MessageStream conversationId={currentId} />
          ) : (
            <div className="flex h-full items-center justify-center text-[13px] text-(--color-text-faint)">
              没有可用会话
            </div>
          )}
        </div>

        <Composer
          value={draft}
          onChange={setDraft}
          onSend={onSend}
          onAbort={abort}
          isStreaming={isStreaming}
          disabled={!currentId}
        />
      </main>

      {currentId && (
        <ProviderDrawer
          open={providerOpen}
          onOpenChange={setProviderOpen}
          conversationId={currentId}
        />
      )}
      {currentId && (
        <DebugDrawer
          open={debugOpen}
          onOpenChange={setDebugOpen}
          conversationId={currentId}
        />
      )}
    </div>
  )
}

function computeProviderLabel(provider?: {
  presetId?: string
  chat_base_url: string
  chat_api_key: string
  chat_model: string
}) {
  if (!provider) return '全局默认'
  const hasOverride =
    provider.chat_base_url.trim() &&
    provider.chat_api_key.trim() &&
    provider.chat_model.trim()
  if (!hasOverride) return '全局默认'
  const preset = PROVIDER_PRESETS.find((p) => p.id === provider.presetId)
  const left = preset?.label || '自定义'
  return `${left} · ${provider.chat_model}`
}
