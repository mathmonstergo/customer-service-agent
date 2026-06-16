# MinerU 后解析对齐 RAGFlow 计划

## 修改目标

向 RAGFlow 最新稳定版本对 MinerU 后解析和 chunk 后处理的做法靠齐，同时结合本项目现有文档管理、切片审核、候选 FAQ、向量状态和来源追溯能力做平衡取舍。

## 影响范围

预计后续会涉及：

* MinerU 结果读取和归一化：`customer_service_agent/document_parser.py`
* 通用切块和 parent-child 逻辑：`customer_service_agent/chunking.py`、`customer_service_agent/admin_server.py`
* 文档知识单元映射和检索：`customer_service_agent/db/builders.py`、`customer_service_agent/db/knowledge.py`
* 测试：`tests/test_document_parser.py`、`tests/test_chunking.py`、`tests/test_admin_server.py`、`tests/test_db.py`
* 可能的前端展示适配：文档管理切片抽屉、来源字段展示、过滤说明

## 当前已确认事实

* 本项目固定使用 MinerU 作为 PDF/Word/Excel 文档解析主路径。
* 本项目不能机械复制 RAGFlow，因为数据模型、任务执行、存储和审核流程不同。
* 用户要求宏观尊重 RAGFlow/MinerU 大团队的设计，有些地方可以调整本项目现有口径去同步。
* page chrome 过滤不能导致切片抽屉丢失页码等来源证据。

## 第一阶段步骤

1. [x] 整理 RAGFlow v0.26.0 相比 v0.25.1 的 MinerU/后处理变更。
2. [x] 明确哪些 RAGFlow 行为应移植、适配或暂缓。
3. [x] 设计 page chrome 过滤策略：过滤正文污染，保留页码/bbox/证据。
4. [x] 设计 parent-child 检索调整：child 召回，parent 回填，避免同权竞争。
5. [x] 实现 MinerU 原始 `content_list` 的 page chrome/未知块过滤、HTML 文本清洗、HTML 表格行文本提取。
6. [x] 实现文档 parent 不参与普通向量/关键词候选竞争，保留 parent embedding 和 child 命中后的 parent 回填。
7. [ ] 后续再抽象完整 `MineruPostProcessor` 管线和多 chunker 分流，不纳入第一阶段 MVP。

## 预期效果

* MinerU 输出解析更健壮，兼容更多 zip/json 结构。
* 文档切片正文更干净，减少页眉页脚、页码、水印、HTML 标签污染。
* 表格、图片、标题、正文等 block 的处理更贴近 RAGFlow 成熟经验。
* 文档管理 UI 的页码、章节、来源证据不被破坏。
* 检索上下文更稳定，避免 parent/child 重复命中导致 prompt 膨胀。

## 需要用户确认的问题

* 第一阶段无阻塞确认项；多 chunker 分流、VLM 图片描述、本地 MinerU provider 后续单独确认。

## 第一阶段实现记录

* `customer_service_agent/document_parser.py`
  * 原始 MinerU `content_list` 过滤 `header`、`footer`、`page_number`、`page_header`、`page_footer`、`page_aside_text`、`discarded` 和未知块类型，避免页眉页脚/页码/侧栏进入正文。
  * HTML 文本按 RAGFlow v0.26 思路做实体还原、换行标签处理、标签剥离和空白归一；保留中文尖括号等非 HTML 字面量。
  * HTML 表格转成 `列 | 列` 行文本参与检索，同时继续把原始 `table_html` 存入 evidence 供前端预览。
  * 正文块的 `page_number`、`position_tag`、`pdf_positions` 仍进入后续 chunk 证据，避免切片抽屉丢页码。
* `customer_service_agent/db/knowledge.py`
  * 向量直接检索和关键词直接检索增加 `(kc.source_type <> 'document' OR kc.chunk_level <> 'parent')`。
  * `_get_parent_context_chunks_sql()` 不加该过滤，parent 仍可作为 child 命中后的上下文回填。

## 验证记录

* `conda run -n customer-service-agent python -m pytest tests/test_document_parser.py::test_extract_blocks_from_mineru_content_list_filters_page_chrome_and_unknown_types tests/test_document_parser.py::test_extract_blocks_from_mineru_content_list_sanitizes_html_without_losing_raw_table tests/test_db.py::test_search_knowledge_sql_excludes_document_parent_from_direct_retrieval tests/test_db.py::test_search_knowledge_text_sql_excludes_document_parent_from_direct_retrieval -q`：4 passed。
* `conda run -n customer-service-agent python -m pytest tests/test_document_parser.py tests/test_db.py tests/test_admin_server.py::test_admin_app_iter_assistant_chat_events_expands_child_hits_with_parent_context -q`：50 passed。
* `conda run -n customer-service-agent python -m ruff check customer_service_agent/document_parser.py customer_service_agent/db/knowledge.py tests/test_document_parser.py tests/test_db.py`：All checks passed。
* `conda run -n customer-service-agent python -m pytest -q`：233 passed。
* `conda run -n customer-service-agent python -m customer_service_agent.cli check-config`：config ok。
