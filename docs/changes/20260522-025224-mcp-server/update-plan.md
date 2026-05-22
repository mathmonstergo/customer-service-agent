# MCP Server 计划

## 背景结论

KB 项目已完成 Reranker + Query Analytics（见 `20260521-175122-rerank-and-query-analytics`），下一步把现有 RAG 能力以 MCP server 形态暴露给上游 agent，验证 KB 层的真实用法。

用户口径：
- 暴露两个工具：`search`（一次性返回候选）+ `answer`（流式返回回答）
- 流式走 MCP progress notification 推 delta
- 代码长在本仓库（`customer_service_agent/mcp_server.py`），不另立项目

## 修改目标

- 提供一个可被 Claude Desktop / 其它 MCP 客户端通过 stdio transport 拉起的 MCP server
- `search` 工具：复用现有 RAG 召回链路（vector + keyword + RRF + 可选 rerank），返回 chunk 列表
- `answer` 工具：复用 chat client 流式生成；每个 delta 通过 progress notification 推给客户端；最终 tool result 返回完整答案 + 来源
- 每次调用都写一条 `query_analytics_events`（复用现有打点），requester_type 默认 `mcp`，requester_id 从启动 env 或工具参数取
- CLI 加 `mcp` 子命令一键启动

## 影响范围

### 依赖
- `pyproject.toml` 加 `mcp>=1.0`（Anthropic 官方 Python SDK）
- 仅在 stdio server 路径用到，不影响其它运行模式

### 新增文件
- `customer_service_agent/mcp_server.py`：MCP server 主体
  - `build_mcp_server(settings, *, rag_tool=None) -> mcp.server.Server`
  - 注册 `search` / `answer` 两个 tool handler
  - `run_stdio(settings)`：启动 stdio transport
- `tests/test_mcp_server.py`：handler 单元测试（用假 RagTool / FakeDatabase / FakeChat）

### 已有文件改动
- `customer_service_agent/cli.py`：新增 `mcp` 子命令 → 调 `mcp_server.run_stdio(load_settings())`
- `customer_service_agent/rag_tool.py`：加 `stream_answer(question, *, system_prompt) -> Iterator[(delta, final_payload)]` 类似生成器接口
  - 现有 `answer()` 改为复用流式实现：聚合所有 delta 再返回，行为不变
  - 或者新增独立 `stream_answer` 方法不动 `answer`（更稳，倾向这个）

### 不动
- 不动 `iter_assistant_chat_events`（admin SSE 链路）
- 不动 frontend
- 不动 analytics schema

## 具体步骤（TDD）

1. 写测试：`tests/test_mcp_server.py`
   - `test_list_tools_returns_search_and_answer`
   - `test_search_tool_calls_rag_and_records_event` — mock RagTool，验证打点写入
   - `test_answer_tool_streams_deltas_via_progress_notification` — 收集 progress 通知 + 验证最终 tool result
   - `test_answer_tool_records_event_with_rerank_flag`
   - `test_search_tool_uses_requester_type_from_payload_or_env`
2. 写测试：`tests/test_rag_tool.py`（如果没有该文件，新建）
   - `test_rag_tool_stream_answer_yields_deltas_and_final_payload`
3. 实现 `rag_tool.RagTool.stream_answer`
4. 实现 `mcp_server.py`
5. 在 `cli.py` 加 `mcp` 子命令
6. `pyproject.toml` 加依赖
7. 跑全量 pytest + ruff + check-config

## 设计要点

### MCP 工具 schema

**search**
- input: `{ query: string, top_k?: int, requester_type?: string, requester_id?: string }`
- output (tool result content):
  - text block：人类可读摘要（"找到 N 条候选，top_score 0.82"）
  - structured content（如果 SDK 支持）或 JSON text block：
    ```json
    {
      "documents": [
        {"id": "kc_1", "score": 0.82, "source_type": "faq",
         "source_title": "...", "content": "...", "section_path": [...]}
      ],
      "top_score": 0.82,
      "hit_count": 3,
      "rerank_used": true
    }
    ```

