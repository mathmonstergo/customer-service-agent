import assert from 'node:assert/strict'
import test from 'node:test'
import {
  confidencePercent,
  evidenceSummary,
  kgReviewStatusLabel,
  relationTitle,
} from './helpers.ts'

test('maps KG review statuses to operator-facing labels', () => {
  assert.equal(kgReviewStatusLabel('needs_review'), '待审核')
  assert.equal(kgReviewStatusLabel('usable'), '已确认')
  assert.equal(kgReviewStatusLabel('disabled'), '已停用')
  assert.equal(kgReviewStatusLabel('unknown'), 'unknown')
})

test('formats confidence as a stable percentage', () => {
  assert.equal(confidencePercent(0.923), '92%')
  assert.equal(confidencePercent(null), '未标注')
  assert.equal(confidencePercent(undefined), '未标注')
})

test('builds compact evidence summaries', () => {
  assert.equal(
    evidenceSummary({
      source_title: '检索技术白皮书',
      section_path: ['2.1 混合检索', '召回策略'],
      page_start: 12,
      page_end: 13,
    }),
    '检索技术白皮书 / 2.1 混合检索 / 召回策略 / 第 12-13 页',
  )
})

test('formats relation title from head, type and tail', () => {
  assert.equal(
    relationTitle({
      head_entity_name: '混合检索',
      relation_type: '优化',
      tail_entity_name: '召回率',
    }),
    '混合检索 - 优化 - 召回率',
  )
})
