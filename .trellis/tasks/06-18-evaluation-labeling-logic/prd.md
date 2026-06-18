# 评测工作台标注逻辑优化

## Goal

解决评测工作台里“期望 source/chunk 需要手填内部 ID，但用户不知道从哪里获得、如何确认”的平台逻辑断点，让用户能从可理解的候选来源、FAQ、文档切片中标注期望命中，并能回到对应资料验证。

## What I already know

* 用户指出：评测召回设置里有“目标块/期望 chunk ids”一类字段，当前需要填写编号，但不知道哪一块属于哪个编号。
* 当前评测用例抽屉 `web/src/pages/evaluation/case-drawer.tsx` 直接暴露：
  * `expected_source_ids`
  * `expected_chunk_ids`
* 当前运行结果表 `web/src/pages/evaluation/result-panel.tsx` 展示：
  * `source_id`
  * `chunk_id`（实际来自 `RetrievalEvalItem.id`）
* 当前文档切片浏览器 `web/src/pages/documents/chunk-browser.tsx` 展示的是 `#1/#2` 这类相对切片编号，不等同于知识库检索候选里的 chunk id。
* 后端 `retrieval_eval_item_payload()` 只返回候选的 `id/source_id/source_type/channels/score`，缺少标题、摘要、页码、文档文件名、FAQ 问题等用户可理解字段。
* 当前评测命中判断是：若填写 `expected_chunk_ids`，只按候选 `item.id` 匹配；否则按 `source_id` 匹配。
* 这类问题属于平台产品逻辑，不只是文案问题：标注入口、候选结果、知识库对象详情之间缺少闭环。

## Assumptions

* 第一版应优先解决内部验收使用，不做复杂标注工作流或批量标注任务。
* 用户不应被要求手写内部 ID；内部 ID 可以保留为高级信息，但不作为主要操作入口。
* 评测工作台可以复用候选结果来“设为期望命中”，先不强制做全库搜索选择器。
* 文档切片页仍应保留 `#1/#2` 便于浏览，但需要能显示/复制真实检索 chunk id 或提供跳转上下文。

## Open Questions

* 当前无阻塞问题。

## Requirements (evolving)

* 评测用例编辑不应只暴露裸 `expected_source_ids` / `expected_chunk_ids` 文本框。
* 运行结果候选表应展示用户可读信息，而不是只有内部 source/chunk id。
* 用户应能从候选结果中把某一条设为期望 source 或期望 chunk。
* 用户应能区分 source 级期望和 chunk 级期望的含义：
  * source 级：命中同一 FAQ 或同一文档即可。
  * chunk 级：必须命中特定知识 chunk。
* 用户应能复制或查看真实 ID，但这应是辅助能力。
* 对 FAQ/document 的候选来源，应尽可能展示问题、文档名、页码/章节、摘要等可追溯字段。
* 文档切片管理抽屉应让用户知道当前可见切片与评测 chunk id 的关系，或提供从评测候选跳回切片的路径。
* 同类平台逻辑问题需要一起梳理并修复，避免字段存在但用户不知道怎么用。
* 本轮 MVP 采用“运行后从候选中标注”的方案：
  * 新建/编辑用例阶段不强制填写期望 ID。
  * 用户运行单条评测后，在 TopK 候选里把某条候选标为期望 source 或期望 chunk。
  * 暂不做新建用例时的全库 FAQ/文档切片搜索选择器。
* 一键标注时同一用例只保留一种评测粒度：
  * 点击“设为期望来源”会切换到 source 级评测，并清空 chunk 级期望。
  * 点击“设为期望切片”会切换到 chunk 级评测，并清空 source 级期望。
  * 高级手填仍可输入内部 ID，但不是推荐路径。

## Acceptance Criteria (evolving)

* [ ] 用户无需手写内部 chunk id 就能为评测用例设置期望命中。
* [ ] 运行结果候选可一键标为期望 source 或期望 chunk。
* [ ] 候选结果展示足够信息，让用户知道命中的是哪条 FAQ 或哪份文档的哪段内容。
* [ ] 已标注的期望命中在用例详情/列表中用可读摘要展示，不只显示数量或 ID。
* [ ] 保留高级 ID 查看/复制能力，便于排查。
* [ ] 后端和前端测试覆盖新增标注行为，或明确手工验证路径。

## Definition of Done

* Tests added or updated for backend behavior that changes.
* Frontend lint/build passes.
* Backend ruff/pytest/check-config remain green, or unrelated failures are documented.
* `docs/changes/20260618-114636-evaluation-labeling-logic/` 更新计划、确认和验证记录。
* 不改变检索核心排序算法，除非 PRD 后续明确纳入。

## Out of Scope

* 批量评测集导入。
* LLM 自动判断答案质量。
* agentic planner/tool loop 评测。
* 知识图谱抽取或图谱可视化。
* 权限、审计、外部 API。

## Technical Notes

* Frontend:
  * `web/src/pages/EvaluationPage.tsx`
  * `web/src/pages/evaluation/case-drawer.tsx`
  * `web/src/pages/evaluation/result-panel.tsx`
  * `web/src/pages/evaluation/helpers.ts`
  * `web/src/pages/documents/chunk-browser.tsx`
* API/schema:
  * `web/src/api/schemas.ts`
  * `web/src/api/hooks.ts`
* Backend:
  * `customer_service_agent/admin_server.py`
  * `customer_service_agent/db/retrieval_meta.py`
* Tests:
  * `tests/test_admin_server.py`
  * frontend lint/build

## Initial Finding

当前最明显的断点是：评测用例创建时要求用户事先知道期望 ID；但这些 ID 只有在运行结果表中以内部字段出现，文档管理抽屉则使用另一套 `#N` 浏览编号。更稳的产品路径是先让用户运行问题，看 TopK 候选，再从候选中点击“设为期望命中”；新建用例阶段只填问题、意图、标签即可。

## Decision

用户已确认本轮先做“运行后从候选中标注期望命中”。这条路径最短，也能用真实召回结果反推资料/切块/别名是否正确；新建时搜索全库目标作为后续增强。

为避免后端“chunk ids 优先于 source ids”的指标规则让用户误读，本轮一键标注会显式切换评测粒度：source 级和 chunk 级不在同一次点击里混用。
