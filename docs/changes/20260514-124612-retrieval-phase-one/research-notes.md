# RAGFlow / LightRAG 检索召回调研结论

调研时间：2026-05-14

## 调研对象

- RAGFlow：重点看文档解析、切块模板、检索测试、混合检索、知识图谱和父子 chunk。
- LightRAG：重点看实体关系图谱、向量与图结合的查询模式，以及轻量 GraphRAG 的适用边界。
- GraphRAG / Contextual Retrieval / Parent-child Retriever：作为召回架构参考，不作为第一阶段直接照搬对象。

参考资料：

- RAGFlow GitHub：https://github.com/infiniflow/ragflow
- RAGFlow 检索测试文档：https://ragflow.com.cn/docs/dev/run_retrieval_test
- RAGFlow 知识图谱文档：https://ragflow.com.cn/docs/dev/construct_knowledge_graph
- RAGFlow 父子分块文档：https://ragflow.com.cn/docs/dev/configure_child_chunking_strategy
- LightRAG GitHub：https://github.com/HKUDS/LightRAG
- LightRAG 论文页：https://arxiv.org/abs/2410.05779
- Anthropic Contextual Retrieval：https://www.anthropic.com/news/contextual-retrieval
- Microsoft GraphRAG 默认数据流：https://microsoft.github.io/graphrag/index/default_dataflow/

## 总体判断

本项目当前已经不是从零开始的 RAG demo。它已经具备 FAQ 管理、文档导入、MinerU 解析、人工审核、文档切片 embedding、统一 `knowledge_chunks` 表、智能问答调试抽屉等基础能力。真正差距在“企业级可运营检索系统”的闭环上，而不是缺某一个高级算法。

对照 RAGFlow 和 LightRAG，当前最需要补齐的是：

1. 检索质量可评测：有固定问题集、期望命中、指标、结果回放和版本对比。
2. 召回链路多通道：不只依赖向量相似度，还要有关键词、精确词、意图路由、重排和后续图谱扩展。
3. 知识结构可追溯：chunk 需要更细粒度来源、父子层级、章节路径、页码和证据。
4. 生产治理：权限、审计、任务队列、失败重试、索引版本、备份和敏感信息策略。

因此第一阶段应该先做“检索评测 + 意图识别 + 混合召回 + 调试可视化”，而不是直接做完整知识图谱。

## RAGFlow 值得借鉴的地方

RAGFlow 的强项是产品化完整链路。它不是单纯把文档切成块丢进向量库，而是把知识库建设拆成多个可独立运行、可观察、可重试的阶段：

- 文档上传和解析。
- 按文档类型选择解析和切块策略。
- 生成普通向量索引。
- 支持关键词、向量、重排的检索测试。
- 可选知识图谱任务，从已有 chunk 抽取实体、关系和社区摘要。
- 在问答应用前先做 retrieval test，确认命中质量。

对本项目的启发：

- 检索测试应该成为正式功能，而不是开发者临时脚本。
- 文档解析结果要继续保留页码、章节、block 类型、表格行等证据。
- KG 不应该替代普通 RAG，而是作为额外召回上下文。
- 检索链路应该能解释：为什么命中、来自哪个通道、分数是多少、是否经过重排。

## RAGFlow 不适合直接照搬的地方

RAGFlow 是平台型系统，依赖更重，面向多知识库、多应用、多租户和复杂文档处理。本项目当前定位是本地客服知识库与 RAG 服务，不建议第一阶段引入完整 RAGFlow 架构。

不建议照搬：

- MinIO、Redis、ES / Infinity 等完整平台依赖。
- 全量知识图谱、社区报告和复杂实体消解。
- 重型工作流编排。
- 复杂多租户应用市场式能力。

更适合的路线是把 RAGFlow 的能力拆小，先做本项目真正缺的检索闭环。

## LightRAG 值得借鉴的地方

LightRAG 的核心启发是：图谱可以作为检索索引的一部分，而不是只做可视化。它把文本 chunk、实体、关系结合起来，支持不同层级的查询模式：

- 局部查询：围绕具体实体和关联关系找答案。
- 全局查询：跨文档、跨社区归纳答案。
- 混合查询：结合实体关系和向量文本。

对客服知识库来说，LightRAG 的价值主要在这些场景：

- 用户问题涉及多个概念之间的关系，例如“某功能在哪些角色下不能用”。
- 问题不是标准 FAQ 问法，需要通过产品名、错误码、流程节点扩展召回。
- 多篇 SOP、手册、注意事项之间存在条件关系。

但 LightRAG 偏算法和框架，不解决本项目必须有的审核、权限、导入、证据、运营和本地管理流程。因此它适合作为第二阶段轻量 KG 设计参考，不适合第一阶段直接整体迁移。

## 父子 chunk 的判断

父子 chunk 是本项目第二优先级最高的召回增强能力，仅次于评测和混合召回。

当前文档切块默认按较大字符数合并，适合给模型上下文，但不适合精准召回。父子 chunk 的价值是：

- child chunk：短文本，负责精准 embedding 和关键词召回。
- parent chunk：较长上下文，负责给 LLM 足够背景。
- sibling chunk：命中后补相邻上下文，避免答案断裂。

建议后续结构：

- `parent_chunk_id`：父块 id。
- `chunk_level`：`parent` / `child`。
- `section_path`：章节路径。
- `page_start` / `page_end`：页码范围。
- `block_type`：段落、标题、表格、列表、图片说明等。
- `source_offsets`：可选，用于定位原文范围。

第一阶段暂不改切块结构，但混合召回模块要预留“命中 child 后回填 parent”的接口位置。

## Contextual Retrieval 的判断

