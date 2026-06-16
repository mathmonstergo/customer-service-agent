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
* 用户澄清：文档解析层的“轻量”指本地部署形态轻，能接 API 就接 API；不是指解析、后处理或 chunker 规则做简化版。
* 文档解析层的长期目标是准确高效地贴近 MinerU/RAGFlow 成熟行为，不能用“轻量分流”替代完整设计。
* 上一版 `feat(rag): 增加 MinerU 轻量 chunker 分流` 已因方向错误撤回。

## 第一阶段步骤

1. [x] 整理 RAGFlow v0.26.0 相比 v0.25.1 的 MinerU/后处理变更。
2. [x] 明确哪些 RAGFlow 行为应移植、适配或暂缓。
3. [x] 设计 page chrome 过滤策略：过滤正文污染，保留页码/bbox/证据。
4. [x] 设计 parent-child 检索调整：child 召回，parent 回填，避免同权竞争。
5. [x] 实现 MinerU 原始 `content_list` 的 page chrome/未知块过滤、HTML 文本清洗、HTML 表格行文本提取。
6. [x] 实现文档 parent 不参与普通向量/关键词候选竞争，保留 parent embedding 和 child 命中后的 parent 回填。
7. [ ] 后续再抽象完整 `MineruPostProcessor` 管线和多 chunker 分流，不纳入第一阶段 MVP。

## 文档解析层长期口径

1. [x] 撤回上一版“轻量 chunker 分流”实现，避免错误方向继续扩散。
2. [x] 重新对照 RAGFlow `naive/manual/qa/table` 的输入输出、元数据、表格行处理、QA 成对、标题层级、tokenize 和 parent-child 行为，形成更精确的移植清单。
3. [x] 设计“部署轻、规则不简化”的文档解析层：MinerU 可走 API，RAGFlow 作为参考代码库，不引入重型本地服务。
4. [x] 对每类解析/后处理/chunker 先定义验收样例和输出结构，再 TDD 实现；不要只靠启发式 `auto` 简化判断。
5. [ ] 确认是否需要显式配置 chunker 类型、文件类型默认映射、以及审核界面展示 chunker 来源。

## 预期效果

* MinerU 输出解析更健壮，兼容更多 zip/json 结构。
* 文档切片正文更干净，减少页眉页脚、页码、水印、HTML 标签污染。
* 表格、图片、标题、正文等 block 的处理更贴近 RAGFlow 成熟经验。
* 文档管理 UI 的页码、章节、来源证据不被破坏。
* 检索上下文更稳定，避免 parent/child 重复命中导致 prompt 膨胀。

## 需要用户确认的问题

* 文档解析层需要重新确认精确设计后再继续多 chunker：chunker 类型选择由文件类型/用户配置/自动识别中的哪一种主导。
* VLM 图片描述、本地 MinerU provider 和是否停用 parent embedding 后续单独确认。

## 第二阶段设计记录

* 已新增 `.trellis/tasks/06-16-mineru-ragflow-postprocessing/research/ragflow-chunker-behavior-map.md`，对照 RAGFlow `qa/table/manual/naive`、`rag/nlp` 和 parent-child 检索行为。
* 已新增 `docs/changes/20260616-100139-mineru-ragflow-postprocessing/chunker-behavior-design.md`，记录本项目适配设计。
* 设计结论：
  * 不引入 RAGFlow 重服务或存储模型；
  * MinerU 继续作为默认 API-first provider；
  * chunker 类型采用“显式配置优先 + 文件类型默认 + 辅助推荐”的设计；
  * `table` 每行一个 chunk，保留表头/行号/sheet 证据；
  * `qa` 每个问答对一个 chunk，坏行按 RAGFlow 追加到当前 answer 或记录 skipped；
  * `manual` 优先标题/outline/section 聚合，适合手册、SOP、政策类文档；
  * `naive` 保持当前 RAGFlow 风格 fallback，并做回归保护。
