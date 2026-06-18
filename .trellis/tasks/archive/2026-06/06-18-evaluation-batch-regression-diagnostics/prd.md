# 评测工作台批量回归与失败诊断

## Goal

把效果验收从“单条用例临时查看”推进到“可重复的批量回归闭环”，让后续 MinerU/RAGFlow 后处理、切块、parent-child、rerank 等检索改动能用同一组评测用例衡量效果变化，并能快速定位失败原因。

## What I already know

* 用户确认下一阶段推荐方向：评测工作台批量回归与失败诊断。
* 上一阶段已经完成“运行后从 TopK 候选标注期望来源/切片”，避免用户手填内部 ID。
* 当前页面 `web/src/pages/EvaluationPage.tsx` 只有单条运行按钮 `运行单条`。
* 当前后端只有单条运行接口：`POST /api/retrieval/eval-cases/{case_id}/run`。
* 当前列表统计只有：
  * 用例总数；
  * 平均命中率；
  * 待补期望数量。
* 当前运行结果只展示单条 case 的最近运行、指标、检索轨迹和候选来源。
* 当前数据库已有：
  * `retrieval_eval_cases`
  * `retrieval_eval_runs`
  * latest run 查询逻辑。
* 当前指标包括 `recall_at_k`、`mrr`、`hit_rate_at_1`，可以作为第一版批量汇总基础。
* 当前没有批次概念、基线概念、失败原因枚举，也没有批量运行的 API/hook/UI。

## Assumptions (temporary)

* 第一版优先服务本地内部验收，不做复杂多人协作、权限、定时任务或 CI 集成。
* 批量运行可以同步顺序执行，不引入后台队列；用例数量预期在几十到一两百条以内。
* 批量运行默认只跑 `active` 用例，避免把禁用或草稿用例混入回归结果。
* 第一版失败诊断先做规则化分类，不引入 LLM 自动判定。
* 基线对比可以先基于“上一批结果/当前 latest run”进行轻量对比，不急于新增复杂基线表。

## Open Questions

* 当前无阻塞问题。

## Requirements (evolving)

* 用户应能一键运行当前筛选范围内的评测用例，至少支持运行全部 active 用例。
* 批量运行过程中 UI 应明确展示：
  * 总数；
  * 已完成数量；
  * 当前运行中的问题；
  * 成功/失败数量；
  * 可中止或至少防止重复触发。
* 批量运行完成后应展示整体汇总：
  * case_count；
  * average recall@k；
  * average MRR；
  * Top1 hit rate；
  * 命中/未命中数量；
  * 待补期望数量。
* 失败诊断应把未命中用例分层，而不是只显示一个红色未命中：
  * 未标注期望：没有 expected source/chunk，无法评估；
  * 完全未召回：TopK 里没有期望 source/chunk；
  * 排序过低：命中了期望但不在 Top1；
  * 粒度不匹配：source 命中但 chunk 期望未命中，或 chunk 命中但用户期望粒度可能过细；
  * 无候选：检索结果为空；
  * 运行失败：接口或检索异常。
* 用户应能从失败列表点击进入对应 case，并查看该 case 的候选来源详情。
* 结果展示要偏工具型、信息密集但清晰，不做营销式大图或解释型首页。
* 后续对齐 MinerU/RAGFlow 后处理时，应能用同一评测集反复跑，判断是否改好或改坏。
* 本轮 MVP 明确不新增持久化 batch/baseline 表：
  * 批量运行由前端顺序调用现有单条 run API；
  * 汇总和失败诊断由前端基于当前列表与 latest run 计算；
  * 基线历史、批次详情页、跨版本趋势对比留到下一轮。

## Acceptance Criteria (evolving)

* [ ] 用户能从评测工作台批量运行 active 用例。
* [ ] 批量运行期间页面展示进度，并禁止重复启动同一批运行。
* [ ] 批量运行结果刷新每个 case 的 latest run。
* [ ] 页面展示批量汇总指标和失败分类统计。
* [ ] 页面提供失败用例列表，点击可定位到对应 case 和其最近运行结果。
* [ ] 未标注期望的 case 不应被当作检索失败，应单独计入“待补期望”。
* [ ] 后端或前端测试覆盖批量汇总/失败分类的核心规则。
* [ ] Python ruff/pytest/check-config、前端 lint/build 通过。

## Definition of Done

* 创建并更新 `docs/changes/20260618-132000-evaluation-batch-regression-diagnostics/`。
* PRD 中记录用户确认的 MVP 范围。
* 若新增 API/schema，更新 `.trellis/spec/` 的可执行合同。
* 后端行为有单元测试；前端类型和构建通过。
* 不改变核心检索排序算法；本任务只增加评测运行、汇总和诊断能力。

## Out of Scope (explicit)

* LLM 自动评价答案质量。
* 定时回归、CI 集成、邮件/微信通知。
* 多用户权限、审计日志。
* 大规模异步任务队列。
* 复杂实验管理平台。
* 修改 MinerU/RAGFlow 后处理逻辑本身。

## Technical Notes

* 现有单条运行：
  * `customer_service_agent/admin_server.py::AdminApp.run_retrieval_eval_case`
  * `POST /api/retrieval/eval-cases/{case_id}/run`
  * `web/src/api/hooks.ts::useRunRetrievalEvalCase`
  * `web/src/pages/EvaluationPage.tsx::handleRun`
* 现有结果展示：
  * `web/src/pages/evaluation/result-panel.tsx`
  * `web/src/pages/evaluation/case-list.tsx`
  * `web/src/pages/evaluation/helpers.ts`
* 现有数据合同：
  * `web/src/api/schemas.ts`
  * `.trellis/spec/backend/customer-service-agent-db-contracts.md`
* 现有测试：
  * `tests/test_admin_server.py`
  * `tests/test_db.py`

## Initial Design Direction

推荐 MVP 采用“前端顺序批量运行 + 前端规则诊断 + 后端保持单条 run API”的方案：

* 不新增后台队列，避免引入任务状态表和并发取消语义。
* 前端根据当前筛选出的 active case 逐条调用现有单条 run API。
* 每条运行完成后立即更新本地 `runOverrides`，让列表和详情逐步刷新。
* 批量汇总和失败分类先由前端从 case/latest_run 计算。
* 后续如果用例规模变大，再升级为后端 batch API 或持久化 batch run。

这个方案最贴合当前本地轻量工具定位，同时能马上形成回归闭环。

## Decision (ADR-lite)

**Context**: 评测工作台需要尽快支持回归验收，用来支撑后续 MinerU/RAGFlow 后处理、切块、parent-child、rerank 等改动的效果判断。当前系统已有单条评测运行、latest run 和一键候选标注能力，但没有批量运行、汇总和失败分层。

**Decision**: 本轮先做 MVP：前端顺序批量运行当前 active 用例，复用 `POST /api/retrieval/eval-cases/{case_id}/run`；前端计算批量汇总和失败诊断；不新增持久化 batch/baseline 表。

**Consequences**:

* 优点：实现面小，复用现有 API 和存储，能快速形成可用回归闭环。
* 代价：刷新页面后只保留每个 case 的 latest run，不保留“某一次批量运行”的完整批次快照。
* 后续演进：当评测集稳定、需要跨版本比较时，再新增 batch run/baseline 数据模型和历史对比视图。
