import test from 'node:test'
import assert from 'node:assert/strict'
import type { RetrievalEvalItem } from '@/api/schemas'
import {
  candidateExcerpt,
  candidateLocationLabel,
  candidateSourceLabel,
  displayStrategyLabel,
  sourceTypeLabel,
  summarizeExpected,
} from './helpers.ts'

test('candidate helpers prefer readable FAQ question and answer fields', () => {
  const item: RetrievalEvalItem = {
    id: 'kc_faq_1',
    source_id: 'faq_1',
    source_type: 'faq',
    source_title: null,
    question: '报告导出失败怎么办？',
    answer: '先检查账号权限，再重新生成报告。',
    channels: ['vector'],
  }

  assert.equal(candidateSourceLabel(item), '报告导出失败怎么办？')
  assert.equal(candidateExcerpt(item), '先检查账号权限，再重新生成报告。')
  assert.equal(candidateLocationLabel(item), 'FAQ')
})

test('candidate helpers keep document page and section trace readable', () => {
  const item: RetrievalEvalItem = {
    id: 'kc_doc_child_1',
    source_id: 'imp_1',
    source_type: 'document',
    source_chunk_id: 'chunk_1',
    source_title: '售后手册.pdf',
    section_path: ['售后', '报告导出'],
    page_start: 3,
    page_end: 4,
    block_type: 'text',
    content: '报告导出失败时，先检查账号权限和网络状态。',
    channels: ['vector', 'keyword'],
  }

  assert.equal(candidateSourceLabel(item), '售后手册.pdf')
  assert.equal(candidateLocationLabel(item), '页 3-4 · 售后 > 报告导出 · 审核切片 chunk_1 · text')
  assert.equal(candidateExcerpt(item), '报告导出失败时，先检查账号权限和网络状态。')
})

test('evaluation display labels hide internal English where possible', () => {
  assert.equal(displayStrategyLabel('retrieval_hybrid_v1'), '混合检索 v1')
  assert.equal(sourceTypeLabel('document'), '文档')
  assert.equal(sourceTypeLabel('faq'), 'FAQ')
  assert.equal(summarizeExpected({ expected_chunk_ids: ['chunk_1'] } as never), '1 个期望切片')
  assert.equal(summarizeExpected({ expected_source_ids: ['faq_1', 'faq_2'] } as never), '2 个期望来源')
  assert.equal(summarizeExpected({ expected_source_ids: [], expected_chunk_ids: [] } as never), '待设置期望命中')
})
