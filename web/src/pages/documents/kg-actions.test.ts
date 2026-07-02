import assert from 'node:assert/strict'
import test from 'node:test'
import {
  formatKgExtractionResult,
  shortDocumentId,
} from './kg-actions.ts'

test('formats KG extraction result with entity and relation counts', () => {
  assert.equal(
    formatKgExtractionResult({ entity_count: 3, relation_count: 2 }),
    'KG 候选已生成：3 个实体，2 条关系',
  )
})

test('shortens long document ids but keeps short ids intact', () => {
  assert.equal(shortDocumentId('chunk_abcdefghijklmnopqrstuvwxyz'), 'chunk_abcdef...')
  assert.equal(shortDocumentId('imp_123'), 'imp_123')
})
