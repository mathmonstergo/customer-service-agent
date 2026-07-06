# 管理后台全量 FastAPI/ASGI 迁移计划

## 修改目标

把现有标准库 `ThreadingHTTPServer` 管理后台全量迁移到 FastAPI/ASGI，并同步加固问答-检索-生成链路的连接复用、超时、并发保护和耗时观测。

同时将项目名改为 `Cyclops`，并将实际 Python 包目录迁移为 `cyclops/`。

## 影响范围

* 后端配置：`cyclops/config.py`
* 数据库连接：`cyclops/db/base.py`、`cyclops/db/__init__.py`
* 模型客户端：`cyclops/llm.py`
* 业务服务 facade：`cyclops/admin_server.py`
* ASGI 入口：新增 FastAPI app 模块，并让现有 `admin` 子命令启动该 ASGI 服务
* ASGI 路由：新增 `cyclops/asgi_app.py` 作为薄 route adapter，复用 `AdminApp` 业务方法
* 品牌命名：README、前端可见文案、服务启动输出、systemd 描述、包元数据
* 包名迁移：实际 Python 包目录、源码 import、测试 monkeypatch 路径、Vite 构建输出目录
* 测试：`tests/test_config.py`、`tests/test_llm.py`、`tests/test_db.py`、`tests/test_admin_server.py`、新增 ASGI 路由测试

## 具体步骤

1. 增加 FastAPI/ASGI 依赖和启动入口。
2. 新增 FastAPI app factory 和薄 route adapter，先复用 `AdminApp` 避免业务逻辑重写。
3. 把现有 `make_handler()` 中的 `/api/*` 路由迁移到 FastAPI route adapter，优先复用 `AdminApp` 方法。
4. 迁移静态文件、上传、下载和 import asset 路由，保持路径安全和响应语义。
5. 迁移 assistant chat stream 和 import generation job events，保持 SSE 事件格式。
6. 增加配置项：
   * DB 连接池最小/最大连接数。
   * Chat / Embedding / Rerank 请求超时。
   * Assistant stream 最大并发。
7. 数据库层增加连接池支持，保持现有 `with self.connect()` 调用方式尽量不变。
8. 模型客户端读取超时配置，避免外部模型调用无限等待。
9. ASGI 问答接口增加并发保护；超限时返回可读流式错误。
10. 给问答链路补充基础耗时记录，便于压测时定位瓶颈。
11. 增加/更新单元测试，确保现有敏感问题短路、SSE 契约、上传下载和关键 API 路由不退化。
12. 将对外 `cyclops admin --host ... --port ...` 切换为启动 ASGI/Uvicorn，并更新 README/systemd 模板。
13. 将用户可见项目名和实际 Python import 包名都改为 `Cyclops` / `cyclops`，不保留旧包兼容入口。
14. 运行 `python -m pytest`、`python -m ruff check .`、`python -m cyclops check-config`。

## 预期效果

* 小并发下减少 PostgreSQL 建连成本和连接数抖动。
* 外部供应商慢响应或挂起时，后端能按配置超时失败。
* C 端突发请求不会无限堆积到线程、事件循环任务和模型供应商。
* 整个管理后台可以通过 ASGI server 部署，为后续公网网关、鉴权、限流和水平扩容留接口。
* 后续压测可以区分 embedding、检索、rerank、生成等阶段耗时。

## 需要用户确认的问题

用户已选择让现有 `admin` 子命令立即切换为 ASGI，并确认可以开始实现。用户同时要求项目名改为 `Cyclops`；后续明确要求实际包目录也迁移为 `cyclops/`，不是只套入口。

## 实现记录

* 新增 `cyclops/asgi_app.py`，以 FastAPI 承载现有 settings、FAQ、import、assistant、retrieval eval、KG、analytics、静态资源、上传下载路由。
* `cyclops/cli.py` 的 `admin` 子命令切换到 Uvicorn/ASGI；`cyclops/` 是真实 Python 包目录，支持 `python -m cyclops ...`。
* 增加 FastAPI、Uvicorn、python-multipart、psycopg-pool 依赖，并同步 `pyproject.toml`、`environment.yml`、`uv.lock`。
* 数据库基础类增加连接池接入和 `close()`，ASGI lifespan 退出时释放已初始化池资源。
* Chat、Embedding、Rerank 客户端接入配置化超时；assistant stream 增加并发信号量保护。
* 前端标题、侧边栏品牌、静态 dist、README、systemd 安装脚本和模板迁移到 `Cyclops`。
* 源码和测试 import、pyproject script、Vite outDir、`.env.example`、AGENTS 开发约定已迁移到 `cyclops`。
* 新增 ASGI route surface、上传、SSE、非法 JSON、lifespan 资源释放测试；更新 CLI、配置、LLM、DB、并发保护相关测试。
* 新增 `.trellis/spec/backend/cyclops-asgi-admin-contracts.md`，记录 ASGI route adapter、CLI、静态资源、SSE、错误映射和 lifespan 资源释放契约。

## 验证记录

* `python -m pytest`（在现有本地 conda 环境中执行）：303 passed。
* `python -m ruff check .`（在现有本地 conda 环境中执行）：All checks passed。
* `npx --yes pnpm@10.10.0 --dir web test`：25 passed。
* `npx --yes pnpm@10.10.0 --dir web lint`：通过。
* `npx --yes pnpm@10.10.0 --dir web build`：通过；Vite 提示当前主 chunk 超过 500 kB，为体积警告非构建失败。
* `python -m cyclops check-config`（在现有本地 conda 环境中执行）：config ok。
* `python -m cyclops.cli check-config`（在现有本地 conda 环境中执行）：config ok。
* `git diff --check`：通过，无 whitespace 错误。
* 包名卫生测试：`tests/test_repository_hygiene.py` 确认运行/交付面不保留旧包目录、旧入口名或旧项目名。
