import assert from 'node:assert/strict'
import test from 'node:test'
import {
  buildSettingsPatch,
  configuredSecretSummary,
  kgExtractionConfigSummary,
  settingValueSummary,
} from './settings-model.ts'

test('omits blank sensitive values when building settings patch', () => {
  const patch = buildSettingsPatch({
    chat_base_url: ' https://api.deepseek.com ',
    chat_api_key: '   ',
    chat_model: ' deepseek-chat ',
    embedding_api_key: '',
    mineru_api_token: '',
    rerank_api_key: 'new-rerank-key',
  })

  assert.deepEqual(patch, {
    chat_base_url: 'https://api.deepseek.com',
    chat_model: 'deepseek-chat',
    rerank_api_key: 'new-rerank-key',
  })
})

test('summarizes configured secrets without exposing plain values', () => {
  assert.equal(configuredSecretSummary(true, 'sk-••••••97b'), '已配置 · sk-••••••97b')
  assert.equal(configuredSecretSummary(true, ''), '已配置')
  assert.equal(configuredSecretSummary(false, ''), '未配置')
})

test('summarizes regular settings compactly for cards', () => {
  assert.equal(settingValueSummary('  deepseek-chat  '), 'deepseek-chat')
  assert.equal(settingValueSummary(''), '未配置')
  assert.equal(settingValueSummary(null), '未配置')
  assert.equal(settingValueSummary(1024), '1024')
})

test('summarizes KG extraction as following chat defaults', () => {
  assert.deepEqual(
    kgExtractionConfigSummary({
      chat_base_url: 'https://api.deepseek.com',
      chat_model: 'deepseek-chat',
      chat_api_key_configured: true,
      chat_api_key: 'sk-••••••97b',
    }),
    ['跟随 Chat 默认', 'DeepSeek 官方 · deepseek-chat', '已配置 · sk-••••••97b'],
  )
})
