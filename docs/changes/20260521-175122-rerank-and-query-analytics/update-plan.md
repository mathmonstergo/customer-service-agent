# Reranker + Query Analytics 计划

## 背景结论

项目定位转型为"企业级跨境电商内部知识库层"，未来作为 MCP server 给上游 agent 调用。本阶段先做两件事：

1. **Reranker**：在混合检索（vector + keyword RRF）之后加一层 cross-encoder 重排，把召回精度往上抬一档。这是检索质量单次最大可见提升。
2. **Query Analytics**：每次查询都记录到 DB，admin 后台看板呈现高频 / 零命中 / 低置信查询；零命中查询可选用 LLM 聚类。这是企业级 KB 的"眼睛"——没它后续任何改动都无法量化。

不做架构重构（db.py / admin_server.py 拆分留下一阶段）、不做 MCP server transport（等 agent 项目立起来再加）。

## 修改目标

- 给 retrieval 链路引入可选的 cross-encoder rerank 阶段，配置存在即启用，缺失即透明回退。
- 给所有查询路径（rag_tool / RAG / admin 智能问答）打点写入新表 `query_analytics_events`，后续可分析。
- 给 admin 设置页加 Rerank 模型配置（base_url + api_key + model + input_size），UI 风格与现有 chat/embedding 设置一致。
- 给 admin 增加"查询看板"页：高频 / 零命中 / 低置信 / 命中率趋势 / chunk 引用频次。
- 零命中聚类用现有 chat client 完成，独立按钮触发，不进自动流程。

## 影响范围

### 配置层
- `customer_service_agent/config.py`
  - 新增字段：`rerank_base_url`、`rerank_api_key`、`rerank_model`、`rerank_input_size`（默认 50）
  - `SETTINGS_ENV_FIELDS` 增加：`RERANK_BASE_URL`、`RERANK_API_KEY`、`RERANK_MODEL`、`RERANK_INPUT_SIZE`
  - `from_env` 增加解析

### 模型客户端层
- `customer_service_agent/llm.py`
  - 新增 `RerankClient` 类：构造 `from_settings(settings)`、`rerank(query, documents, top_n)` 方法
  - 调用 Cohere 兼容协议：`POST {base_url}/v1/rerank` body `{model, query, documents, top_n}`
  - 返回归一化的 `list[RerankResult]`（含 `index` 和 `relevance_score`）
  - 未配置 base_url / key / model 任一项时，`from_settings` 返回 None；调用方据此跳过 rerank

### 检索层
- `customer_service_agent/retrieval.py`
  - 新增 `rerank_candidates(query, candidates, client, top_k)` 函数：取前 `RERANK_INPUT_SIZE` 候选，调 client，按 relevance_score 排序，截 top_k
  - 不修改 `analyze_query` / `fuse_retrieval_candidates`；rerank 是融合后的独立阶段
- `customer_service_agent/db.py`
  - 检索入口（如 `search_knowledge_with_keywords` 等）保持 vector + keyword 召回 limit 提到 `max(RAG_TOP_K, RERANK_INPUT_SIZE)`
- `customer_service_agent/rag.py` / `rag_tool.py`
  - 在调用 `search` 之后、构造 prompt 之前插入 `rerank_candidates` 步骤
  - rerank client 缺失则透传原候选

### 数据库 schema
- `sql/001_init.sql` + `db.py` 的 `init_schema`
  - 新表 `query_analytics_events`：
    ```sql
    CREATE TABLE IF NOT EXISTS query_analytics_events (
        id BIGSERIAL PRIMARY KEY,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        query TEXT NOT NULL,
        intent TEXT,
        retrieved_chunk_ids TEXT[] NOT NULL DEFAULT '{}',
        top_score DOUBLE PRECISION,
        hit_count INT NOT NULL DEFAULT 0,
        rerank_used BOOLEAN NOT NULL DEFAULT false,
        latency_ms INT,
        requester_type TEXT NOT NULL DEFAULT 'unknown',
        requester_id TEXT,
        metadata JSONB NOT NULL DEFAULT '{}'::jsonb
    );
    CREATE INDEX IF NOT EXISTS idx_query_analytics_created_at ON query_analytics_events (created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_query_analytics_hit_zero ON query_analytics_events (created_at DESC) WHERE hit_count = 0;
    ```
  - 新表 `query_analytics_cluster_summaries`（可选，存 LLM 聚类结果）：
    ```sql
    CREATE TABLE IF NOT EXISTS query_analytics_cluster_summaries (
        id BIGSERIAL PRIMARY KEY,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        period_start TIMESTAMPTZ NOT NULL,
        period_end TIMESTAMPTZ NOT NULL,
        cluster_label TEXT NOT NULL,
        suggested_content TEXT,
        event_count INT NOT NULL,
        sample_queries TEXT[] NOT NULL DEFAULT '{}'
    );
    ```

