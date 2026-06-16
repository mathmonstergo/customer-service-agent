# 用户确认记录

## 已有确认

* 用户确认新的任务目标是：向 RAGFlow 对 MinerU 的后解析和各种文档类型处理靠齐，并根据本项目已有功能进行平衡。
* 用户强调需要宏观考虑，MinerU/RAGFlow 是大团队项目，有些设计有其合理性；必要时本项目应做出让步并与其同步。
* 用户指出 page chrome/页码过滤不能简单丢弃来源信息，否则会影响文档管理切片抽屉展示页码。
* 用户确认第一阶段先做方案 2：MinerU 输出清洗/证据保留 + parent-child 检索口径调整；完整多 chunker 分流后续再做。
* 用户确认 parent 行策略采用方案 1：继续生成 parent embedding，但检索默认排除 parent，parent 只通过 child 命中后回填上下文。

## 待确认

* 第二阶段无阻塞确认项。
* VLM 图片描述、本地 MinerU provider 和是否停用 parent embedding，后续单独确认。

## 2026-06-16 第一阶段实现后记录

* 已按用户确认先做方案 2：MinerU 输出清洗/证据保留 + parent-child 检索口径调整。
* 已按用户确认先做方案 1：parent 行继续生成 embedding，但文档 parent 不参与普通向量/关键词直接检索。
* 已保留正文块页码、bbox/position tag 和表格 HTML 证据；过滤只作用于 page chrome/未知块进入正文候选的路径。
* 已验证全量测试、Ruff 和配置检查通过。

## 2026-06-16 第二阶段开始前确认

* 用户确认第二阶段可以继续做多 chunker 分流。
* 用户强调本项目主打轻量化，不做本地重量级部署项目。
* 用户确认当前默认只接入 MinerU 一个解析 provider，看好 MinerU 前景。
* 用户明确实现时必须参考 RAGFlow，不要自行重复造轮子。

记录结论：

* 第二阶段以 RAGFlow 的 `naive/manual/qa/table` chunk 思路为参考源。
* 本项目只移植轻量规则和数据组织方式，不引入 RAGFlow 任务执行器、租户 provider、ES/Infinity/OceanBase、RAPTOR/GraphRAG 或本地服务编排。

## 2026-06-16 第二阶段实现后记录

* 已实现 `qa`、`table`、`title_manual`、`naive` 轻量分流。
* 分流实现参考 RAGFlow 对应 chunker 的行为：QA 成对、表格按行、手册标题并入正文、naive 兜底。
* 未新增解析 provider；MinerU 仍是默认且唯一文档解析 provider。
* 未引入本地重量级部署组件，未改数据库 schema。
* 已验证全量测试、Ruff 和配置检查通过。
