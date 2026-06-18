import test from 'node:test'
import assert from 'node:assert/strict'
import type { RetrievalEvalCase } from '@/api/schemas'
import { buildEvaluationBatchSummary } from './batch-diagnostics.ts'

test('buildEvaluationBatchSummary separates unlabeled, missed, and low-rank cases', () => {
  const cases: RetrievalEvalCase[] = [
    {
      id: 'case_unlabeled',
      question: '如何导出报告？',
      intent: null,
      expected_source_ids: [],
      expected_chunk_ids: [],
      tags: [],
      note: null,
      status: 'active',
      latest_run: null,
    },
    {
      id: 'case_missed',
      question: '如何重置密码？',
      intent: null,
      expected_source_ids: ['faq_password'],
      expected_chunk_ids: [],
      tags: [],
      note: null,
      status: 'active',
      latest_run: {
        id: 'run_missed',
        case_id: 'case_missed',
        strategy: 'hybrid',
        metrics: { recall_at_k: 0, mrr: 0, hit_rate_at_1: 0 },
        analysis: {},
        retrieved_items: [
          { id: 'kc_other', source_id: 'faq_other', source_type: 'faq', channels: ['keyword'] },
        ],
      },
    },
    {
      id: 'case_low_rank',
      question: '售后电话是多少？',
      intent: null,
      expected_source_ids: ['faq_after_sale'],
      expected_chunk_ids: [],
      tags: [],
      note: null,
      status: 'active',
      latest_run: {
        id: 'run_low_rank',
        case_id: 'case_low_rank',
        strategy: 'hybrid',
        metrics: { recall_at_k: 1, mrr: 0.5, hit_rate_at_1: 0 },
        analysis: {},
        retrieved_items: [
          { id: 'kc_other_2', source_id: 'faq_other_2', source_type: 'faq', channels: ['vector'] },
          { id: 'kc_expected', source_id: 'faq_after_sale', source_type: 'faq', channels: ['keyword'] },
        ],
      },
    },
  ]

  const summary = buildEvaluationBatchSummary(cases)

  assert.equal(summary.caseCount, 3)
  assert.equal(summary.activeCaseCount, 3)
  assert.equal(summary.labeledCaseCount, 2)
  assert.equal(summary.missingExpectedCount, 1)
  assert.equal(summary.missedCount, 1)
  assert.equal(summary.lowRankCount, 1)
  assert.equal(summary.hitCount, 1)
  assert.equal(summary.averageRecall, 0.5)
  assert.deepEqual(
    summary.diagnostics.map((item) => [item.caseId, item.reason]),
    [
      ['case_unlabeled', 'missing_expected'],
      ['case_missed', 'missed'],
      ['case_low_rank', 'low_rank'],
    ],
  )
})
