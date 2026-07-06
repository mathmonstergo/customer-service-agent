export type SettingsPatchValue = string | number | boolean | null | undefined

export type SettingsPatchDraft = Record<string, SettingsPatchValue>

export type KgExtractionSettingsSummaryInput = {
  chat_base_url?: string
  chat_model?: string
  chat_api_key?: string
  chat_api_key_configured?: boolean
}

const SENSITIVE_SETTING_KEYS = new Set([
  'chat_api_key',
  'embedding_api_key',
  'mineru_api_token',
  'rerank_api_key',
  'database_url',
])

const PROVIDER_LABELS: Record<string, string> = {
  'https://api.openai.com/v1': 'OpenAI',
  'https://api.deepseek.com': 'DeepSeek 官方',
  'https://api.moonshot.cn/v1': 'Moonshot Kimi',
  'https://dashscope.aliyuncs.com/compatible-mode/v1': '通义千问',
  'https://open.bigmodel.cn/api/paas/v4': '智谱 GLM',
}

// 生成设置保存 payload；敏感字段空值表示保留旧值，不能把空字符串提交成覆盖。
export function buildSettingsPatch(draft: SettingsPatchDraft): Record<string, string | number | boolean> {
  const patch: Record<string, string | number | boolean> = {}
  Object.entries(draft).forEach(([key, value]) => {
    if (value === null || value === undefined) return
    if (typeof value === 'string') {
      const trimmed = value.trim()
      if (SENSITIVE_SETTING_KEYS.has(key) && !trimmed) return
      patch[key] = trimmed
      return
    }
    patch[key] = value
  })
  return patch
}

// 给卡片展示密钥状态；后端只返回脱敏值，前端不尝试读取旧明文。
export function configuredSecretSummary(configured: boolean | undefined, masked: string | undefined): string {
  if (!configured) return '未配置'
  const text = (masked || '').trim()
  return text ? `已配置 · ${text}` : '已配置'
}

// 给设置卡片展示一行短摘要，空值统一显示未配置。
export function settingValueSummary(value: string | number | boolean | null | undefined): string {
  if (value === null || value === undefined) return '未配置'
  if (typeof value === 'boolean') return value ? '开启' : '关闭'
  const text = String(value).trim()
  return text || '未配置'
}

// 知识图谱实体/关系抽取当前使用全局 ChatClient，这里显式生成卡片摘要，避免用户误以为没有配置入口。
export function kgExtractionConfigSummary(settings: KgExtractionSettingsSummaryInput): string[] {
  const provider = providerSummary(settings.chat_base_url)
  const model = settingValueSummary(settings.chat_model)
  return [
    '跟随 Chat 默认',
    `${provider} · ${model}`,
    configuredSecretSummary(settings.chat_api_key_configured, settings.chat_api_key),
  ]
}

// 将常见 Base URL 压缩成供应商名，未命中时回退到 URL 本身。
export function providerSummary(baseUrl: string | undefined): string {
  const text = (baseUrl || '').trim()
  return PROVIDER_LABELS[text] ?? settingValueSummary(text)
}
