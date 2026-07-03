import assert from 'node:assert/strict'
import test from 'node:test'
import {
  buildAssistantSourceGroupTarget,
  buildAssistantSourceTargetKey,
  findAssistantSourceTargetIndex,
} from './source-target.ts'

test('builds stable target keys for faq and document sources', () => {
  assert.equal(
    buildAssistantSourceTargetKey({
      source_type: 'faq',
      source_id: 'faq_1',
      id: 'kc_faq_1',
    }),
    'faq:faq_1:kc_faq_1',
  )
  assert.equal(
    buildAssistantSourceTargetKey({
      source_type: 'document',
      source_id: 'imp_1',
      source_chunk_id: 'chunk_1',
      id: 'kc_chunk_1',
    }),
    'document:imp_1:chunk_1',
  )
})

test('source group target selects first matching drawer source', () => {
  const sources = [
    { source_type: 'faq', source_id: 'faq_1', id: 'kc_faq_1' },
    { source_type: 'document', source_title: '手册.pdf', source_id: 'imp_1', source_chunk_id: 'c1' },
    { source_type: 'document', source_title: '手册.pdf', source_id: 'imp_1', source_chunk_id: 'c2' },
  ]

  const target = buildAssistantSourceGroupTarget(sources[1])

  assert.equal(findAssistantSourceTargetIndex(sources, target), 1)
})
