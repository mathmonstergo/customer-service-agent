# FastAPI/ASGI 全量迁移与问答性能加固

## Goal

把当前标准库 `ThreadingHTTPServer` 管理后台全量迁移到 FastAPI/ASGI，同时强化问答-检索-生成链路，为未来面向 C 端开放提供更合适的并发模型、流式响应能力、API 结构和性能保护。

## What I Already Know

* 当前问答链路在 `AdminApp.iter_assistant_chat_events()` 内同步执行：意图识别、embedding、向量检索、关键词检索、可选 rerank、父 chunk 回填、LLM 流式生成、查询打点。
* HTTP 服务使用标准库 `ThreadingHTTPServer`，每个流式问答请求会长期占用一个线程。
* `Database.connect()` 当前每次操作新建 psycopg 连接，问答链路会多次访问数据库。
* `ChatClient`、`EmbeddingClient`、`RerankClient` 都是同步外部调用；模型供应商限流、超时、网络波动会直接影响用户请求。
* 项目仍定位为本地内部工具；面向 C 端开放前必须谨慎处理鉴权、限流、超时、降级和观测。
* 用户已在 2026-07-06 确认选择 Option C：启动 ASGI/FastAPI 迁移，而不是只做原地加固。
* 用户已在 2026-07-06 进一步确认选择“全量迁移”：文档、FAQ、KG、评测、设置、上传、静态资源等管理后台 API 一起迁到 FastAPI。
* 用户已在 2026-07-06 确认让现有 `admin` 子命令直接切换到 ASGI，不保留旧 server 作为默认启动路径。
* 用户已在 2026-07-06 要求项目对外名称改为 `Cyclops`。
* 用户已在 2026-07-06 后续澄清：项目更名不是只套入口，而是实际 Python 包目录也必须迁移为 `cyclops/`。
* 官方文档研究已记录在 `research/fastapi-full-migration.md`。

## Assumptions

* 全量迁移仍应保持业务逻辑复用：优先把 HTTP 路由层换成 FastAPI，避免把 `AdminApp` 业务方法全部重写。
* 现有管理后台 API 路径、前端调试事件契约和静态资源路径尽量保持不变，避免同时引入 UI 大改。
* ASGI 迁移仍需要保留基础性能保护：数据库连接池、模型调用超时、问答并发上限、基础耗时指标和降级路径。
* `Cyclops` 命名必须覆盖用户可见层、运维入口、Python 包目录、源码 import、测试 monkeypatch 路径和前端构建输出目录。
* 保留 `/api/*` HTTP 路径是为了让当前 React 前端继续使用同一 API contract；不保留旧 Python 包名兼容入口。

## Requirements

* 引入 FastAPI/ASGI 运行入口，用于承载现有管理后台和问答流式接口。
* 把当前 `make_handler()` 覆盖的所有管理 API 路由迁到 FastAPI：
  * settings
  * import files/chunks/candidates/generation jobs
  * FAQ
  * assistant chat stream/provider probe/models
  * retrieval evaluation and aliases
  * KG entities/relations/subgraph/extraction jobs
  * analytics
  * upload/download/import assets
* 迁移静态资源服务：`/` 返回 React 入口，`/static/dist/*` 服务 Vite 构建产物。
* 迁移文件上传到 FastAPI `UploadFile`，并保留当前上传大小限制和安全文件名约束。
* 迁移文件下载和资产读取，保留路径逃逸防护和下载文件名编码。
* 为数据库访问引入连接池或等价连接复用机制，减少每个问答请求反复建连。
* 为外部模型调用增加明确超时配置，覆盖 chat、embedding、rerank。
* 为问答流式接口增加服务端并发保护，超过上限时返回用户可读流式错误，避免请求无限堆积。
* 将对外 `cyclops admin --host ... --port ...` 切换为启动 ASGI/Uvicorn 服务。
* 更新 README 和 systemd 模板中的后台启动方式，确保仍使用 `admin --host --port`。
* 将项目名改为 `Cyclops`：
  * README 标题与说明。
  * 前端侧边栏/页面标题/静态入口中可见品牌。
  * 服务启动日志和 server title。
  * systemd 描述和服务模板中用户可见名称。
  * Python package metadata 的 project display name。
  * Python 包目录、模块入口和所有运行面 import。
