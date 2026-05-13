# RAGFlow、MinerU 与知识图谱参考笔记

记录时间：2026-05-12

## 背景

本项目当前是本地客服知识库与 RAG 服务，已有流程是：

上传资料 -> 解析切块 -> AI 生成候选 FAQ -> 人工审核 -> 保存正式 FAQ -> 独立生成 embedding -> RAG 检索回答。

后续希望学习 RAGFlow 的文档识别、切块和知识图谱思路，但不引入 RAGFlow 全套重型架构。当前倾向是使用 MinerU 作为 PDF、Word 等文档解析能力的主要来源。

## RAGFlow 的关键结论

RAGFlow 的整体流水线可以概括为：

文档上传 -> 文档解析和切块 -> embedding 入文档引擎 -> 另起 GraphRAG 任务读取已切好的 chunk -> 抽取实体和关系 -> 将图谱内容也存为可检索 chunk。

它的重点不是单个切块算法，而是把“文档解析”“普通 RAG 索引”“知识图谱索引”拆成可独立运行的阶段。

### 文档解析和切块

RAGFlow 的普通解析入口会根据 `parser_id` 选择不同 chunker：

- `naive`：通用文档切块，支持 PDF、docx、xlsx/csv、txt、Markdown、HTML、EPUB、JSON 等。
- `qa`：把问答表中的每个问答对作为一个 chunk。
- `table`：把表格每一行作为一个 chunk，并尝试识别字段类型。
- `paper`、`book`、`manual`、`laws` 等：面向特定文档类型的切块策略。

PDF 解析会先走文档识别器，RAGFlow 可选 DeepDOC、MinerU、Docling、PaddleOCR、PlainText 等解析方式，再把解析出的段落、表格、图片描述合并成 chunk。

值得借鉴的是：切块前尽量保留结构信息，例如标题、页码、表格、图片说明、章节关系；切块后每个 chunk 都要带来源证据。

### 知识图谱

RAGFlow 的知识图谱不是替代 RAG，而是作为额外的检索上下文。

它从已切好的 chunk 中抽取：

- entity：实体，例如组织、人、地点、事件、类别等。
- relation：实体之间的关系。
- graph：全局图。
- subgraph：单个文档对应的子图。
- community_report：社区报告，用于多跳和复杂问题。

这些图谱对象最终仍然被写成文档引擎中的 chunk，通过 `knowledge_graph_kwd` 区分类型。实体和关系也会生成 embedding，查询时再按实体、关系、社区报告检索。

检索时，如果开启 `use_kg`，RAGFlow 会先做普通向量/全文检索，再额外做知识图谱检索，并把图谱检索结果插入上下文。

## 对本项目的轻量化借鉴

本项目不建议直接照搬 RAGFlow 的 MinIO、Redis、ES/Infinity、复杂 OCR、社区报告和实体消解。

更适合的轻量路线是：

1. 保持现有导入审核流程不变。
2. 用 MinerU 做文档解析，先把 PDF、Word 等资料转成带结构的 Markdown/JSON。
3. 在 `import_chunks` 中保存结构化来源信息，例如文件名、页码、章节、表格行、图片说明。
4. 继续让 AI 基于 chunk 生成候选 FAQ，候选内容默认 `needs_review`。
5. 后续新增轻量知识图谱表，例如 `kg_entities`、`kg_relations`、`kg_evidence`、`faq_entity_links`。
6. 图谱抽取结果也走人工审核，不直接进入正式可检索状态。
7. RAG 检索时先向量召回 FAQ，再用 FAQ 关联实体扩展相关 FAQ 和关系上下文。

第一阶段目标应该是“提升文档解析质量和证据可追溯”，不是立即做完整 GraphRAG。

## MinerU 作为文档解析的建议边界

MinerU 在本项目中的定位建议是独立解析适配层，而不是侵入 RAG 或数据库逻辑。

建议新增一个解析模块，职责类似：

上传文件原件 -> 调用 MinerU -> 产出统一的结构化解析结果 -> 转成本项目现有 `import_chunks`。

统一解析结果至少应包含：

- `source_file`：原文件名。
- `page_number`：页码，无法提供时为空。
- `section_title`：章节标题或最近标题。
- `block_type`：段落、标题、表格、图片、列表等。
- `text`：可供模型理解和生成 FAQ 的正文。
- `evidence`：可回溯证据，例如页码、表格行号、章节路径。

表格资料不要只转纯文本，应该尽量保留表头和行号；平台手册、SOP、注意事项类资料优先保留标题层级。

## 后续实现顺序建议

1. 先做 MinerU 解析适配层，支持 PDF 转结构化 chunk。
2. 把 MinerU 输出接入现有导入审核中心，让用户先看 chunk 和候选 FAQ。
3. 补充 Word、xlsx 的解析策略，统一输出结构。
4. 再做 FAQ 关联实体的轻量知识图谱。
5. 最后再考虑图谱可视化、实体合并、社区报告、多跳检索。

## 关键约束

- 用户上传原件、真实客户资料、聊天记录、生产提示词和密钥不能提交到 Git。
- AI 解析、FAQ 生成、图谱抽取都只能作为候选结果，必须人工审核后进入正式知识库。
- 保存 FAQ 和生成 embedding 继续保持独立步骤。
- 知识图谱第一版应服务客服问答召回，不追求通用复杂推理。
