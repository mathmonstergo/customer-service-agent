# 用户确认记录

## 已有确认

* 用户确认新的任务目标是：向 RAGFlow 对 MinerU 的后解析和各种文档类型处理靠齐，并根据本项目已有功能进行平衡。
* 用户强调需要宏观考虑，MinerU/RAGFlow 是大团队项目，有些设计有其合理性；必要时本项目应做出让步并与其同步。
* 用户指出 page chrome/页码过滤不能简单丢弃来源信息，否则会影响文档管理切片抽屉展示页码。
* 用户确认第一阶段先做方案 2：MinerU 输出清洗/证据保留 + parent-child 检索口径调整；完整多 chunker 分流后续再做。
* 用户确认 parent 行策略采用方案 1：继续生成 parent embedding，但检索默认排除 parent，parent 只通过 child 命中后回填上下文。

## 待确认

* 第一阶段无阻塞确认项。
* 完整多 chunker 分流、VLM 图片描述、本地 MinerU provider 和是否停用 parent embedding，后续单独确认。

## 2026-06-16 第一阶段实现后记录

* 已按用户确认先做方案 2：MinerU 输出清洗/证据保留 + parent-child 检索口径调整。
* 已按用户确认先做方案 1：parent 行继续生成 embedding，但文档 parent 不参与普通向量/关键词直接检索。
* 已保留正文块页码、bbox/position tag 和表格 HTML 证据；过滤只作用于 page chrome/未知块进入正文候选的路径。
* 已验证全量测试、Ruff 和配置检查通过。
