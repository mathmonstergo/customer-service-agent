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

## Scenario: Readable Candidate Provenance

### 1. Scope / Trigger

- Trigger: code modifies `web/src/pages/evaluation/result-panel.tsx`, `web/src/pages/evaluation/helpers.ts`, `web/src/pages/EvaluationPage.tsx`, or backend retrieval evaluation candidate payloads.
- Reason: evaluation candidates are used by non-developer users to label expected hits. The UI must show readable FAQ/document provenance first and keep raw ids as secondary troubleshooting data.

### 2. Signatures

- Backend payload function:
  - `retrieval_eval_item_payload(candidate) -> RetrievalEvalItem`
- Frontend helper functions:
  - `candidateSourceLabel(item: RetrievalEvalItem) -> string`
  - `candidateLocationLabel(item: RetrievalEvalItem) -> string`
  - `candidateExcerpt(item: RetrievalEvalItem) -> string`
  - `displayStrategyLabel(value?: string | null) -> string`
  - `retrievalChannelLabel(value: string) -> string`
- Frontend source drawers:
  - `FaqDrawer({ faqId, onClose, onCreated })`
  - `DocumentDrawer({ fileId, onClose })`
  - `useUi().setOpenImportFileId(fileId, sourceChunkId?)`

### 3. Contracts

- `RetrievalEvalItem` must preserve:
  - `id`: knowledge chunk id, used for chunk-level expected hit matching.
  - `source_id`: FAQ id for FAQ candidates; import file id for document candidates.
  - `source_chunk_id`: import chunk id for document candidates when available; used to position `DocumentDrawer`.
  - `source_type`: `faq` or `document`.
  - `source_title`, `section_path`, `page_start`, `page_end`, `block_type`, `content`, `metadata`: readable document provenance fields.
  - `question`, `answer`, `category`, `tags`: readable FAQ fields.
  - `channels`, `fused_score`, `vector_score`, `keyword_score`: ranking diagnostics.
- Evaluation UI must open source drawers rather than create a separate preview:
  - FAQ candidate -> `setOpenFaqId(item.source_id)`.
  - Document candidate -> `setOpenImportFileId(item.source_id, item.source_chunk_id ?? null)`.
- Raw ids remain visible only as secondary rows with explicit copy icon buttons.
- Copy buttons must have `title`/`aria-label` and `cursor-pointer`.

### 4. Validation & Error Matrix

- Missing FAQ `question` but `source_title` exists -> use `source_title`.
- Missing FAQ `answer` but `content` exists -> use `content`.
- Missing document `source_chunk_id` -> open the document drawer without forced chunk positioning.
- Missing `navigator.clipboard.writeText` or copy failure -> show a toast error; do not silently fail.
- Unknown strategy/channel/source type -> display the raw value for troubleshooting.

### 5. Good/Base/Bad Cases

- Good: FAQ candidate shows question, answer excerpt, `查看 FAQ`, and copy icons for source/chunk ids.
- Good: Document candidate shows file name, page/section/chunk position, excerpt, `查看切片`, and opens the existing document drawer.
- Base: If source metadata is incomplete, UI falls back to id text and still allows copy.
- Bad: Showing only `source_id/chunk_id` as the primary candidate text.
- Bad: Creating a one-off evaluation preview drawer instead of reusing FAQ/document drawers.

### 6. Tests Required

- Node test for `helpers.ts` must assert:
  - FAQ helpers prefer `question` and `answer`.
  - document helpers include page, section, source chunk id, and excerpt.
  - internal strategy/source labels are translated where known.
- Python test for `retrieval_eval_item_payload()` must assert FAQ `question`, `answer`, `category`, and `tags` are included.
- Frontend `npm test`, `npm run lint`, and `npm run build` must pass.
- Backend `python -m pytest`, `python -m ruff check .`, and `python -m customer_service_agent.cli check-config` must pass when the environment is available.

### 7. Wrong vs Correct

#### Wrong

```tsx
<div>source {item.source_id} · chunk {item.id}</div>
```

This makes users label expected hits by opaque ids and hides the actual provenance.

