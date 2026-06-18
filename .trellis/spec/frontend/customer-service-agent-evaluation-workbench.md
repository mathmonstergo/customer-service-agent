# Customer Service Agent Evaluation Workbench

> Project-specific frontend contracts for retrieval evaluation workflows in the local admin UI.

## Scenario: Batch Regression Diagnostics MVP

### 1. Scope / Trigger

- Trigger: code modifies `web/src/pages/EvaluationPage.tsx`, `web/src/pages/evaluation/batch-diagnostics.ts`, `web/src/pages/evaluation/batch-panel.tsx`, or evaluation batch-run UI behavior.
- Reason: the evaluation workbench is the safety net for retrieval/chunking changes. Batch regression must remain lightweight while still separating real retrieval failures from unlabeled or not-yet-run cases.

### 2. Signatures

- Frontend pure function:
  - `buildEvaluationBatchSummary(cases: RetrievalEvalCase[]) -> EvaluationBatchSummary`
  - `diagnoseEvaluationCase(evalCase: RetrievalEvalCase) -> EvaluationCaseDiagnostic`
- Frontend component:
  - `EvaluationBatchPanel({ summary, runState, batchCaseCount, onRunBatch, onSelectCase })`
- Existing API dependency:
  - `POST /api/retrieval/eval-cases/{case_id}/run`

### 3. Contracts

- Batch MVP does not create a persistent batch/baseline record.
- Batch run reuses the single-case run API sequentially for the current filtered active cases.
- Each successful run must update the page's local `runOverrides`, so the case list, batch summary, and selected result panel reflect progress immediately.
- Batch summary reads current page state only:
  - active cases count;
  - labeled cases count;
  - run count;
  - average `recall_at_k`;
  - average `mrr`;
  - average `hit_rate_at_1`;
  - hit/missed/low-rank/granularity/empty/not-run/missing-expected counts.
- Missing expected source/chunk ids must not be counted as retrieval failure.
- Cases without a latest run must not be counted as retrieval failure.

### 4. Validation & Error Matrix

- No expected source/chunk ids -> reason `missing_expected`.
- Expected ids exist, no latest run -> reason `not_run`.
- Latest run has no candidates -> reason `empty_candidates`.
- Expected id is absent from TopK -> reason `missed`, unless a chunk-level case has a source-level match that indicates `granularity_mismatch`.
- Expected id rank is `1` -> reason `hit`.
- Expected id rank is `> 1` -> reason `low_rank`.
- A failed single-case run during batch increments the transient failed count and must not stop the remaining cases.

### 5. Good/Base/Bad Cases

- Good: user runs active cases, sees progress, and failing cards link back to the case detail.
- Good: unlabeled cases appear as "待标注" and guide the user to label them, not as retrieval failures.
- Base: page reload keeps only each case's persisted latest run; transient batch progress is reset.
- Bad: adding a backend batch table for the MVP before the workflow needs historical baselines.
- Bad: averaging missing metrics as zero, which would make unknown results look like failures.

### 6. Tests Required

- Node test for `buildEvaluationBatchSummary()` must assert:
  - unlabeled cases are counted as missing expected;
  - missed cases are counted separately;
  - low-rank hits still count as hits and low-rank diagnostics;
  - average metrics ignore unknown values.
- Frontend `npm test`, `npm run lint`, and `npm run build` must pass.
- Browser verification should load `/#/evaluation` and confirm the batch panel renders.

### 7. Wrong vs Correct

#### Wrong

```typescript
const failed = cases.filter((item) => item.latest_run?.metrics?.recall_at_k === 0)
```

This treats unlabeled and not-run cases as equivalent to retrieval failures.

#### Correct

```typescript
const summary = buildEvaluationBatchSummary(cases)
const failures = summary.diagnostics.filter(
  (item) => item.reason === 'missed' || item.reason === 'empty_candidates',
)
```

The UI can now explain whether the next action is labeling, running, or fixing retrieval.
