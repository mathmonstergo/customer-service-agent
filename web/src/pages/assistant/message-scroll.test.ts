import assert from 'node:assert/strict'
import test from 'node:test'
import { shouldAutoScrollMessageStream } from './message-scroll.ts'

test('auto-scrolls to latest when entering a different conversation', () => {
  assert.equal(
    shouldAutoScrollMessageStream({
      didConversationChange: true,
      distanceToBottom: 1200,
      lastMessageRole: 'assistant',
    }),
    true,
  )
})

test('keeps historical reading position when the same conversation receives assistant updates far from bottom', () => {
  assert.equal(
    shouldAutoScrollMessageStream({
      didConversationChange: false,
      distanceToBottom: 1200,
      lastMessageRole: 'assistant',
    }),
    false,
  )
})
