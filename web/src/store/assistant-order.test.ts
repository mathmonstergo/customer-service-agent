import assert from 'node:assert/strict'
import test from 'node:test'
import { moveConversationIdToFront } from './assistant-order.ts'

test('moves the active conversation to the latest position after it receives a message', () => {
  assert.deepEqual(moveConversationIdToFront(['a', 'b', 'c'], 'b'), ['b', 'a', 'c'])
})

test('keeps conversation order stable when the active conversation id is unknown', () => {
  assert.deepEqual(moveConversationIdToFront(['a', 'b'], 'x'), ['a', 'b'])
})
