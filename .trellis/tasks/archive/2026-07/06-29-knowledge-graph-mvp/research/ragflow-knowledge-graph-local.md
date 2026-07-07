# 本地 RAGFlow 知识图谱实现调研

调研对象：`/home/adam/projects/ragflow`

调研时间：2026-06-29

## 结论摘要

RAGFlow 的 GraphRAG 是“生成图谱产物后写回文档检索存储”的模式，不依赖独立图数据库。它把全局图、文档子图、实体、关系、社区报告都作为特殊 chunk 存储，并在检索时通过 `use_kg` 开关额外生成一条“Related content in Knowledge Graph”上下文插入普通 RAG 结果前面。

这个方向适合我们借鉴，但不能直接照搬：RAGFlow 默认生成后就可进入 KG 检索链路，而本项目要求 AI 生成内容必须先人工审核。因此我们第一版应保留 RAGFlow 的“KG 产物可检索化”和“合成 KG 上下文”思路，但增加候选审核层和证据追溯状态。

## 产品入口

RAGFlow 的 KG 产品路径分成两条：

* 数据集侧：配置 GraphRAG 并触发生成 Knowledge graph。
* 检索/聊天侧：通过 `use_kg` 开关决定是否把 KG 检索上下文加入回答。

相关文件：

* `web/src/components/parse-configuration/graph-rag-form-fields.tsx`
  * 配置项包括 `entity_types`、`method`、`resolution`、`community`。
  * `method` 支持 `light` 和 `general`。
  * `GenerateLogButton` 触发 `KnowledgeGraph` 生成。
* `web/src/pages/dataset/testing/testing-form.tsx`
  * 测试检索表单有 `UseKnowledgeGraphFormField name="use_kg"`。
* `api/apps/services/dataset_api_service.py`
  * `run_index(..., index_type="graph")` 负责创建 GraphRAG 任务。
  * `get_knowledge_graph(...)` 返回图数据，并限制前端展示为 pagerank 前 256 个节点、weight 前 128 条边。

## 生成流程

核心入口：

* `rag/svr/task_executor.py`
  * `task_type == "graphrag"` 时读取知识库 `parser_config.graphrag`。
  * 未配置时自动写入默认配置：`use_graphrag=True`、默认实体类型、`method="light"`。
  * 使用 `kg_limiter` 限流后调用 `run_graphrag_for_kb(...)`。
* `rag/graphrag/general/index.py`
  * `run_graphrag_for_kb(...)` 是 KB 级批处理入口。
  * 先读取所有目标文档 chunk，把内容按约 4096 token 拼成抽取输入。
  * 对每个文档并发生成子图，默认并发上限 `max_parallel_docs=4`。
  * 若文档已有 `subgraph`，跳过 LLM 抽取。
  * 所有成功子图按 KB 合并成全局图。
  * 可选执行 entity resolution 和 community report。

关键实现点：

* `generate_subgraph(...)`
  * 使用 Light 或 General 抽取器从文本生成实体和关系。
  * 实体写入 networkx node，关系写入 edge。
  * 子图以 `knowledge_graph_kwd="subgraph"` 的 chunk 写回 doc store。
* `merge_subgraph(...)`
  * 读取已有全局图，合并当前子图。
  * 计算 pagerank。
  * 调用 `set_graph(...)` 写回图谱产物。
* `resolve_entities(...)`
  * 可选实体消歧/合并。
* `extract_community(...)`
  * 可选社区报告，写成 `knowledge_graph_kwd="community_report"` 的 chunk。

## 存储模型

RAGFlow 把 KG 产物放在同一个 doc store/index 体系里，通过 `knowledge_graph_kwd` 区分类型：

* `graph`：KB 级全局 networkx 图，JSON node-link 格式。
* `subgraph`：文档级子图，带 `source_id=[doc_id]`。
* `entity`：实体 chunk，带 `entity_kwd`、`entity_type_kwd`、实体描述 embedding。
* `relation`：关系 chunk，带 `from_entity_kwd`、`to_entity_kwd`、关系描述 embedding。
* `community_report`：社区摘要 chunk。

相关文件：

* `rag/graphrag/utils.py`
  * `graph_node_to_chunk(...)` 将实体转为可检索 chunk。
  * `graph_edge_to_chunk(...)` 将关系转为可检索 chunk。
  * `get_graph(...)` / `set_graph(...)` 读写全局图。
  * `rebuild_graph(...)` 可从 `subgraph` 重建全局图。