Contextual Retrieval 的核心思想是：不要只把孤立 chunk 做 embedding，而是在 embedding 文本里补充文档级和章节级上下文。对中文客服知识库尤其有用，因为很多 chunk 单独看会缺主语，例如“点击右上角导出”不知道是哪个页面。

本项目已经有 `embedding_text` 和 `search_text` 字段，适合做上下文增强：

- FAQ embedding_text：标准问题、相似问法、答案、分类、标签。
- 文档 embedding_text：文件名、章节路径、页码、标题、正文、自动关键词、自动问题。
- search_text：保留更多别名、错误码、产品名、菜单名、按钮名。

第一阶段可以先不重算所有 embedding，但设计上应保证后续可以重建 embedding_text 并标记 stale。

## GraphRAG / 知识图谱的判断

知识图谱值得做，但不是第一阶段。

客服知识库第一版 KG 应该控制在“召回增强”范围，不追求通用复杂推理。推荐实体类型：

- 产品 / 平台 / 模块。
- 功能 / 页面 / 按钮 / 菜单。
- 错误码 / 异常现象。
- 流程 / 任务 / 报告 / 订单。
- 角色 / 权限 / 渠道。
- 限制条件 / 适用条件 / 转人工条件。

推荐关系类型：

- `belongs_to`：功能属于模块。
- `requires`：操作需要前置条件。
- `causes`：现象可能由原因导致。
- `resolves_by`：问题可通过步骤解决。
- `blocked_by`：功能受某条件阻塞。
- `available_for`：适用于某角色或渠道。
- `escalate_when`：满足条件需转人工。

第一版 KG 仍应走人工审核，不应让模型抽取结果直接进入可检索状态。查询时只做实体识别和关联 chunk 扩展，不做复杂社区报告。

## 当前项目差距清单

### 检索召回

- 当前主要是向量检索，`knowledge_chunks` 的全文索引还没有形成真正的混合召回链路。
- 没有 query analysis / intent detection，实时状态问题、闲聊、敏感问题和标准 FAQ 都走同一条 RAG。
- 没有候选融合策略，例如 RRF、加权融合或 rerank。
- 没有检索评测数据和指标，无法判断一次检索改动是提升还是退化。
- 没有失败样本沉淀，命中差的问题无法稳定复现。
- 文档切块更偏上下文，不够适合精准召回。

### 知识治理

- 文档切片生成 embedding 后可以进入 `usable`，但企业正式使用时应更严格地区分“已解析”“已审核”“可检索”。
- 缺少知识版本、发布记录和回滚机制。
- 缺少低质量知识、重复知识、冲突知识的治理看板。
- 缺少敏感信息识别和脱敏审核。

### 企业生产能力

- 管理后台当前仍是本地内部工具，缺登录鉴权、RBAC、审计日志和上传限制。
- 缺后台任务队列，长任务主要依赖同步调用或简单轮询。
- 缺监控告警，例如 embedding 失败率、解析失败率、检索空召回率、平均延迟。
- 缺备份恢复和索引重建策略。

## 第一阶段建议范围

第一阶段只做后端和最小接口，不做完整 UI。

目标：

1. 新增意图识别层。
2. 新增混合召回模块。
3. 新增检索评测数据结构和基础指标。
4. 改造智能问答事件流，让调试抽屉能看到 query analysis、hybrid retrieval、source context。
5. 继续保持现有 FAQ、文档、embedding 流程不被大幅打断。

意图识别第一版采用“规则优先 + Chat 模型兜底”：

- 高确定性问题用规则识别，避免每次都调用模型。
- 规则无法判断时，允许 Chat 模型输出结构化 JSON。
- 模型输出只影响检索策略，不直接生成答案。
- 敏感问题和实时状态问题必须进入保守处理。

混合召回第一版：

- vector candidates：现有 `search_knowledge`。
- keyword candidates：新增基于 `search_text` / `content` / `source_title` 的关键词召回。
- fusion：先用 RRF 或简单加权融合。
- rerank：只预留插槽，不强依赖外部 reranker。

评测第一版：

- 支持手工录入真实客服问题。
- 支持记录期望命中 `knowledge_chunk_id` / `source_id`。
- 支持计算 Recall@K、MRR、top1 是否命中。
- 支持保存每次运行的候选列表和分数，方便回放。

## 第二阶段建议范围

第二阶段做父子 chunk 和上下文增强：

- parent / child chunk 数据结构。
- child embedding、parent 回填。
- 相邻 chunk 扩展。
- 文档 embedding_text 增加文件名、章节、页码、自动关键词和自动问题。
- 重新生成 embedding 时保留版本和 stale 状态。

## 第三阶段建议范围

第三阶段做轻量知识图谱：

- KG 实体、关系、证据表。
- AI 抽取候选实体关系。
- 人工审核后发布。
- 查询时识别实体并扩展关联 chunk。
- 先服务召回，不做复杂图谱可视化。

## 高级产品经理视角的结论

要达到公司正式使用级别，本项目要从“能问答”升级为“可运营的知识服务系统”。关键不是堆更多模型，而是让知识进入、审核、索引、召回、回答、反馈、评测形成闭环。

优先级应该是：

1. 检索评测和失败样本闭环。
2. 意图识别和混合召回。
3. 父子 chunk 与上下文增强。
4. 轻量 KG 扩召回。
5. 企业权限、审计、监控、备份和发布治理。

第一阶段做完后，项目应该能回答三个问题：

- 这次检索为什么命中了这些知识？
- 它比上一个版本更好吗？
- 哪些问题仍然召回失败，下一步该优化哪里？

如果这三个问题不能回答，直接上知识图谱也很难稳定提升实际客服效果。
