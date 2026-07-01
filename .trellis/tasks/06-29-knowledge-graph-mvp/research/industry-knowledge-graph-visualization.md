# 主流知识图谱 / GraphRAG / 可视化实践调研

调研时间：2026-06-29

## 结论摘要

主流做法不是先做炫目的图谱界面，而是先把知识图谱底座做稳：来源切片、实体/关系抽取、schema/ontology、实体归一、证据追溯、质量审核、检索接入和评测。3D 或图形化探索通常是消费层，用来浏览、演示、排查和分析；它依赖一个可信、可过滤、可分页、可聚合的图谱 API。

对本项目来说，3D 可视化可以作为目标形态，但不应该进入第一版核心闭环。第一版应先产出可审核、可追溯、可检索的实体/关系；同时在数据模型和 API 上预留图谱查询接口，后续再扩展 2D/3D 图谱视图。

## 公开资料观察

### Microsoft GraphRAG

官方 GraphRAG 文档把流程分为 Index 和 Query：

* Index 阶段先把语料切成 TextUnits，作为后续分析和细粒度引用单元。
* 从 TextUnits 抽取 entities、relationships 和 key claims。
* 对图做层次化社区聚类，并生成 community summaries。
* Query 阶段支持 Global Search、Local Search、DRIFT Search 和 Basic Search。

这说明 Microsoft 的重点是“结构化索引 + 查询增强 + 社区摘要”，可视化只是理解图结构的辅助，不是第一层产品能力。

参考：

* `https://microsoft.github.io/graphrag/`

### Google Knowledge Graph / RAG Engine

Google 公开的 Knowledge Graph Search API 面向“查找 Google Knowledge Graph 中的实体”，强调实体识别、实体信息和 API 查询，而不是图形界面。

Google Cloud 的 Gemini Enterprise Agent Platform RAG Engine 定位为“构建上下文增强 LLM 应用的数据框架”，公开产品重点是 corpus/import/retrieval 等数据与检索能力。

参考：

* `https://developers.google.com/knowledge-graph`
* `https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/rag-engine/rag-overview`

### 云厂商图数据库 + GenAI 常见模式

AWS Neptune、Neo4j 等图数据库/图平台的 GenAI 方案通常是：

* 图数据库或图索引保存实体、关系和属性。
* 向量检索保存文本语义召回。
* LLM 在查询阶段结合图关系和文本证据生成答案。
* 图浏览器、notebook、Bloom/Explorer/GraphXR 等工具作为分析和排查界面。

这类系统把“图谱存储/查询/权限/质量”作为底座，把图形化界面作为上层工具。3D 图谱更多用于探索、演示和复杂拓扑观察；业务审核、客服排查、证据确认通常仍需要表格、筛选、详情页和来源引用。

## 3D 图谱的真实价值和风险

### 适合做 3D 的场景

* 展示全局结构、实体簇、模块间关系，帮助用户形成直觉。
* 在节点数量受控时做探索式浏览，例如 50-300 个节点的局部子图。
* 演示知识库覆盖度和关系密度，增强产品感知。
* 做客服排查时，从一个实体向外展开 1-2 跳，查看相关问题、错误、步骤和限制。

### 不适合第一版直接做 3D 的原因

* 没有可信实体/关系时，3D 只是把错误放大展示。
* 图谱节点一多会遮挡、重叠、漂移，审核效率不如列表和详情页。
* 3D 需要额外前端渲染栈，例如 Three.js、3d-force-graph 或自研 WebGL/canvas 层；当前 `web/package.json` 没有相关依赖。
* 3D 需要专门的 API：按中心节点扩展、按类型筛选、按状态过滤、限制节点数、返回布局权重和证据摘要。
* 本项目管理后台定位是工具型，知识生产流程必须先保证状态、审核、证据和可回滚。

## 推荐路线

### Phase 1: KG 底座 MVP

目标是做出可信图谱数据，而不是先做视觉效果。

* 建立实体、关系、证据、审核状态模型。
* AI 抽取结果进入候选状态。
* 人工审核后进入 `usable`。
* 确认结果可投影成可检索 KG chunk。
* 检索增强只读取已确认 KG。
* 提供最小图谱 API：按实体查询 1-hop 关系、按状态/类型过滤、返回证据摘要。

### Phase 2: 图谱治理 UI

目标是让用户高效修图谱。

* 审核列表、实体详情、关系详情、证据对照。
* 局部关系视图可以先做 2D 或轻量 canvas/SVG。
* 支持合并实体、禁用关系、查看来源和跳转 FAQ/文档切片。

### Phase 3: 3D 可视化图谱

目标是让图谱可探索、可演示，但不替代审核流程。

* 使用 Three.js 或 `3d-force-graph` 做局部子图。
* 默认从选中实体展开 1-2 跳，而不是一次渲染全库。
* 节点按实体类型配色，边按关系类型/置信度编码。
* 右侧保留详情面板和证据列表，避免只看图不看事实。
* 设置节点上限、边上限、搜索、过滤、重置视角、聚焦路径。

## 对本项目的建议

可以把“3D 可视化图谱”作为明确产品方向写进路线图，但第一版仍应选择“独立审核表 + 确认后投影为 KG chunk”。关键是第一版就把后续可视化需要的数据结构留好：

* 实体有稳定 ID、类型、别名、描述、状态、置信度、来源统计。
* 关系有稳定 ID、头尾实体、关系类型、描述、状态、置信度、证据集合。
* 证据能回到 FAQ/文档切片。
* API 支持局部子图查询，而不是只返回全量图。
* 可检索 KG chunk 和可视化图谱共用同一套已审核实体/关系，不做两套事实来源。