* `api/db/services/document_service.py`
  * 删除文档时会从图谱 chunk 的 `source_id` 中移除文档 ID。
  * 如果全局图受影响，会把 `graph` 标记为 `removed_kwd="Y"`，后续可重建。

注意：本地 RAGFlow 的实体 chunk 在 `graph_node_to_chunk(...)` 中主要保存 `important_kwd`、`entity_kwd`、`entity_type_kwd`、`content_with_weight`、`source_id`、embedding 等字段；检索代码会读取 `n_hop_ents`，但本次看到的实体 chunk 生成片段没有直接写入该字段，后续如需要 n-hop 应以本项目自己的表或查询逻辑为准。

## 检索接入

核心文件：`rag/graphrag/search.py`

`KGSearch.retrieval(...)` 流程：

1. 调用 LLM 做 query rewrite，提取实体类型和实体关键词。
2. 用实体关键词向量检索 `knowledge_graph_kwd="entity"`。
3. 用实体类型过滤检索实体。
4. 用原始问题向量检索 `knowledge_graph_kwd="relation"`。
5. 合并实体、关系和可选社区报告。
6. 返回一条 synthetic chunk：
   * `docnm_kwd="Related content in Knowledge Graph"`
   * `content_with_weight` 包含 CSV 形式的 Entities、Relations、Community Report。
   * `similarity=1.0`，通常插入普通检索结果最前面。

接入位置：

* `api/db/services/dialog_service.py`
  * 普通 KB 检索完成后，如果 `prompt_config.use_kg` 为真，则调用 `settings.kg_retriever.retrieval(...)`。
  * KG chunk 有内容时插入 `kbinfos["chunks"]` 第 0 位。
* `api/apps/services/dataset_api_service.py`
  * 数据集测试检索请求中如果 `use_kg` 为真，也会插入 KG synthetic chunk。

## 可借鉴点

* 不上独立图数据库，沿用现有存储和检索基础设施。
* 图谱构建从已存在 chunk 开始，而不是重新解析原文件。
* KG 结果以实体、关系、全局图、子图分层保存，便于重建和删除来源。
* 检索时不要让 KG 替代普通 RAG，而是额外合成一条 KG 上下文。
* UI 不需要第一版就做复杂图可视化，RAGFlow 也只截取 top 节点/边展示。

## 不宜照搬点

* RAGFlow 没有本项目要求的“AI 候选 -> 人工审核 -> 可检索”闸门。
* RAGFlow 的 KG 产物写入 doc store 后更接近系统内部索引，不适合直接暴露为人工知识治理对象。
* RAGFlow 的默认实体类型偏通用：organization/person/geo/event/category，不适合客服知识库。
* 社区报告、实体消歧和多跳扩展会显著增加实现面，第一版不应全部做。
* 直接把 KG synthetic chunk 插到最前面会影响回答引用，需要我们保留原始 FAQ/文档证据作为最终依据。

## 映射到本项目的建议

本项目已有 `knowledge_chunks`、导入候选审核、混合检索和评测工作台。推荐第一版采用“审核表为主，确认后投影到可检索 chunk”的折中方案：

* 用独立表保存候选实体、候选关系和证据，状态包含 `needs_review`、`usable`、`disabled`。
* 候选来源必须指向 `faq_documents` 或 `knowledge_chunks` / `import_chunks`，保留文件名、页码、章节等元数据。
* 人工确认后，再把实体/关系投影为 `knowledge_chunks` 的特殊来源类型，例如 `kg_entity`、`kg_relation`。
* 检索增强第一步可以模仿 RAGFlow：生成一条 KG 合成上下文，但只使用 `usable` KG 产物，并在内容里附带证据 ID。
* 暂不做 community report 和复杂全局图可视化。

## 推荐 MVP

第一版建议目标：

1. 从已审核 FAQ / 可用文档 chunk 抽取实体和关系候选。
2. 候选必须人工审核，确认后才进入 KG 可用状态。
3. 确认后的实体/关系可投影为特殊 `knowledge_chunks`，便于后续向量/关键词检索复用。
4. 检索增强可以先做开关和 synthetic KG context，但默认只作为调试/评测入口，不立即改所有客服回答路径。

