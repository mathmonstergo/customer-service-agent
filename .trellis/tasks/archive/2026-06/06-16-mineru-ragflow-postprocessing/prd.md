# MinerU 后解析对齐 RAGFlow

## Goal

把本项目的 MinerU 后解析、切块、parent-child 和来源证据处理向 RAGFlow 最新做法靠齐，同时保留本项目已有的文档管理、切片审核、候选 FAQ、向量状态和来源追溯能力。目标不是机械复制 RAGFlow，而是在宏观上尊重 MinerU/RAGFlow 大团队的设计取舍，必要时调整本项目现有口径与其同步。

## What I Already Know

* 用户希望新的任务目标聚焦“向 RAGFlow 对 MinerU 的后解析靠齐”，覆盖各种文档类型。
* 用户明确要求搬运整理时结合本系统已有功能判断，例如不能因为 page chrome 过滤而丢失切片抽屉展示页码所需的证据字段。
* 本项目当前 PDF、docx、xlsx/xls 统一走 MinerU；Markdown 走微信聊天记录解析。
* 本项目当前 MinerU 输出会转成 `ParsedBlock`，再通过 RAGFlow naive merge 风格生成 `import_chunks`。
* 本项目已经有 `knowledge_chunks`、parent/child 字段和 parent 回填接口，但当前 parent 与 child 都会进入检索候选。
* RAGFlow 远端已有 `v0.26.0`，本地原先停在 `v0.25.1`；`v0.26.0` 含 MinerU 和 chunk 后处理相关更新。

## Requirements (Evolving)

* 对齐 RAGFlow v0.26.0 中 MinerU 后解析相关改进，并持续以 RAGFlow 最新稳定 tag 作为参考源。
* 将 RAGFlow 行为移植为本项目自己的轻量后处理层，不直接引入 RAGFlow 的租户模型、ES/Infinity、task executor、RAPTOR 等重型依赖。
* 保留本项目文档管理依赖的来源字段：页码、章节、block type、bbox/position、资产路径、table HTML 或等价证据。
* 对 page chrome、重复页眉页脚、页码文本、水印等噪音，只从可检索正文中过滤，不丢可追溯证据。
* 后续方案应考虑 parent-child 检索口径向 RAGFlow 靠齐：child 负责精准召回，parent 负责上下文回填。
* 第一阶段 MVP 采用“清洗 + parent-child 检索调整”：先做 MinerU 输出读取兜底、HTML/table 清洗、page chrome 过滤且保留证据，同时调整文档检索为 child 优先召回、parent 回填上下文。
* 第一阶段继续为 parent 行生成 embedding，避免破坏现有向量摘要和 UI 状态；但文档检索默认排除 `chunk_level = 'parent'`，parent 只通过 child 命中后回填进入回答上下文。

## Acceptance Criteria (Evolving)

* [x] RAGFlow v0.26.0 MinerU 后解析改进被整理成研究文档，并标注“移植 / 暂缓 / 不适用”的判断。
* [x] MinerU 后处理不会破坏文档管理切片列表/抽屉中的页码、章节、来源证据展示。
* [x] 过滤 page chrome 后，切片正文和 embedding 文本不再被页眉页脚/页码重复污染。
* [x] parent-child 检索行为有明确设计：避免 parent 与 child 同权竞争造成重复命中。
* [x] 文档 parent 行仍可生成/刷新 embedding，但不会作为普通向量或关键词候选参与融合排名。
* [x] 对 PDF、Word、Excel、Markdown/类 Markdown 输出、图片/表格资产分别定义处理策略。
* [x] 修改 Python 行为时补充对应单元测试，尤其覆盖 MinerU 输出归一化、证据保留、过滤规则和 parent-child 行为。
* [x] 用户确认第二阶段 `qa/table/manual/naive` chunker 适配设计后，再按 TDD 进入实现。
* [x] 第二阶段实现 `DOCUMENT_CHUNKER_TYPE` / `chunker_type`，支持 `naive/manual/qa/table`，并保留 import review 和来源证据。

## Definition of Done

