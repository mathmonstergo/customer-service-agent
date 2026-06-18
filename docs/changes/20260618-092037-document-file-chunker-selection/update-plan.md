# 文档导入按文件选择 chunker

## 修改目标

在现有 MinerU 文档导入链路中增加文件级 `chunker_type` 选择和展示，使 `naive`、`manual`、`qa`、`table` 后解析策略能按文件使用，而不是只能依赖全局 `DOCUMENT_CHUNKER_TYPE`。

## 影响范围

* 后端导入文件数据模型和 API。
* MinerU 解析任务启动、完成、重新解析流程。
* 文档管理前端的详情抽屉和列表展示。
* 后端测试和前端构建产物。

## 具体步骤

1. [x] 补充导入文件数据层对 `chunker_type` 的持久化和默认值兼容。
2. [x] 让解析任务 payload 可传入 `chunker_type`，并在任务开始前保存到文件记录。
3. [x] 让 MinerU 切片构建阶段使用文件记录上的 `chunker_type`。
4. [x] 在文档详情抽屉增加 chunker 选择控件，并在开始解析时提交该值。
5. [x] 在列表或详情中展示当前 chunker，便于追溯。
6. [x] 按 TDD 补充后端测试，并运行项目验证命令。

## 预期效果

混合导入 PDF/manual/SOP、FAQ 表、结构化表格时，用户可以在文件级选择合适的 RAGFlow 风格后处理 chunker；系统仍保持 MinerU 默认解析 provider 和审核后入库的流程。

## 需要用户确认的问题

已在对话中确认：本阶段继续做文件级 chunker 选择，不做轻量自动分流；默认 MinerU provider；准确高效优先；参考 RAGFlow 后解析思路。

## 验证记录

* `conda run -n customer-service-agent python -m pytest -q`：242 passed。
* `conda run -n customer-service-agent python -m ruff check customer_service_agent/admin_server.py customer_service_agent/db/imports.py tests/test_admin_server.py tests/test_db.py`：通过。
* `conda run -n customer-service-agent python -m customer_service_agent.cli check-config`：通过。
* `python3 -m py_compile customer_service_agent/admin_server.py customer_service_agent/db/imports.py`：通过。
* `npm run build`（`web/`）：通过，并更新 `customer_service_agent/static/dist`。
* `npx eslint src/api/hooks.ts src/api/schemas.ts src/pages/documents/chunker-options.ts src/pages/documents/document-drawer.tsx src/pages/documents/document-list.tsx`（`web/`）：通过。
* `npm run lint`（`web/`）：失败，剩余为既有 lint 问题，主要在 UI 基础组件 Fast Refresh 规则、`FaqsPage.tsx`、`assistant/provider-drawer.tsx`、`documents/chunk-browser.tsx`、`faqs/faq-drawer.tsx` 的 `set-state-in-effect`。
* `conda run -n customer-service-agent python -m ruff check .`：失败，剩余为 `.trellis/scripts/common/*` 既有 ruff 问题。
