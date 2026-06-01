# 用户确认记录

## 2026-05-22 02:52:24

### 范围确认

- 本阶段做 MCP server，暴露 KB 给上游 agent：
  - **search**：一次性返回融合 + rerank 后的候选 chunk 列表
  - **answer**：流式生成最终回答，delta 通过 MCP **progress notification** 推送
- 代码长在本仓库（`customer_service_agent/mcp_server.py` + `cli.py` 加 `mcp` 子命令），不另立项目
- transport 只做 **stdio**（Claude Desktop / 多数 agent CLI 通用）
- 复用现有 query analytics 打点（requester_type 默认 `mcp`）

### 4 项设计口径

- **MCP SDK 版本**：`mcp>=1.6,<2.0` —— 稳定线，避开 1.0/1.1 早期 API 变动
- **rag_tool 改动方式**：新增 `stream_answer` 不动 `answer` —— 保守不动现有测试
- **init_schema**：MCP 启动**不跑**，假设后台已初始化（只读访问）
- **top_k 默认值**：**复用 `settings.rag_top_k`**（当前 5），不为 MCP 单独设默认

### 已存在口径回顾

- 进程内 stdio：**stdout 是 MCP 协议通道，禁止 `print()` 或日志写 stdout**；所有日志走 stderr
- 失败不阻塞主链路（analytics 写入失败仅 warning）
- search / answer 都要支持工具参数 `requester_type` / `requester_id`，缺则取 env `MCP_REQUESTER_TYPE/ID`，再缺用 `mcp` / `null`

### 计划文档
- `docs/changes/20260522-025224-mcp-server/update-plan.md`

## 完成记录（2026-05-22）

### 落地范围
- **MCP server**：`customer_service_agent/mcp_server.py`（~270 行），暴露 `search` 和 `answer` 两个工具
  - `search`：一次性返回融合 + rerank 后的 chunk 列表（top_score / hit_count / documents）
  - `answer`：通过 `session.send_progress_notification(progress_token, progress, message=delta)` 流式推送 chat delta，tool result 返回完整 answer + 来源
  - 每次调用都写 `query_analytics_events`，`metadata.flow` 区分 `mcp_search` / `mcp_answer`
  - requester 身份：args > env (`MCP_REQUESTER_TYPE` / `MCP_REQUESTER_ID`) > 默认 (`mcp`, `None`)
  - 业务逻辑（`handle_search` / `handle_answer` / `resolve_requester`）做成纯函数，绑定 SDK 装饰器的 `call_tool` 只做参数适配 → 测试不依赖真实 stdio runtime
- **rag_tool.stream_answer**：新生成器，按 `{"type": "delta"}` 顺序 yield，最后 yield `{"type": "final", ...}`，包含 answer_draft / documents / top_score / hit_count
- **CLI**：`customer-service-agent mcp` 子命令，调 `run_stdio(settings)`；stdio 启动时 logging 显式重定向到 stderr，避免污染协议通道
- **依赖**：`pyproject.toml` 加 `mcp>=1.6,<2.0`（实际安装 1.27.1）；不动现有依赖
- **stdio 协议安全**：`run_stdio` 内禁止往 stdout 写日志；不调用 `init_schema`（按确认结论假设后台已初始化）

### 测试与校验
- 红→绿 TDD：先在 `tests/test_rag_tool.py` 加 3 条 `stream_answer` 用例 + 新建 `tests/test_mcp_server.py` 8 条用例确认红灯，再实现
- `pytest -q` → **257 passed**（原 244 + 新 13）
- `ruff check customer_service_agent tests` → All checks passed
- `python -m customer_service_agent.cli check-config` → config ok
- `python -m customer_service_agent.cli mcp --help` → 子命令注册成功（usage 正确）
- init-db 未执行（假设 DB 已初始化，且新增改动只读已存在表）

### 设计要点回顾
- **流式契约**：MCP 客户端没传 `progressToken` 时，answer 仍然能正常返回完整结果（不抛异常、不打 progress）；适合 Claude Desktop 之外的非流式客户端
- **失败隔离**：analytics 写入失败 / progress notification 推送失败都只打 warning，不阻塞主链路
- **不动现有**：`iter_assistant_chat_events`、admin 看板、frontend、analytics schema 全部不动；只新增 `mcp_server.py` + `cli.py` 一行子命令 + `rag_tool.stream_answer`

### 风险与后续
- `mcp 1.27.1` 比锁定下界 1.6 高很多，未来如果 2.x 发布要重新评估 API 兼容性
- 当前只支持 stdio；要给远程 agent / 浏览器调用，下一步可加 SSE 或 Streamable HTTP transport（MCP 1.x 已有这些 transport，复用同一个 `Server` 实例即可）
- agent 编排（写五点、客诉自动回复等）属于另一个独立项目；本仓库只负责 KB 层 + MCP 接口