#### Correct

```tsx
<div>{candidateSourceLabel(item)}</div>
<div>{candidateLocationLabel(item)}</div>
<button title="打开对应 FAQ 抽屉">查看 FAQ</button>
```

Readable provenance is primary; ids are secondary copy actions.

## Scenario: Shared Admin Drawer And Icon Button Conventions

### 1. Scope / Trigger

- Trigger: code modifies admin drawers, drawer widths, icon-only buttons, popover/select controls, or confirmation dialogs.
- Reason: the local admin UI should feel like one tool. New pages must reuse existing controls instead of inventing separate button/drawer/dialog structures.

### 2. Signatures

- Drawer width constants:
  - `DRAWER_WIDTH_COMPACT = 520`
  - `DRAWER_WIDTH_MEDIUM = 560`
- Shared components:
  - `Button`, `Drawer`, `Dialog`, `Popover`, `Tooltip`, `Badge`, `toast`

### 3. Contracts

- Default drawer width is compact (`520px`) unless the content needs a documented medium width.
- FAQ/evaluation/simple editing drawers should use compact width.
- Document chunk browsing can use medium width when compact width would make the toolbar and chunk browser too cramped.
- Icon-only buttons must include `title` or tooltip-equivalent text and `cursor-pointer`.
- Hard-to-understand primary actions may use short text + icon.
- Dangerous actions must keep danger styling and explicit confirmation through the existing `Dialog` component.
- Native `select` should not be used for dark-theme popups when an existing Popover/Button menu can provide stable contrast.
- Common function button mapping:
  - Start/run actions -> `Play` icon + short verb text, e.g. `开始解析`, `运行单条`.
  - Close actions -> `X` icon for explicit close buttons; text cancel remains `取消` when it means aborting a form/dialog.
  - Save actions -> `Save` icon + `保存` / `保存修改` text.
  - Embedding actions -> `Waypoints` icon + `Embedding` text across FAQ, document, and chunk-level embedding; use loading spinner while pending.
  - Regenerate chunk embedding must not use refresh icons; it is still an Embedding action.
  - Download actions -> `Download` icon.
  - Disable/enable visibility at chunk level -> `EyeOff` / `Eye`; document-level power state -> `PowerOff` / `Power`.
  - Delete actions -> `Trash2` icon with danger styling and existing `Dialog` confirmation.

### 4. Validation & Error Matrix

- Icon button lacks title/tooltip -> fix before commit.
- Clickable icon lacks pointer cursor -> fix before commit.
- New drawer hardcodes a width already covered by shared constants -> use the constant.
- New destructive action uses `confirm()` -> replace with existing dialog.
- New dropdown has unreadable dark-theme popup -> replace with existing Popover/Button pattern.

### 5. Good/Base/Bad Cases

- Good: secondary toolbar actions are icon-only with title and stable dimensions.
- Good: platform-wide function buttons reuse the semantic icon mapping above, so the same action has the same visual language across drawers.
- Good: Embedding buttons are `Waypoints + Embedding`, including chunk-level regeneration.
- Good: Chunker selection uses Popover/Button so dark theme is readable.
- Base: Main workflow buttons such as "开始解析" may keep short text.
- Bad: A new page creates local one-off drawer widths, button shapes, or custom popover markup.
- Bad: Different drawers use unrelated button styles for the same action type.

### 6. Tests Required

- Frontend lint and build must pass.
- Browser/manual verification should inspect any modified drawer at desktop width and confirm buttons do not overlap.
- If a pure display helper is added, add a Node test.

### 7. Wrong vs Correct

#### Wrong

```tsx
<select className="...">
  <option value="naive">Naive</option>
</select>
```

Native select popups can render outside the app theme and become unreadable in dark mode.

#### Correct

```tsx
<Popover>
  <PopoverTrigger asChild>
    <Button title="选择解析后的切块策略">Chunker</Button>
  </PopoverTrigger>
  <PopoverContent>{/* themed options */}</PopoverContent>
</Popover>
```

Use existing themed primitives for consistent dark-mode behavior.
