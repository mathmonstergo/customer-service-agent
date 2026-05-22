# 用户确认记录

## 2026-05-21 17:51:22

### 范围确认

- 本阶段两件事：**Reranker**（Cohere 格式 API，配了就启用）+ **Query Analytics**（DB 打点 + 看板 + 零命中 LLM 聚类按钮）。
- 不动架构、不做 MCP transport、不做多租户、不做 incremental sync。
- 项目定位：企业级跨境电商内部知识库层，未来作为 MCP server 给上游 agent 调用。

### 4 项设计口径

- **Schema 落地**：追加到 `sql/001_init.sql`（保持 init-db 一个文件）。
- **零命中 / 低置信 UI**：两个 tab 分开（`hit_count=0` 和 `top_score<阈值`）；LLM 聚类默认用零命中，可选低置信。
- **趋势图实现**：纯 SVG 自画，不引前端依赖。
- **`RERANK_INPUT_SIZE` 默认 50**：vector + keyword 召回到 50，rerank 截到 `RAG_TOP_K`（默认 5）。

### 已存在口径回顾

- Cohere `/v1/rerank` 协议格式（`{model, query, documents, top_n}`）→ 不兼容本地 sentence-transformers，要本地跑请自部署 OpenAI 兼容 wrapper。
- 配了 base_url + api_key + model 自动启用，缺一项就回退到 RRF 结果，不报错。
- requester 身份强制：调查询接口必须传 `X-Requester-Type` / `X-Requester-Id` header，未传记 `unknown`。
- 零命中聚类用现有 chat client，独立按钮触发，不进自动流程。

### 计划文档
- `docs/changes/20260521-175122-rerank-and-query-analytics/update-plan.md`

## 完成记录（2026-05-21）

### 落地范围
- **Reranker 层**：`Settings` 加 `rerank_base_url/api_key/model/input_size`；`RerankClient` 走 Cohere `/v1/rerank`，缺配置自动回退；`rerank_candidates(query, candidates, *, client, top_k)` 在融合候选 > top_k 时按 cross-encoder 重排，失败不影响主链路。
- **Query Analytics 层**：新增 `query_analytics_events` + `query_analytics_cluster_summaries` 两张表；`Database` 加 `record_query_event / list_top_queries / list_zero_hit_queries / list_low_score_queries / query_hit_rate_timeseries / top_referenced_chunks / save_cluster_summary / list_cluster_summaries / query_analytics_overview`。
- **AdminApp 集成**：`iter_assistant_chat_events` 在融合后插入条件 rerank step，结束后写一条 `query_analytics_events`（query / intent / chunk_ids / top_score / hit_count / rerank_used / latency / requester / metadata）。新增 7 个 `/api/analytics/*` 路由 + 1 个 `/api/analytics/cluster-zero-hit` POST。HTTP 层从 `X-Requester-Type / X-Requester-Id` header 兜底注入 payload。
- **前端**：设置弹窗加 "Rerank 模型" 面板（Base URL / API Key / Model / 输入候选数）；主页加 "查询分析" 卡 + `analyticsWorkspace`：今日/7日/30日概览卡、SVG 命中率折线、五个 tab（高频 / 零命中 / 低置信 / chunk 引用 / LLM 聚类），零命中聚类按钮直接触发后端 LLM。

### 测试与校验
- 红→绿 TDD：先在 `test_config / test_llm / test_retrieval / test_db / test_admin_server` 加 21 条失败用例确认红灯，再逐层实现。
- `pytest -q` → 244 passed（原 216 + 新 28，含一条原 settings_snapshot 测试加 rerank 字段补全）。
- `ruff check customer_service_agent tests` → All checks passed。
- `python -m customer_service_agent.cli check-config` → config ok。
- `node --check customer_service_agent/static/admin.js` → 通过（无输出即 OK）。
- init-db 未本地执行（无运行中的 PG 实例），schema 改动通过 string assertion 测试覆盖。

### 风险与后续
- Rerank 失败 / 配置缺失时透传原候选，主路径绝不阻塞；rerank step 仅在实际触发时 yield，故不影响现有事件序列断言。
- query 文本会落 DB；DB 不入 Git，沿用既有 `.gitignore` 策略，无需变更。
- 后续若做 MCP server 暴露 search 接口，`requester_type / requester_id` 已就位；MCP transport 留给下一个项目。
- 前端折线图为自画 SVG，无新前端依赖；未来加更复杂图表时再评估是否引入图表库。