* 建议第二阶段 MVP：先不做 schema/UI 大改，`chunker_type` 可先落在 `source_offsets["chunker"]`；若需要正式字段或 UI 筛选，再单独确认。

## 第二阶段实现记录

* `customer_service_agent/document_parser.py`
  * `build_import_chunks_from_blocks()` 新增 `chunker_type` 参数，支持 `naive`、`manual`、`qa`、`table`。
  * `table` chunker 按 RAGFlow `table.py` 思路把每个数据行生成为一个审核切片，正文采用 `- 字段: 值`，并保留 `sheet_name`、`row_index`、`headers`、`field_map`、`table_html` 证据。
  * `qa` chunker 按 RAGFlow `qa.py` 思路把每个 Q/A pair 生成为一个审核切片；txt/csv 风格坏行在已有 question 后追加到 answer。
  * `manual` chunker 按标题/章节连续聚合 ParsedBlock，保留 `section_path`、页码和来源块证据。
  * 非 naive chunker 会在 `source_offsets["chunker"]` 记录采用的 chunker 类型。
* `customer_service_agent/config.py`
  * 新增 `DOCUMENT_CHUNKER_TYPE` / `Settings.document_chunker_type`，默认 `naive`，只允许 `naive/manual/qa/table`。
* `customer_service_agent/admin_server.py`
  * 设置快照、租户设置持久化和文档解析入口均接入 `document_chunker_type`。

## 第二阶段验证记录

* `conda run -n customer-service-agent python -m pytest tests/test_document_parser.py::test_build_import_chunks_table_chunker_outputs_one_chunk_per_row_with_evidence tests/test_document_parser.py::test_build_import_chunks_qa_chunker_appends_malformed_rows_to_current_answer tests/test_document_parser.py::test_build_import_chunks_manual_chunker_groups_blocks_by_section_path -q`：先红灯，缺少 `chunker_type` 参数；实现后 3 passed。
* `conda run -n customer-service-agent python -m pytest tests/test_config.py::test_settings_from_env_parses_required_values tests/test_config.py::test_settings_from_env_parses_document_chunking_values tests/test_config.py::test_settings_from_env_rejects_unknown_document_chunker_type tests/test_admin_server.py::test_admin_app_settings_snapshot_exposes_runtime_config_for_local_modal tests/test_admin_server.py::test_admin_app_update_settings_persists_local_tenant_settings_and_refreshes_runtime_config tests/test_admin_server.py::test_admin_app_update_settings_preserves_document_chunking_when_payload_omits_fields tests/test_admin_server.py::test_admin_app_build_document_import_chunks_passes_configured_chunker_type -q`：先红灯，配置/管理端未接入；实现后 7 passed。
* `conda run -n customer-service-agent python -m pytest tests/test_document_parser.py tests/test_config.py tests/test_admin_server.py::test_admin_app_build_document_import_chunks_passes_configured_chunker_type tests/test_admin_server.py::test_admin_app_settings_snapshot_exposes_runtime_config_for_local_modal tests/test_admin_server.py::test_admin_app_update_settings_persists_local_tenant_settings_and_refreshes_runtime_config tests/test_admin_server.py::test_admin_app_update_settings_preserves_document_chunking_when_payload_omits_fields -q`：35 passed。
* `conda run -n customer-service-agent python -m ruff check customer_service_agent/document_parser.py customer_service_agent/config.py customer_service_agent/admin_server.py tests/test_document_parser.py tests/test_config.py tests/test_admin_server.py`：All checks passed。

## 文档解析层纠偏记录

* 2026-06-16：用户指出“不要做轻量分流”，准确高效优先。
* 2026-06-16：用户进一步澄清，该口径不是只针对第二阶段，而是针对文档解析这一层。
* 纠偏结论：撤回上一版简化分流实现；文档解析层后续必须先研究并对齐 MinerU/RAGFlow 真实行为，再做本项目适配。
* 边界保持：轻量化指部署/依赖形态，优先 API 接入 MinerU；不引入 RAGFlow 重服务，但解析、后处理和 chunker 规则不能因部署轻而降低质量。

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
