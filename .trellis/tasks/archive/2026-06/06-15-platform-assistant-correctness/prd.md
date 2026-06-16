# 平台问答页正确性优先修复

## Goal

先保证内部平台的问答页能稳定、可信地展示知识库效果：检索只命中当前有效知识单元，解析/嵌入状态字段稳定，答案来源可追溯。当前阶段不处理微信、CLI、MCP、外部 API、权限、限流、审计或公司级治理模型。

## What I Already Know

* 用户明确要求优先保证平台问答页面正确。
* 微信入口不用管。
* CLI 是命令行入口，当前不用管。
* MCP 是给外部 agent 的 stdio 工具，当前不用管。
* 当前平台问答页调用 `/api/assistant/chat-stream`，主链路包含意图识别、向量召回、关键词召回、融合、可选 rerank、parent context 和答案生成。
* 当前测试套件有 4 个失败：3 个 MinerU 解析状态响应测试、1 个统一知识检索 SQL 断言。
* 当前 `replace_import_chunks()` 只删除 `import_chunks`，没有删除对应旧 `knowledge_chunks`，重解析后旧向量可能继续污染问答页检索。

## Requirements

* 修复文档重新解析后旧 `knowledge_chunks` 残留的问题，避免问答页命中已被替换的旧切片。
* 修复解析状态响应构造对测试替身数据库的硬依赖，同时保持真实页面返回 `embedding_summary`。
* 明确并测试统一知识检索的状态过滤口径：FAQ 读实时 `faq_documents.status`，文档读 `knowledge_chunks.status` 并叠加文件/切片禁用。
* 第二阶段检查平台问答页端到端事件流，确保前端能正确消费后端的 meta、step、delta、done/error 事件。
* 第二阶段检查无命中、敏感信息、实时状态类问题的问答页策略，不让页面表现成“有依据的确定回答”。
* 第二阶段检查来源展示字段是否能表达文件名、chunk 正文、parent context 和检索通道，便于内部判断知识库效果。
* 只修改平台问答页正确性相关的后端与测试，不扩展外部入口。
* 保持现有 React 页面 API 字段兼容，不做 UI 布局改造。

## Acceptance Criteria

* [x] 重新解析某个导入文件时，该文件旧的文档来源 `knowledge_chunks` 会被同步清理或失效，后续问答页不会召回旧切片。
* [x] MinerU 解析提交、轮询中、完成三个状态测试通过。
* [x] 统一知识检索 SQL 测试体现当前真实过滤口径，不再用过期字符串断言误报。
* [x] `conda run -n customer-service-agent python -m pytest` 通过，或仅剩与本任务无关且已说明的失败。
* [x] `conda run -n customer-service-agent python -m ruff check customer_service_agent tests` 通过。
* [x] 问答页 SSE 事件契约有测试覆盖，前端消费逻辑能稳定处理 step/delta/done/error。
* [x] 无命中、敏感信息、实时状态策略在后端或前端表现上有明确测试覆盖。
* [x] 来源展示所需字段在后端事件和前端类型/渲染中保持一致。

## Definition of Done

* Tests added or updated for behavior that affects问答页检索正确性。
* Existing behavior stays scoped to platform admin/question page.
* No changes to微信、CLI、MCP、外部 API、权限、限流、审计。
* Final response includes changed files, verification commands, remaining risks.

## Technical Approach

1. Add a regression test proving document reparse removes stale document `knowledge_chunks`.
2. Update `ImportMixin.replace_import_chunks()` so chunk replacement and stale knowledge cleanup happen in the same database transaction.
3. Make `_import_parse_status_payload()` tolerate lightweight database fakes by using `getattr(..., None)` for optional embedding summary support while preserving real runtime payload shape.
4. Update the SQL assertion test to check `COALESCE(fq.status, kc.status) = %(status)s` and disable filters, matching the actual intended query.
5. Inspect `AdminApp.iter_assistant_chat_events()` and frontend `useChatStream` / `AssistantPage` to verify event contract parity.
6. Add backend/frontend tests only where the inspection finds a concrete platform问答页 correctness gap.

## Decision (ADR-lite)

**Context**: The user wants internal knowledge-base retrieval precision before external API or governance work.

**Decision**: Prioritize correctness of the platform问答页 data path and defer all non-platform entrances and governance concerns.

**Consequences**: This keeps the MVP focused and lowers implementation risk. Later API/MCP/微信 parity may still need a separate task once the platform chain is proven.

## Out of Scope

* 微信服务 behavior.
* CLI command behavior.
* MCP tool behavior.
* 外部 HTTP API.
* 登录、权限、租户、限流、审计、成本统计。
* 知识图谱抽取和可视化实现。
* React 问答页布局调整。

## Technical Notes

* Main platform endpoint: `customer_service_agent/admin_server.py` `/api/assistant/chat-stream`.
* Relevant DB code: `customer_service_agent/db/imports.py`, `customer_service_agent/db/knowledge.py`.
* Relevant tests: `tests/test_admin_server.py`, `tests/test_db.py`.
* Business-code lint already passes with `conda run -n customer-service-agent python -m ruff check customer_service_agent tests`.
* Full repository ruff currently includes untracked `.trellis/` scripts and fails there; this task only gates business package and tests unless Trellis files are explicitly in scope.
