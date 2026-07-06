import assert from 'node:assert/strict'
import test from 'node:test'

const memoryStorage = new Map<string, string>()
Object.defineProperty(globalThis, 'localStorage', {
  configurable: true,
  value: {
    getItem: (key: string) => memoryStorage.get(key) ?? null,
    setItem: (key: string, value: string) => {
      memoryStorage.set(key, value)
    },
    removeItem: (key: string) => {
      memoryStorage.delete(key)
    },
  },
})
Object.defineProperty(globalThis, 'window', {
  configurable: true,
  value: { localStorage: globalThis.localStorage },
})

const { EMPTY_PROVIDER, useAssistant } = await import('./assistant.ts')

function makeConversation(id: string, title: string, updatedAt: number) {
  return {
    id,
    title,
    provider: EMPTY_PROVIDER,
    messages: [],
    createdAt: updatedAt,
    updatedAt,
  }
}

function resetAssistantStore() {
  useAssistant.setState({
    conversations: {},
    conversationOrder: [],
    currentId: null,
    modelsCache: {},
    debugDrawerOpen: false,
  })
}

test('selecting a conversation changes the chat panel without reordering the conversation list', () => {
  resetAssistantStore()
  useAssistant.setState({
    conversations: {
      latest: makeConversation('latest', '最新会话', 300),
      middle: makeConversation('middle', '中间会话', 200),
      old: makeConversation('old', '旧会话', 100),
    },
    conversationOrder: ['latest', 'middle', 'old'],
    currentId: 'latest',
  })

  useAssistant.getState().selectConversation('old')

  assert.equal(useAssistant.getState().currentId, 'old')
  assert.deepEqual(useAssistant.getState().conversationOrder, ['latest', 'middle', 'old'])
})
