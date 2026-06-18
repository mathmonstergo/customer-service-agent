# Journal - sensen (Part 1)

> AI development session journal
> Started: 2026-06-15

---



## Session 1: 平台问答页正确性修复

**Date**: 2026-06-15
**Task**: 平台问答页正确性修复
**Branch**: `main`

### Summary

修复文档重解析旧向量残留、平台问答页敏感问题短路拒答、SSE/来源字段契约，并忽略本地 agent/trellis 目录。

### Main Changes

- Added `import_files.chunker_type` persistence and idempotent SQL migration.
- Added parse-job and reparse payload support for file-level `chunker_type`.
- Ensured MinerU finish/reparse uses the file record chunker when calling RAGFlow-derived post-processing.
- Added document drawer chunker selector and list/header chunker display.
- Added backend regression tests and updated parser contract specs.

### Git Commits

| Hash | Message |
|------|---------|
| `cbac7d3` | (see git log) |
| `3f2f1b6` | (see git log) |
| `8d7f32f` | (see git log) |

### Testing

- [OK] `conda run -n customer-service-agent python -m pytest -q` -> 242 passed.
- [OK] `conda run -n customer-service-agent python -m ruff check customer_service_agent/admin_server.py customer_service_agent/db/imports.py tests/test_admin_server.py tests/test_db.py`
- [OK] `conda run -n customer-service-agent python -m customer_service_agent.cli check-config`
- [OK] `npm run build` in `web/`
- [OK] `npx eslint src/api/hooks.ts src/api/schemas.ts src/pages/documents/chunker-options.ts src/pages/documents/document-drawer.tsx src/pages/documents/document-list.tsx` in `web/`
- Known pre-existing: full `npm run lint` and full `ruff check .` still fail outside this task's touched files.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 2: MinerU RAGFlow 多 chunker 后解析

**Date**: 2026-06-16
**Task**: MinerU RAGFlow 多 chunker 后解析
**Branch**: `main`

### Summary

对齐 RAGFlow naive/manual/qa/table 后解析，新增 DOCUMENT_CHUNKER_TYPE，完成测试验证并归档任务。

### Main Changes

- Fixed `.trellis/scripts/common/*` ruff failures while preserving the shared script re-export API.
- Split non-component UI exports into sibling utility modules so React Fast Refresh lint passes.
- Reworked page draft/page-reset state to avoid synchronous `setState` inside effects.
- Recorded the Fast Refresh export convention in `.trellis/spec/frontend/quality.md`.

### Git Commits

| Hash | Message |
|------|---------|
| `3283818` | (see git log) |

### Testing

- [OK] `conda run -n customer-service-agent python -m ruff check .`
- [OK] `npm run lint` in `web/`
- [OK] `npm run build` in `web/`
- [OK] `conda run --no-capture-output -n customer-service-agent python -m pytest -q` (242 passed)
- [OK] `conda run -n customer-service-agent python -m customer_service_agent.cli check-config`
- [OK] `git diff --check`

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 3: Document file chunker selection

**Date**: 2026-06-18
**Task**: Document file chunker selection
**Branch**: `main`

### Summary

Implemented file-level document chunker persistence, parse-job override, UI selection/display, tests, and specs for MinerU/RAGFlow post-processing.

### Main Changes

- Added readable provenance fields to retrieval evaluation candidate payloads.
- Added one-click expected source/chunk labeling from TopK candidates in the evaluation workbench.
- Moved raw expected ID inputs into an advanced drawer section and documented the contract in code-spec.

### Git Commits

| Hash | Message |
|------|---------|
| `8a5b174` | (see git log) |
| `4992b1a` | (see git log) |

### Testing

- [OK] `conda run -n customer-service-agent python -m ruff check .`
- [OK] `conda run --no-capture-output -n customer-service-agent python -m pytest -q`
- [OK] `conda run -n customer-service-agent python -m customer_service_agent.cli check-config`
- [OK] `npm run lint` in `web/`
- [OK] `npm run build` in `web/`
- [OK] `git diff --check`

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 4: Lint and ruff quality gate cleanup

**Date**: 2026-06-18
**Task**: Lint and ruff quality gate cleanup
**Branch**: `main`

### Summary

Restored full backend ruff and frontend lint/build quality gates, documented Fast Refresh export convention, and archived the cleanup task.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `ca07f01` | (see git log) |
| `e992a98` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 5: 评测候选标注逻辑优化

**Date**: 2026-06-18
**Task**: 评测候选标注逻辑优化
**Branch**: `main`

### Summary

完成评测工作台从候选结果一键标注期望来源/切片，补充候选可读来源字段、前端展示和代码规格记录。

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `ccd9615` | (see git log) |
| `04e3543` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 6: 评测批量回归诊断 MVP

**Date**: 2026-06-18
**Task**: 评测批量回归诊断 MVP
**Branch**: `main`

### Summary

完成评测工作台批量回归 MVP：前端顺序运行 active 用例、实时进度、汇总指标、失败诊断卡、纯函数测试和前端 code-spec。

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `7689b92` | (see git log) |
| `41b5e2b` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete
