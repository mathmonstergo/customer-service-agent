# 平台问答效果验收工具

## Goal

把当前已经存在的检索评测后端能力产品化到内部平台，让团队可以维护标准问题集、运行评测、查看命中来源和指标，快速判断知识库资料、切块、关键词、别名和问答策略是否真的有效。当前阶段优先服务内部验收和调参，不做外部 API、权限、审计或完整知识图谱。

## What I Already Know

* 用户希望继续下一步，方向是先做“平台问答效果验收工具”，再考虑知识图谱和图谱可视化。
* 当前项目已有 `retrieval_eval_cases`、`retrieval_eval_runs`、`retrieval_aliases` 数据表和数据库方法。
* 后端已有最小 API：
  * `GET /api/retrieval/eval-cases`
  * `POST /api/retrieval/eval-cases`
  * `POST /api/retrieval/eval-cases/{case_id}/run`
  * `GET /api/retrieval/aliases`
  * `POST /api/retrieval/aliases`
* `AdminApp.run_retrieval_eval_case()` 已复用当前 hybrid 检索链路，保存 `retrieved_items`、`metrics`、`analysis`。
* 当前 React 路由只有 `/documents`、`/faqs`、`/assistant`，没有评测工作台页面。
* 当前问答页已有流程详情抽屉，能展示单次问答的步骤、命中来源和来源字段。
* 用户明确：问答机器人长期方向应该是 agentic。
* 用户确认：评测工作台可以做独立页面。
* 之前已明确：微信、CLI、MCP、外部 API、权限、限流、审计暂不处理。

## Assumptions

* 第一版只需要内部手工维护评测用例，不做自动从聊天记录/FAQ 批量生成用例。
* 第一版评测重点是“检索效果”，不是让 LLM 自动判答案好坏。
* 评测用例的期望命中可以先用 `expected_source_ids` 或 `expected_chunk_ids`，不要求复杂标注体系。
* 评测页面应偏工具型、信息密集但清晰，沿用现有后台风格。

## Open Questions

* 当前无阻塞问题。

## Requirements (Evolving)

* 提供内部页面入口，用于查看检索评测用例列表。
* 支持新增/编辑评测用例：问题、意图、期望 source ids、期望 chunk ids、标签、备注、状态。
* 第一版采用 Approach A：只做检索评测工作台，不跑完整 LLM 回答生成。
* 第一版只支持运行单条评测用例；批量运行全部 active 用例后置，避免 MVP 同时引入队列/并发、失败重试、批量进度和汇总报表复杂度。
* 与问答页边界：问答页继续负责“单次问答调试”，展示一次真实问答的步骤、命中来源、score、召回通道；评测工作台负责“固定问题集验收”，在这些字段基础上增加期望命中判断和可反复运行记录。
* 页面入口采用独立路由，例如 `/evaluation`，避免把问答页变成重型评测系统。
* 评测数据结构和页面文案需要为后续 agentic 问答预留扩展点：后续可评估 planner、工具调用、检索动作、风险策略和最终回答，但本轮只落地 retrieval evaluation。
* 支持运行单条评测，并展示最近运行结果：
  * query analysis / rewrite / query terms
  * vector_count / keyword_count
  * Recall@K / MRR / top1 hit
  * topK 候选、source_type、source_id、chunk_id、score、retrieval_channels
* 支持区分失败类型：无命中、低分命中、期望未命中、风险策略类样本。
* 支持别名词典最小维护入口，便于调关键词召回。
* 不改变当前问答页主链路；评测页复用已有后端能力。

## Acceptance Criteria (Evolving)

* [ ] 平台有可进入的评测工作台页面。
* [ ] 评测工作台通过独立路由进入，不塞进现有问答页。
* [ ] 用户能创建/编辑/停用评测用例。
* [ ] 用户能运行单条评测并看到指标与候选来源。
* [ ] 评测结果能在问答页已有来源展示能力基础上额外显示期望命中判断。
* [ ] 候选来源展示字段足够定位到 FAQ 或文档切片。
* [ ] 别名词典可以查看和维护，运行评测时能体现关键词扩展。
* [ ] 后端和前端有针对新增行为的测试或可说明的手工验证。

