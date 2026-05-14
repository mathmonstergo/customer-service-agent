# 统一可检索知识单元表改动计划

## 修改目标

参考平台化知识库的抽象方式，新增 `knowledge_chunks` 统一可检索知识单元表，用于承载 FAQ、文档切片、网页和数据库等来源的可检索内容。第一步只落表结构和数据库映射能力，不切换现有 FAQ RAG 检索链路。

## 影响范围

- 数据库 schema：新增 `knowledge_chunks` 表、向量索引、全文检索表达式索引和常用过滤索引。
- 数据库层：新增 FAQ 与文档切片到统一知识单元的行映射方法，以及统一 upsert SQL。
- 测试：覆盖表结构关键字段、索引、FAQ 映射和文档切片映射。

## 具体步骤

1. 在 `tests/test_db.py` 中先写失败测试，锁定 FAQ 和文档切片映射后的字段形状。
2. 在 `tests/test_schema.py` 中检查 `knowledge_chunks` 表结构、向量索引、全文检索索引和唯一来源索引。
3. 修改 `sql/001_init.sql`，新增 `knowledge_chunks` 表。
4. 修改 `customer_service_agent/db.py`，新增映射方法与 `upsert_knowledge_chunk`。
5. 用 conda 运行聚焦测试、全量 pytest、ruff 和配置检查。

## 预期效果

- FAQ、文档切片、未来网页和数据库记录可以沉淀为统一 `knowledge_chunks`。
- 现有 FAQ 问答检索不受影响，仍使用 `faq_documents.embedding`。
- 后续可以新增混合检索节点，把 `knowledge_chunks` 作为向量检索、全文检索和 rerank 的统一候选来源。

## 暂不包含

- 不迁移现有 FAQ 数据到 `knowledge_chunks`。
- 不把智能问答 `/api/assistant/chat-stream` 切换到新表。
- 不实现 BM25 排序和 rerank 业务逻辑，仅预留全文检索索引和统一元数据结构。

## 完成记录

- 已新增 `knowledge_chunks` 表，包含来源类型、来源 id、原始内容、embedding 文本、全文检索文本、metadata、tags、状态、confidence、向量和 embedding 状态字段。
- 已新增向量 HNSW 索引、全文检索 GIN 表达式索引、metadata GIN 索引和常用状态/来源索引。
- 已新增 FAQ 与文档切片映射函数，后续可用于把 `faq_documents` 和 `import_chunks` 投影到统一检索表。
- 已新增 `Database.upsert_knowledge_chunk` 和集中维护的 upsert SQL。
- 已让 FAQ 生成 embedding 时同步写入 `knowledge_chunks`，避免新 FAQ 仍只存在旧检索表。
- 已新增 `sync-knowledge-chunks` CLI 命令，用于把已有 `embedding_status = ready` 的 FAQ 复用原向量投影到 `knowledge_chunks`。
- 已在文档管理详情抽屉新增 `生成 embedding` 按钮，仅当文档状态为 `needs_review` / `completed` 且已有切片时可点击。
- 已新增文档切片 embedding API：解析完成的文档会按切片逐条生成向量，并以 `source_type = document` 写入 `knowledge_chunks`。
- 已把智能问答 `vector_search` 节点切到 `knowledge_chunks`，不再只查旧 `faq_documents`；该检索不过滤 `confidence`，允许文档切片参与命中。
- 已用 `conda run -n customer-service-agent python -m customer_service_agent.cli init-db` 应用到当前配置数据库，返回 `database schema ok`。

## 验证记录

- `conda run -n customer-service-agent python -m pytest tests/test_db.py -q`：`8 passed`
- `conda run -n customer-service-agent python -m pytest -q`：`150 passed`
- `conda run -n customer-service-agent python -m ruff check .`：`All checks passed!`
- `conda run -n customer-service-agent python -m customer_service_agent.cli check-config`：`config ok`

## 后续追加验证记录

- `conda run -n customer-service-agent python -m pytest tests/test_db.py tests/test_admin_server.py::test_admin_app_save_import_candidate_writes_needs_review_faq_and_embeds tests/test_admin_server.py::test_admin_app_embed_import_file_requires_parsed_document tests/test_admin_server.py::test_admin_app_embed_import_file_writes_document_chunks_to_knowledge_chunks tests/test_admin_table_layout.py::test_document_management_exposes_embedding_button_only_for_parsed_files tests/test_cli.py::test_sync_knowledge_chunks_projects_ready_faqs -q`：`14 passed`
- `node --check customer_service_agent/static/admin.js`：通过
- `conda run -n customer-service-agent python -m pytest -q`：`155 passed`
- `conda run -n customer-service-agent python -m ruff check .`：`All checks passed!`
- `conda run -n customer-service-agent python -m customer_service_agent.cli check-config`：`config ok`
- `conda run -n customer-service-agent python -m customer_service_agent.cli init-db`：`database schema ok`
- `conda run -n customer-service-agent python -m customer_service_agent.cli sync-knowledge-chunks`：`synced 59 ready faq knowledge chunks`
- Playwright 静态页面检查：`pending` 文档的 `生成 embedding` 按钮禁用，`needs_review` 文档且有切片时按钮启用。
- `conda run -n customer-service-agent python -m pytest tests/test_db.py::test_search_knowledge_sql_reads_unified_chunks_without_confidence_filter tests/test_admin_server.py::test_admin_app_iter_assistant_chat_events_streams_basic_rag_trace -q`：`2 passed`
- `conda run -n customer-service-agent python -m ruff check customer_service_agent/db.py customer_service_agent/admin_server.py tests/test_db.py tests/test_admin_server.py`：`All checks passed!`
- 切换智能问答检索后的全量复测：
  - `conda run -n customer-service-agent python -m pytest -q`：`156 passed`
  - `conda run -n customer-service-agent python -m ruff check .`：`All checks passed!`
  - `conda run -n customer-service-agent python -m customer_service_agent.cli check-config`：`config ok`
  - `node --check customer_service_agent/static/admin.js`：通过