* 保持敏感问题短路逻辑不退化：敏感问题不得进入 embedding、检索、rerank 或答案生成。
* ASGI 问答接口复用现有 SSE 事件格式：`meta`、`step`、`delta`、`done`、`error`。
* ASGI 导入候选生成事件接口复用现有 SSE 事件格式和前端消费方式。
* 给问答链路记录或暴露基础性能分段数据：embedding、vector search、keyword search、rerank、generation、total。
* 新增或更新测试覆盖 ASGI 路由、静态文件、上传下载、连接池/配置解析、超时参数、并发保护和问答链路错误降级。

## Acceptance Criteria

* [x] 项目提供 FastAPI/ASGI app 入口，能启动现有管理后台 API 和问答流式接口。
* [x] `cyclops admin --host 127.0.0.1 --port 8765` 启动 ASGI server。
* [x] README 和 systemd 模板中的启动说明仍正确。
* [x] 用户可见项目名显示为 `Cyclops`。
* [x] 实际 Python 包目录为 `cyclops/`，不保留旧包目录或旧包入口。
* [x] 现有前端调用的 `/api/*` 路径在 ASGI app 中有对应路由。
* [x] `/` 和 `/static/dist/*` 能通过 ASGI app 服务 React 管理后台。
* [x] 文件上传、下载、import asset 路由在 ASGI app 中保持安全约束和响应语义。
* [x] `Database` 访问不再对每个操作无条件新建独立连接，且测试能验证连接获取路径。
* [x] `Settings` 支持问答相关超时和并发上限配置，并有默认值。
* [x] `ChatClient`、`EmbeddingClient`、`RerankClient` 调用使用配置化超时或客户端超时。
* [x] ASGI 问答接口超过并发上限时返回结构化 SSE `error` 或等价流式错误，不会进入检索或模型调用。
* [x] 现有 assistant SSE 契约测试继续通过。
* [x] `python -m pytest` 可通过；如环境缺失导致无法全跑，在最终说明中明确。
* [x] `python -m ruff check .` 可通过；如环境缺失导致无法全跑，在最终说明中明确。

## Verification

* `python -m pytest`（在现有本地 conda 环境中执行）：303 passed。
* `python -m ruff check .`（在现有本地 conda 环境中执行）：All checks passed。
* `npx --yes pnpm@10.10.0 --dir web test`：25 passed。
* `npx --yes pnpm@10.10.0 --dir web lint`：通过。
* `npx --yes pnpm@10.10.0 --dir web build`：通过；Vite 提示当前主 chunk 超过 500 kB，为体积警告非构建失败。
* `python -m cyclops check-config`（在现有本地 conda 环境中执行）：config ok。
* `python -m cyclops.cli check-config`（在现有本地 conda 环境中执行）：config ok。
* `git diff --check`：通过，无 whitespace 错误。
* 包名卫生测试：`tests/test_repository_hygiene.py` 确认运行/交付面不保留旧包目录、旧入口名或旧项目名。

## Definition Of Done

* 代码改动限制在 ASGI 全量路由迁移和必要性能保护范围内。
* Python 新增或修改的函数/方法都有中文注释或 docstring，说明做什么和关键约束。
* 不改变知识库审核语义，不让未审核内容进入可检索状态。
* 不默认公网暴露；远程开放仍需要单独的鉴权/审计/上传限制设计。
* 更新 `docs/changes/20260706-093651-c-end-qa-performance-hardening/` 的计划和确认记录。

## Out Of Scope

