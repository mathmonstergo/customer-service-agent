# 用户确认记录

## 已有确认

* 用户确认新的任务目标是：向 RAGFlow 对 MinerU 的后解析和各种文档类型处理靠齐，并根据本项目已有功能进行平衡。
* 用户强调需要宏观考虑，MinerU/RAGFlow 是大团队项目，有些设计有其合理性；必要时本项目应做出让步并与其同步。
* 用户指出 page chrome/页码过滤不能简单丢弃来源信息，否则会影响文档管理切片抽屉展示页码。
* 用户确认第一阶段先做方案 2：MinerU 输出清洗/证据保留 + parent-child 检索口径调整；完整多 chunker 分流后续再做。
* 用户确认 parent 行策略采用方案 1：继续生成 parent embedding，但检索默认排除 parent，parent 只通过 child 命中后回填上下文。

## 待确认

* 文档解析层第二阶段建议采用“显式配置优先 + 文件类型默认 + 辅助推荐”的 chunker 选择策略；等待用户确认后进入 TDD 实现。
* 第二阶段 MVP 建议先把 `chunker_type` 放入 `source_offsets["chunker"]`，暂不做 schema/UI 大改；如需要正式字段或 UI 筛选需单独确认。
* VLM 图片描述、本地 MinerU provider 和是否停用 parent embedding，后续单独确认。

## 2026-06-16 第一阶段实现后记录

* 已按用户确认先做方案 2：MinerU 输出清洗/证据保留 + parent-child 检索口径调整。
* 已按用户确认先做方案 1：parent 行继续生成 embedding，但文档 parent 不参与普通向量/关键词直接检索。
* 已保留正文块页码、bbox/position tag 和表格 HTML 证据；过滤只作用于 page chrome/未知块进入正文候选的路径。
* 已验证全量测试、Ruff 和配置检查通过。

## 2026-06-16 文档解析层纠偏确认

用户纠正：

* 不要做“轻量分流”。
* 本项目目标是准确高效，切块这类东西不能用简化规则糊过去。
* 之前说的轻量化指本地部署和依赖形态：能接 API 就接 API，而不是在 chunker 规则上降级。
* 这个口径不是只针对第二阶段，而是针对文档解析这一层。

记录结论：

* 已撤回上一版 `feat(rag): 增加 MinerU 轻量 chunker 分流` 实现。
* 后续文档解析层要重新以 MinerU/RAGFlow 真实行为为蓝本，先做精确设计和验收样例，再实现。
* 本项目仍保持 MinerU 默认 API 接入和部署轻量，但解析、后处理和 chunker 目标是准确高效、尽量对齐 RAGFlow。

## 2026-06-16 第二阶段设计待确认

已按用户要求开始下一阶段前置设计，并完成 RAGFlow 行为对照：

* `qa`：Q/A pair 一对一 chunk；txt/csv 坏行在已有 question 后追加到 answer；Markdown/Docx 标题栈形成 question path。
* `table`：每个数据行一个 chunk；表头必须有语义；多级表头、合并单元格、坏行、重复表头都要有明确处理。
* `manual`：面向手册/SOP/政策，按 outline、标题、章节和媒体上下文聚合。
* `naive`：继续作为普通 fallback，现有实现已覆盖 RAGFlow-style merge、children_delimiter、证据保留和媒体上下文。
* parent-child：继续 child 召回、parent 回填，不让 parent 和 child 同权竞争。

用户已确认可以开始按 `docs/changes/20260616-100139-mineru-ragflow-postprocessing/chunker-behavior-design.md` 的第二阶段 MVP 进入 TDD 实现。

## 2026-06-16 第二阶段实现记录

* 已按 TDD 实现 `DOCUMENT_CHUNKER_TYPE` / `document_chunker_type`，默认 `naive`，允许 `naive/manual/qa/table`。
* 已实现 `build_import_chunks_from_blocks(..., chunker_type=...)`：
  * `table`：每个表格数据行一个审核切片，保留表头、行号、sheet、table_html 等证据。
  * `qa`：每个问答对一个审核切片，txt/csv 风格坏行追加到当前 answer。
  * `manual`：按标题/章节连续聚合 ParsedBlock，保留 section path 和页码证据。
* 已接入 AdminApp 设置快照、租户配置持久化和文档解析构建入口。
* 本阶段未改数据库 schema，chunker 来源先记录在 `source_offsets["chunker"]`。
