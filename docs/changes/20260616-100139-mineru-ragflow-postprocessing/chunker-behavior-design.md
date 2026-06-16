# RAGFlow Chunker 对齐设计

## 目标

第二阶段不做“轻量分流”。目标是把本项目的文档后解析/chunker 行为向 RAGFlow `naive/manual/qa/table` 靠齐，同时保留本项目轻部署、导入审核、切片抽屉、来源证据和 parent-child 检索语义。

## 总体设计

采用项目自有的后解析层，不引入 RAGFlow 服务或存储依赖：

1. MinerU 继续作为默认解析 provider，优先 API 接入。
2. MinerU/Markdown/Excel 等解析结果统一进入项目后处理层。
3. 后处理层显式选择 chunker：`naive`、`manual`、`qa`、`table`。
4. 每个 chunker 输出仍映射为现有 `import_chunks` 字段，除非后续确认 schema/UI 改动。
5. 所有结果先进入导入审核，不能直接进入正式 FAQ 或可检索知识。
6. 检索继续保持 child 召回、parent 回填，parent 不作为同权直接候选。

## Chunker 选择策略

推荐采用“显式配置优先 + 文件类型默认 + 辅助推荐”的模式：

* 显式配置优先：导入任务或后端参数可指定 `chunker_type`。
* 文件类型默认：
  * xlsx/csv/txt 表格导入意图：`table`
  * xlsx/csv/txt 问答导入意图：`qa`
  * PDF/Word 使用手册、SOP、政策、说明书：`manual`
  * 普通文档或无法判断：`naive`
* 辅助推荐只负责给默认值，不隐藏实际采用的 `chunker_type`。

这样既避免“轻量猜测”，也不强迫本地部署 RAGFlow 的完整任务系统。

## 输出字段映射

继续复用现有 `import_chunks`：

* `source_text`：用户审核正文。
* `source_blocks`：结构化来源块，保存原始 block 级证据。
* `page_start/page_end`：切片抽屉页码展示来源。
* `section_path`：manual/qa 标题栈或 RAGFlow section path。
* `block_type`：`text`、`table`、`table_row`、`qa`、`image`、`mixed` 等。
* `source_offsets`：页码、bbox、position tag、Excel 行号、sheet、headers、table_html、asset paths 等证据。
* `children_delimiter`：沿用 RAGFlow children split 语义。

建议后续新增或复用 metadata 记录：

* `chunker_type`
* `chunker_reason`
* `parser_provider = mineru`

如果不改 schema，可先放入 `source_offsets["chunker"]`；但长期更适合在 import file/chunk 元数据中显式展示。

## QA 行为

对齐 RAGFlow `rag/app/qa.py`：

* Excel：每行前两个非空单元格分别作为 question/answer。
* TXT/CSV：两列为一组；坏行在已有 question 后追加到 answer，未出现 question 前记录为 skipped。
* Markdown：标题栈作为 question path，标题下正文作为 answer，代码块内不识别标题。
* Word/PDF：标题或问题编号形成 question，后续正文/图片/表格作为 answer。

本项目适配：

* 每个 Q/A pair 生成一个 import chunk。
* `source_text` 使用 `问题：...\n回答：...`。
* question/answer 原文、行号、页码、标题栈进入 `source_offsets`。
* Q/A 结果可进入候选 FAQ，但仍需要人工审核确认。

## Table 行为

对齐 RAGFlow `rag/app/table.py`：

* 每个数据行是一个 chunk。
* 第一行或多级表头提供字段名。
* 合并单元格继承父值。
* 空行跳过，坏行记录。
* 重复表头报错，不静默覆盖。

本项目适配：

* 每行 `source_text` 格式为多行 `- 字段: 值`。
* `source_offsets` 保存 `sheet_name`、`row_index`、`header_rows`、`headers`、`field_map`。
* Excel 图片描述先作为后续能力，除非确认引入视觉模型。
* 不复制 RAGFlow ES/Infinity typed field 存储模型。

## Manual 行为

对齐 RAGFlow `rag/app/manual.py`：

* PDF 优先使用 outline；outline 不足时用 bullet/title frequency 判断章节。
* 同章节或小片段合并为 parent chunk。
* 表格/图片可带前后文本上下文。
* Word 表格保留 HTML，并尝试附带最近标题层级。

本项目适配：

* 对手册、SOP、政策类材料优先采用 `manual`。
* parent chunk 按标题/章节聚合，child 从 block 或 children_delimiter 产生。
* 页码、bbox、table_html、asset paths 必须留在 `source_blocks/source_offsets`。
* PDF outline 是否单独展示，需要后续 UI/schema 确认；不要塞进正文。

## Naive 行为

现有代码已覆盖主要 RAGFlow naive 语义：

* block/section 合并到 token 阈值。
* 自定义反引号 delimiter。
* children_delimiter 拆 child。
* position tag 从正文移除，但作为证据保留。
* 表格/图片可附带上下文。

第二阶段对 naive 只做回归保护和小修，不推翻已有路径。

## Parent-Child 检索

沿用第一阶段结果：

* parent 行可保留 embedding 和 UI 状态。
* 普通向量/关键词直接检索排除 document parent。
* child 命中后回填 parent 作为上下文。
* 后续可评估是否停用 parent embedding，但这不是第二阶段前置条件。

## 暂缓项

* 引入 RAGFlow 服务、任务执行器、租户模型、ES/Infinity/OceanBase、RAPTOR、GraphRAG。
* 本地部署 MinerU 作为强依赖。
* VLM 图片描述和 Excel 图片语义补全。
* PDF outline 的 UI 展示和 schema 持久化。

## 建议第二阶段 MVP

1. 增加 chunker 类型模型和记录位置，但尽量不改数据库 schema；如果必须改 schema，先单独确认。
2. TDD 实现 `table` row chunking，覆盖 xlsx/csv/txt、表头、坏行、证据保留。
3. TDD 实现 `qa` chunking，覆盖 xlsx/csv/txt malformed、Markdown 标题栈。
4. TDD 实现 `manual` 的 ParsedBlock 标题层级聚合，先覆盖 MinerU 已有 `section_title/layout_type/page/bbox`。
5. 回归现有 `naive`、page chrome 过滤、parent-child 检索测试。

## 需要确认

我建议第二阶段先按上述 MVP 开始，其中 `chunker_type` 的展示/存储先放在 `source_offsets["chunker"]`，避免先做 schema/UI 大改。等 table/qa/manual 行为稳定后，再决定是否加正式字段和 UI 筛选。