## Definition of Done

* Tests added or updated for backend behavior that changes.
* Frontend build passes.
* Existing backend pytest and ruff remain green, or unrelated failures are explicitly documented.
* Docs/changes updated with plan, confirmation, and verification record.
* No changes to微信、CLI、MCP、外部 API、权限、限流、审计。

## Out of Scope

* 知识图谱抽取、存储和可视化。
* Agentic planner / tool loop 实现。
* Agentic 问答完整轨迹评测。
* 自动 LLM 答案质量评分。
* 批量运行全部 active 评测用例。
* 批量导入评测集文件。
* 外部 API 或开放评测接口。
* 用户权限、限流、审计。
* 微信、CLI、MCP。

## Technical Notes

* Backend:
  * `customer_service_agent/admin_server.py`
  * `customer_service_agent/db/retrieval_meta.py`
  * `customer_service_agent/retrieval.py`
* Existing tests:
  * `tests/test_admin_server.py`
  * `tests/test_db.py`
  * `tests/test_retrieval.py`
* Frontend:
  * `web/src/main.tsx`
  * `web/src/api/hooks.ts`
  * `web/src/api/schemas.ts`
  * likely new page under `web/src/pages/`
* Relevant docs:
  * `docs/changes/20260514-124612-retrieval-phase-one/`
  * `docs/changes/20260615-111942-platform-assistant-correctness/`
  * `docs/changes/20260615-130211-assistant-evaluation-workbench/`

## Research References

* [`research/agentic-rag-patterns.md`](research/agentic-rag-patterns.md) — 成熟项目普遍把 agentic RAG 定义为“LLM 决策循环 + 工具调用 + 检索/改写/打分/重试/轨迹”，而不只是替换检索算法。

## Candidate MVP Approaches

### Approach A: 检索评测工作台 (Recommended)

页面化已有 eval-cases/run/aliases 能力，只评估检索命中，不跑完整回答生成。

Pros: 复用现有后端，风险低，最快看到知识库检索效果；适合当前“内部先跑通流程”的阶段。

Cons: 不能直接评估最终回答语气和完整性。

### Approach B: 问答回放工作台

每个测试问题都跑完整 `/api/assistant/chat-stream`，保存答案、来源和步骤。

Pros: 更接近真实用户问答效果。

Cons: 成本更高、耗时更长、结果受 LLM 波动影响，第一版更难稳定验收。

### Approach C: 评测 + 知识图谱雏形

评测页面同时预留实体/关系/图谱视图。

Pros: 和后续 KG 方向衔接更明显。

Cons: 范围过大，会拖慢当前“先看到知识库效果”的目标。

## Decision (ADR-lite)

**Context**: 问答页已经能展示单次问答的流程、命中来源、score 和召回通道，但它不是固定用例验收工具，不能稳定判断一次检索策略改动是提升还是退化。

**Decision**: 第一版选择 Approach A：做独立的检索评测工作台，复用问答页已有的来源/score/通道展示口径，但新增标准问题集、期望命中、Recall@K、MRR、Top1 命中等评测字段。不跑完整 LLM 回答生成。

**Consequences**: 能最快量化知识库检索效果，适合内部验收和调参。最终回答质量、语气和完整性仍需要后续“问答回放/答案评分”阶段处理。

## Agentic Direction Note

长期问答机器人方向按 agentic 设计：后续可能包含任务规划、工具选择、检索动作、知识图谱查询、风险检查、回答生成和自检。当前评测工作台先服务最底层的“检索是否准确”，但 UI 和运行结果命名不应写死为只能评估向量检索；建议用 `strategy` / `run type` 区分 `retrieval_hybrid_v1`、未来 `agentic_rag_v1` 等运行模式。

外部调研显示，agentic RAG 相比普通 RAG 通常多出 planner/tool selector、tool registry、query rewrite、relevance grader、iterative loop、state/memory、observability trace、stopping reason 等组件。本任务只保留命名和详情区域扩展点，不实现这些 agentic 组件。