### 数据访问层
- `customer_service_agent/db.py`
  - `record_query_event(event_dict)`：写入一行
  - `list_top_queries(limit, since)`：聚合最常见 query（normalized 后）
  - `list_zero_hit_queries(limit, since)`：hit_count=0 的最近查询
  - `list_low_score_queries(limit, since, threshold)`：top_score < threshold 的最近查询
  - `query_hit_rate_timeseries(bucket, since)`：每日/每小时命中率
  - `top_referenced_chunks(limit, since)`：chunk_id 在 retrieved_chunk_ids 中出现频次
  - `save_cluster_summary(row)` / `list_cluster_summaries(...)`

### Admin API
- `customer_service_agent/admin_server.py`
  - `settings_snapshot` / `update_settings` 增加 rerank 4 个字段
  - 新增 `/api/analytics/overview` GET：返回今日 / 7 日 / 30 日命中率、总查询、零命中数
  - 新增 `/api/analytics/top-queries` GET
  - 新增 `/api/analytics/zero-hit` GET
  - 新增 `/api/analytics/low-score` GET
  - 新增 `/api/analytics/top-chunks` GET
  - 新增 `/api/analytics/cluster-zero-hit` POST：触发 LLM 聚类，写入 cluster_summaries
  - 新增 `/api/analytics/cluster-summaries` GET
  - 把 retrieval 主路径（assistant chat、rag 测试、未来 rag_tool）改成 wrap 一层"记录后返回"

### 工具接口
- `customer_service_agent/rag_tool.py`
  - `search` / `answer` 增加可选 `requester_type` / `requester_id` 参数
  - 内部读 header `X-Requester-Type` / `X-Requester-Id`（如果上游用 HTTP）→ 这一层 rag_tool 是 Python，不直接 HTTP；HTTP 那一层在 admin_server 里包

### 前端
- `customer_service_agent/static/admin.html` / `admin.js` / `admin.css`
  - 设置弹窗：在 LLM/Embedding 后面加 "Rerank 模型" 一节，4 个字段 + 复用现有 secret reveal 组件
  - 顶部导航新增"查询分析"页签 → 新建 `<section id="analyticsView">`：
    - 概览卡片（今日 / 7 日 / 30 日）
    - 高频查询表
    - 零命中查询表 + "用 LLM 聚类"按钮
    - 低置信查询表
    - 命中率折线图（用 SVG 简单画，不引图表库）
    - chunk 引用频次表
    - 聚类结果列表

### 测试
- `tests/test_config.py`：rerank 字段默认值 + env 覆盖
- `tests/test_llm.py`：RerankClient 构造 / 调用 / 返回归一化 / 缺配置返回 None
- `tests/test_retrieval.py`：`rerank_candidates` 按 score 重排 / 输入小于 top_k 时不调 API / client=None 时透传
- `tests/test_db.py`：`record_query_event` 写入 / 各聚合查询 SQL
- `tests/test_admin_server.py`：analytics API 几个端点的 happy path / 设置页 rerank 字段持久化
- 新建 `tests/test_analytics_views.py`（如果 admin 测试文件太大）

## 具体步骤（TDD 顺序）

1. 写测试：config 新字段
2. 实现 config 新字段
3. 写测试：RerankClient 构造 + Cohere 协议调用（mock requests）+ 缺配置返回 None
4. 实现 RerankClient
5. 写测试：`rerank_candidates` 行为（重排 / 透传 / 调用次数）
6. 实现 `rerank_candidates`
7. 写测试：DB schema 包含 query_analytics_events，`record_query_event` 写入回读一致
8. 实现 schema + record_query_event
9. 写测试：各聚合 SQL（top / zero-hit / low-score / time-series / chunk-refs）
10. 实现聚合方法
11. 写测试：retrieval 主路径调用时记录 event（rag / rag_tool / assistant chat 包一层）
12. 实现 retrieval 路径打点
13. 写测试：admin analytics API 几个端点的 happy path
14. 实现 admin analytics API
15. 写测试：零命中 LLM 聚类（mock chat client，验证 prompt 形态 + 写入 cluster_summaries）
16. 实现聚类按钮路径
17. 前端 UI：设置页 rerank 字段 + 查询分析页签
18. 跑全量 pytest + ruff + check-config + init-db
19. 填 confirmation.md

