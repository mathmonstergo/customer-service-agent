# 平台问答页正确性优先修复

## 修改目标

优先保证内部平台问答页能可信展示知识库效果：检索不被旧切片污染，解析/嵌入状态字段稳定，统一知识检索过滤口径清晰可测，并让问答页 SSE、特殊问题策略、来源字段保持前后端一致。

## 用户确认的范围

当前阶段只关注平台问答页正确性。微信、CLI、MCP、外部 API、权限、限流、审计、公司级治理模型都不做。

## 影响范围

* `customer_service_agent/db/imports.py`：导入文件重新解析和切片替换时的知识单元清理。
* `customer_service_agent/admin_server.py`：解析状态响应中的可选 embedding summary 兼容；智能问答敏感问题短路拒答；来源 payload 顶层 provenance 字段。
* `web/src/api/schemas.ts`、`web/src/pages/assistant/debug-drawer.tsx`、`web/src/pages/assistant/message-stream.tsx`：问答页来源字段类型/展示兜底与 lint 修正。
* `tests/test_admin_server.py`：解析状态、SSE 事件契约、敏感/实时策略、来源字段回归测试。
* `tests/test_db.py`：统一知识检索 SQL 过滤口径测试。
* `.trellis/spec/backend/customer-service-agent-assistant-contracts.md`：平台问答页 SSE、敏感短路、来源字段契约。

## 具体步骤

1. 补一个回归测试，证明 `replace_import_chunks()` 会清理同一文件旧的 document `knowledge_chunks`。
2. 修改 `replace_import_chunks()`，在替换 `import_chunks` 前同步删除该文件旧的 `knowledge_chunks`。
3. 修改 `_import_parse_status_payload()`，真实数据库仍返回 `embedding_summary`，测试替身缺少该方法时不抛错。
4. 更新统一知识检索 SQL 测试，使其断言 `COALESCE(fq.status, kc.status) = %(status)s`、embedding ready、文件/切片禁用过滤。
5. 运行聚焦测试、业务包 ruff、全量 pytest。
6. 第二阶段补充问答页 SSE 契约测试，覆盖 `meta`、`step`、`delta`、`done`、`error`。
7. 第二阶段敏感问题在意图识别后直接拒答，不做 embedding、检索或模型生成。
8. 第二阶段补充实时状态提示测试，确保模型 prompt 明确不能确认后台实时状态。
9. 第二阶段对齐后端来源 payload 与前端 `AssistantSource` 类型，顶层暴露章节、页码、block type、source offsets。

## 第二阶段计划

1. 检查平台问答页后端 `/api/assistant/chat-stream` 的事件序列和数据字段：`meta`、`step`、`delta`、`done`、`error`。
2. 检查前端 `AssistantPage` / `useChatStream` / SSE parser 是否完整消费事件并正确维护调试节点、来源、回答文本。
3. 检查无命中、敏感信息、实时状态类问题在问答页中的策略是否清晰，避免无依据确定回答。
4. 检查来源展示字段是否覆盖文件名、正文、parent context、检索通道和 score。
5. 只在发现真实契约缺口时补红灯测试并修复；不做视觉布局改造，不做微信/CLI/MCP/外部 API。

## 预期效果

* 文档重新解析后，平台问答页不会再召回旧切片向量。
* 文档解析状态接口字段稳定，页面轮询不因缺少辅助统计方法而失败。
* 检索 SQL 的测试断言与真实设计一致，后续改检索时更容易发现回归。
* 平台问答页遇到敏感问题不会表现成“检索到了答案”，实时状态问题会明确提示不能确认后台实时状态。
* 调试抽屉可以直接读取来源章节、页码、偏移、检索通道和 parent context，便于内部判断知识库效果。

## 实施记录

* 已修改 `ImportMixin.replace_import_chunks()`：替换导入切片前先删除同一文件的 document `knowledge_chunks`。
* 已修改 `AdminApp._import_parse_status_payload()`：数据库对象支持 `get_import_file_embedding_summary` 时继续返回 `embedding_summary`，轻量测试替身缺少该方法时不抛错。
* 已新增 `test_replace_import_chunks_removes_old_document_knowledge_chunks`，覆盖重新解析旧向量残留风险。
* 已更新统一知识检索 SQL 断言，匹配 FAQ 实时 status + knowledge chunk status 的过滤口径。
* 已新增 SSE 事件契约测试，覆盖问答页前端消费的 `meta`、`step`、`delta`、`done`、`error`。
* 已新增敏感问题短路拒答测试，证明不会继续 embedding、向量检索、关键词检索或模型生成。
* 已新增实时状态 prompt 测试，确保问题进入模型前带有“不能确认后台实时状态 / 不要编造后台实时状态”的约束。
* 已让 `assistant_document_payload()` 顶层输出 `section_path`、`page_start`、`page_end`、`block_type`、`source_offsets`。
* 已更新前端 `AssistantSource` 类型和调试抽屉页码读取，顶层字段优先、metadata 兜底。
* 已修正问答页 `message-stream.tsx` 的 conditional hook 和 markdown link 参数 lint 问题。
* 已新增平台问答页 assistant 契约 spec，沉淀 SSE 事件、敏感短路和来源 provenance 字段要求。

## 验证记录

* `conda run -n customer-service-agent python -m pytest tests/test_db.py::test_replace_import_chunks_removes_old_document_knowledge_chunks tests/test_admin_server.py::test_admin_app_starts_mineru_parse_job_without_blocking_for_result tests/test_admin_server.py::test_admin_app_polling_mineru_parse_status_updates_progress tests/test_admin_server.py::test_admin_app_polling_mineru_done_downloads_result_and_replaces_chunks tests/test_db.py::test_search_knowledge_sql_reads_unified_chunks_without_confidence_filter -q`：`5 passed`
* `conda run -n customer-service-agent python -m pytest tests/test_admin_server.py tests/test_db.py -q`：`93 passed`
* `conda run -n customer-service-agent python -m ruff check customer_service_agent tests`：通过
* `conda run -n customer-service-agent python -m pytest`：`228 passed`
* `conda run -n customer-service-agent python -m customer_service_agent.cli check-config`：`config ok`
* `conda run -n customer-service-agent python -m pytest tests/test_admin_server.py -q -k "sse_event_contract or sensitive_without_retrieval or realtime_prompt_marks_status_limit or provenance_fields or streams_hybrid_retrieval_trace or expands_child_hits"`：`6 passed`
* `./node_modules/.bin/eslint src/pages/assistant/debug-drawer.tsx src/pages/assistant/message-stream.tsx src/pages/assistant/use-chat-stream.ts src/lib/sse-assistant.ts src/api/schemas.ts`：通过
* `npm run build`：通过，已重建 `customer_service_agent/static/dist/` 前端产物；仅保留 Vite chunk size warning。
* `npm run lint`：未全量通过，剩余为既有 FAQ/通用 UI/provider drawer 的 React lint 规则问题，不属于本次平台问答正确性修复范围。

## 需要用户确认的问题

当前无阻塞问题。若后续发现平台问答页还存在答案来源展示或无命中策略问题，另行收敛范围后处理。