* 不新增用户登录、计费或完整 C 端账号体系。
* 不重做前端页面布局；前端最多因 API 行为兼容性做小修。
* 不更换 pgvector 或 PostgreSQL 检索栈。
* 不引入完整任务队列或独立 worker 服务。
* 不在本任务内实现完整登录、C 端账号体系、计费或公网部署方案。
* 不在本任务内重命名 GitHub 仓库和本地项目根目录；用户后续会单独改仓库名。

## Technical Approach

Current decisions:

* User chose FastAPI/ASGI migration.
* User chose full migration of the existing admin API surface, not only the C-end/assistant stream.

Recommended implementation shape for MVP:

* Add a new ASGI app module with FastAPI app factory.
* Split route adapters by domain using FastAPI `APIRouter`.
* Keep `AdminApp` as a temporary service facade, so the migration changes HTTP parsing/routing first and avoids duplicating business logic.
* Add DB pooling, model timeouts, stream concurrency limits, and latency metadata as shared infrastructure.
* Add route smoke tests and focused behavior tests for high-risk routes.
* Replace the current `admin` command with ASGI/Uvicorn startup during this task.
* Rename the actual Python package to `cyclops/` and remove the old forwarding-entry approach.

## Decision

Context: the current synchronous HTTP server can support internal tooling but is a poor fit for C-end streamed answer generation under concurrent load.

Decision: user selected Option C on 2026-07-06: use FastAPI/ASGI migration rather than only in-process hardening. User then selected full migration of the existing admin API surface and direct replacement of the existing `admin` command. User also requested the project name and actual Python package to become `Cyclops` / `cyclops`.

Consequence: scope is now large and should be implemented as a clean ASGI route-layer migration plus package rename, not as a business-logic rewrite.

## Open Question

* None. User confirmed implementation can start.

## Implementation Plan

1. Add dependencies and settings:
   * FastAPI, Uvicorn, python-multipart, optional psycopg pool support.
   * ASGI/server and model timeout/concurrency settings.
2. Add ASGI app factory:
   * app lifespan initializes `AdminApp` and database schema.
   * shared dependencies expose `AdminApp`.
   * exception handlers reuse current error classification.
3. Add FastAPI route adapters:
   * settings, FAQ, import, assistant, retrieval, KG, analytics.
   * static root and `/static/dist/*`.
   * upload/download/import asset responses.
4. Preserve streaming contracts:
   * assistant chat stream.
   * import generation job events.
5. Switch CLI `admin` to Uvicorn startup:
   * preserve `--host` and `--port`.
   * preserve loopback guard.
6. Add performance protections:
   * DB connection pooling or reusable connection manager.
   * model timeout configuration.
   * assistant stream concurrency guard.
   * latency metadata where useful.
7. Tests and docs:
   * ASGI route smoke tests for all migrated route groups.
   * focused tests for SSE, upload/download/static, config, LLM timeout, DB pooling.
   * README and systemd template update.

## Research References

* `research/fastapi-full-migration.md` — official FastAPI/Starlette docs mapping for SSE, static files, uploads, testing, routers, and Uvicorn workers.

## Technical Notes

* Relevant backend files:
  * `cyclops/admin_server.py`
  * `cyclops/db/base.py`
  * `cyclops/db/__init__.py`
  * `cyclops/llm.py`
  * `cyclops/config.py`
  * `cyclops/retrieval.py`
* Relevant tests:
  * `tests/test_admin_server.py`
  * `tests/test_db.py`
  * `tests/test_config.py`
  * `tests/test_llm.py`
  * `tests/test_rag_tool.py`
  * `tests/test_repository_hygiene.py`
* Relevant contracts:
  * `.trellis/spec/backend/cyclops-assistant-contracts.md`
  * `.trellis/spec/backend/cyclops-db-contracts.md`
  * `.trellis/spec/backend/cyclops-asgi-admin-contracts.md`