## 设计要点

### Rerank Client
- HTTP 调用直接用 `requests.post`（项目已用），不引新依赖
- 超时：默认 30 秒（与 chat client 一致）
- 失败处理：调用失败 → 打 warning + 返回 None → 上层退回原候选；**不影响主链路**
- 返回归一化：`[(chunk_index, score), ...]` 按 score 降序

### Rerank 触发条件
- `RerankClient.from_settings(settings)` 三个字段都配齐才返回实例
- 调用方拿到 None 直接跳过
- 候选数 ≤ top_k 时也跳过（无需重排）

### 检索召回数量
- 当前 `search` 走 `top_k=5`
- 接 rerank 后：先召回 `max(top_k, RERANK_INPUT_SIZE)` 条，rerank 完截到 top_k
- 不破坏现有 rag.py / rag_tool.py 的 `top_k` 语义

### 打点位置
- 抽一个 `record_retrieval_event(app, query, intent, docs, latency_ms, requester)` 工具函数
- 在 `admin_server` 的 retrieval/RAG 路径包一层
- 在 `rag_tool` 的 `search`/`answer` 包一层
- 出错不影响主流程（try/except + log warning）

### 零命中 LLM 聚类
- 取最近 N 天（默认 7）的零命中 query
- 上限 200 条（避免 prompt 爆炸），多了随机抽样
- prompt 结构：
  > "下面是过去 7 天 N 条没有命中知识库的用户查询。请按主题聚类（不超过 10 类），每类给出：cluster_label（中文短语）、suggested_content（建议补充什么内容）、representative_queries（代表性 3-5 条）。输出 JSON。"
- 解析 JSON → 逐行写入 cluster_summaries
- 失败不抛，记 admin 错误

### Privacy / 数据安全
- query 文本会落到 DB——AGENTS.md 说"客户聊天记录不能提交 Git"，DB 不入 Git 没问题，但 `.gitignore` 不需要改
- 不写 retrieved chunk 的完整文本，只写 chunk_id
- 不写 LLM 完整回答

### 前端简化
- 不引入 chart 库；折线图用纯 SVG 几行代码画
- 表格复用现有 admin.css 样式

## 预期效果

- agent 测试 / 客户查询走完一遍以后，admin 看板能直接看到"问什么 / 命中没 / 多快 / 谁问的"
- 命中精度因为 rerank 阶段实测上一档（粗估 +15% 左右，取决于内容质量）
- 后续任何检索调优（embedding 模型、chunk 策略、关键词权重）都能用 analytics 做 before/after 对比
- 用户可以一键看到"哪些主题用户在问但我没内容"，反向驱动内容建设

## 需要用户确认的问题

1. **DB schema 落地方式**：现在 schema 在 `sql/001_init.sql` 一个文件里。新表是追加到这个文件里，还是建一个 `sql/002_analytics.sql`？建议**追加到 001**，保持初始化简单（项目还没多 schema 文件管理工具）。
2. **看板默认时间窗口**：开第一眼看几天？建议**最近 7 天**。
3. **零命中聚类的"零"怎么定义**：`hit_count == 0`（一条都没召回）？还是 `top_score < min_score`（召回了但都不够格）？建议**两者都算**：UI 上分开 "零命中" 和 "低置信" 两个 tab。
4. **rerank_input_size 默认 50 OK 吗**？rerank 50 → 取 top 5，typical Cohere API 单次大约几十毫秒。
5. **前端折线图**：自己用 SVG 画 vs 引 chart.js 等库？我倾向自己画（项目历来零前端依赖）。

## 暂不包含

- 不做 MCP server transport（等 agent 项目立起来）
- 不做多租户 namespace（设计上为之留口子但本轮不实施）
- 不做 incremental embedding sync
- 不做架构层拆分
- 不做缓存层 / rate limit
- 不做 PG → 其它 DB 迁移

## 验证命令

- `source /home/adam/miniconda3/etc/profile.d/conda.sh && conda run -n customer-service-agent python -m pytest -q`
- `source /home/adam/miniconda3/etc/profile.d/conda.sh && conda run -n customer-service-agent python -m ruff check .`
- `source /home/adam/miniconda3/etc/profile.d/conda.sh && conda run -n customer-service-agent python -m customer_service_agent.cli check-config`
- `source /home/adam/miniconda3/etc/profile.d/conda.sh && conda run -n customer-service-agent python -m customer_service_agent.cli init-db`
- `node --check customer_service_agent/static/admin.js`
- `git diff --check`