**answer**
- input: `{ query: string, system_prompt?: string, top_k?: int, requester_type?: string, requester_id?: string }`
- progress notifications: 每个 chat delta → `notifications/progress { progressToken, progress: N, total: null, message: <delta-text> }`
- output (tool result content):
  - text block：完整答案
  - JSON text block：`{ "answer": "...", "documents": [...], "top_score": ..., "hit_count": ..., "latency_ms": ... }`

### 流式实现（progress notification）

- MCP SDK 在 server 端可以 `await ctx.session.send_progress_notification(progress_token, progress, total, message)`
- `answer` handler 拿到 progressToken（如果客户端 request 里带了 `_meta.progressToken`）
- 每个 chat delta → 发一个 progress notification，`message=<delta-text>`，`progress` 单调递增（用累计字符数或片段计数）
- 客户端没传 progressToken 也要 work（不报错，照样最终返回完整结果）

### Requester 身份

- 工具参数 `requester_type` / `requester_id` 优先
- 否则取启动 env `MCP_REQUESTER_TYPE` / `MCP_REQUESTER_ID`
- 都没有就用 `mcp` / `null`

### Analytics 打点

- search：完成后 `record_query_event` with `hit_count=len(docs), top_score, rerank_used, metadata={"flow": "mcp_search"}`
- answer：完成后 `record_query_event` with metadata `{"flow": "mcp_answer"}`
- 失败不抛（沿用 admin 链路的 try/except 策略）

### stdio 协议安全

- MCP stdio：stdout 是协议通道，**绝对禁止往 stdout 写日志**
- 用 logging 配置全部走 stderr
- `print()` 不能用；CLI 启动时直接调 SDK 的 `stdio_server()` context manager

### 依赖锁定

- `mcp>=1.0,<2.0`
- 该包依赖 `pydantic` `anyio` 等，会扩张 lock，但 KB 已有 `openai` `psycopg` `python-dotenv` 等，可接受

### 不做

- 不做 HTTP/SSE transport（先 stdio）
- 不做认证（stdio 进程级隔离）
- 不做 resources / prompts MCP feature（只暴露 tools）
- 不做 streaming source documents（answer 完成后一次性给 sources）
- 不暴露 analytics（按确认结论）

## 验证命令

- `source /home/adam/miniconda3/etc/profile.d/conda.sh && conda run -n customer-service-agent python -m pytest -q`
- `source /home/adam/miniconda3/etc/profile.d/conda.sh && conda run -n customer-service-agent python -m ruff check customer_service_agent tests`
- `source /home/adam/miniconda3/etc/profile.d/conda.sh && conda run -n customer-service-agent python -m customer_service_agent.cli check-config`
- `source /home/adam/miniconda3/etc/profile.d/conda.sh && conda run -n customer-service-agent python -m customer_service_agent.cli mcp --help`（确认子命令注册）

## 需要用户确认的问题

1. **MCP SDK 版本**：直接锁 `mcp>=1.0`？还是更保守的 `mcp>=1.6,<2.0`（避开早期 1.0 / 1.1 的 API 变动）？建议**1.6+**，当前稳定线。
2. **rag_tool 改动方式**：新增 `stream_answer` 不动 `answer`（保守）vs 把 `answer` 改为 `stream_answer` 的聚合包装（统一但更动）？建议**新增不动**，减少 admin 测试受影响风险。
3. **MCP 启动时是否自动跑 `init_schema`**？建议**不跑**，假设管理后台已初始化；MCP 启动只读不建表。
4. **`top_k` 默认值**：用 `Settings.rag_top_k`（5）还是给 MCP 一个独立默认（比如 8）？建议**复用 settings**，配置单一来源。

## 暂不包含

- HTTP / SSE transport
- 认证 / rate limit
- prompts / resources MCP features
- streaming source documents
- agent 编排（属于另一个项目）