* Tests added/updated for parser post-processing and retrieval behavior.
* `python -m pytest` relevant tests pass, or final notes explain local blockers.
* `python -m ruff check .` pass, or final notes explain local blockers.
* `python -m customer_service_agent.cli check-config` pass, or final notes explain local blockers.
* `docs/changes/20260616-100139-mineru-ragflow-postprocessing/` updated with plan and confirmation.
* No user materials, upload originals, prompts, tokens, or sensitive files are committed.

## Open Questions

* 无阻塞问题；等待用户确认完整需求后进入实现。

## Out of Scope (Temporary)

* 不引入 RAGFlow 全套服务、任务执行器、ES/Infinity/OceanBase、RAPTOR 或 GraphRAG。
* 不把 MinerU 官方 API 替换成本地 MinerU 服务，除非后续单独确认。
* 不改动真实上传文件或提交用户材料。
* 第二阶段不引入 RAGFlow 服务、任务执行器、租户模型、ES/Infinity/OceanBase、RAPTOR 或 GraphRAG。
* 第二阶段不做简化的“轻量分流”；chunker 行为必须先映射 RAGFlow 行为，再以本项目字段适配。

## Decision (ADR-lite)

**Context**: 任务可从三个范围切入：只做 MinerU 清洗、清洗加 parent-child 检索调整、或一次纳入多 chunker 分流。  
**Decision**: 第一阶段采用“清洗 + parent-child 检索调整”。  
**Consequences**: 能同时解决 MinerU 输出污染和 parent/child 重复命中的核心问题，改动面可控；多 chunker 分流暂缓，但实现边界需要为后续 `qa/table/title-manual` 预留。

**Context**: parent 行可以继续生成 embedding、改为不生成 embedding，或仅在检索后做去重。  
**Decision**: 第一阶段继续生成 parent embedding，但文档检索默认排除 parent，parent 仅作为 child 命中后的上下文回填。  
**Consequences**: 该策略最小化 UI/向量摘要/刷新流程变动，同时修正 parent 与 child 同权竞争的问题；缺点是仍会消耗 parent embedding 成本，后续可单独评估是否改成不可嵌入上下文记录。

## Technical Notes

* Current task: `.trellis/tasks/06-16-mineru-ragflow-postprocessing/`
* Change record: `docs/changes/20260616-100139-mineru-ragflow-postprocessing/`
* Current project files likely impacted later:
  * `customer_service_agent/document_parser.py`
  * `customer_service_agent/chunking.py`
  * `customer_service_agent/admin_server.py`
  * `customer_service_agent/db/knowledge.py`
  * `customer_service_agent/db/builders.py`
  * `tests/test_document_parser.py`
  * `tests/test_chunking.py`
  * `tests/test_admin_server.py`
  * `tests/test_db.py`
* RAGFlow reference files inspected:
  * `/home/adam/projects/ragflow/deepdoc/parser/mineru_parser.py`
  * `/home/adam/projects/ragflow/rag/app/naive.py`
  * `/home/adam/projects/ragflow/rag/nlp/__init__.py`
  * `/home/adam/projects/ragflow/rag/svr/task_executor.py`
  * `/home/adam/projects/ragflow/rag/nlp/search.py`

## Research References

* `research/ragflow-v026-mineru-postprocessing.md` — RAGFlow v0.26.0 相比 v0.25.1 的 MinerU/后处理关键变化和移植判断。
* `research/ragflow-chunker-behavior-map.md` — RAGFlow `qa/table/manual/naive` 和 parent-child 检索行为映射。
* `docs/changes/20260616-100139-mineru-ragflow-postprocessing/chunker-behavior-design.md` — 本项目第二阶段 chunker 适配设计和待确认 MVP。

## Phase 2 Implementation Notes

* `DOCUMENT_CHUNKER_TYPE` is the runtime switch; allowed values are `naive`, `manual`, `qa`, `table`.
* `naive` remains the default and preserves previous behavior.
* Non-naive chunkers write route metadata to `source_offsets["chunker"]` rather than changing database schema.
* `table` row chunks keep headers, sheet name, row index, field map, and table HTML evidence.
* `qa` chunks keep question/answer and row evidence; malformed continuation rows append to the active answer.
* `manual` chunks group consecutive blocks by section title/path.
