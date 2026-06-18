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

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `3283818` | (see git log) |

### Testing

- [OK] (Add test results)

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

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `8a5b174` | (see git log) |
| `4992b1a` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete
