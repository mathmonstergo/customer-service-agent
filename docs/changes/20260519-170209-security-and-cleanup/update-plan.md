# 安全加固与代码质量小项

## 背景结论

本次基于全项目 review 发现的问题做最小化加固，**不动架构**（db.py / admin_server.py 拆分留作下一阶段），只解决：

1. 本地后台没有 host 守门，`--host 0.0.0.0` 可以无警告暴露到局域网。
2. `read_json` / `read_multipart_file` 按 Content-Length 一次读到内存，无上限。
3. `send_error_json` 对 500 错误直接回 `str(exc)`，会泄漏 SQL / 文件路径 / 内部 URL。
4. `safe_upload_name` 只做字符清理，未阻止 `.` / `..` 基名，缺少 resolve 后的边界校验。
5. `retrieval.py:330` Chat 调用回退完全静默，调试困难。
6. `chunking.py:36-37` tiktoken import 失败时不区分"没装"和"真有 bug"。

review 中提到的 `_clean_*` "重复"经核对实际是不同类型转换（list / dict / block_list / int），不是真冗余，**本次不动**。

## 修改目标

围绕"localhost 内部工具"这一现有定位，给最容易踩雷的几条路径加守门和限额，同时把两处静默吞异常改成可观测。
不引入新依赖、不破坏现有 UI（密钥 reveal 眼睛图标继续工作）、不动数据库 schema、不动检索/RAG 行为。

## 影响范围

- `customer_service_agent/admin_server.py`
  - 新增 host 守门函数 + 接入 `run_admin_server`。
  - `read_json` / `read_multipart_file` 限制请求体大小。
  - `send_error_json` 区分用户态异常和内部异常，500 类返回通用文案，详细写日志。
  - `safe_upload_name` 增加 `.` / `..` 基名拒绝；上传保存处加 resolve 校验。
- `customer_service_agent/config.py`
  - 新增 `admin_max_request_bytes`（默认 200 MB），允许 env 覆盖。
  - 新增 `admin_max_json_bytes`（默认 10 MB），允许 env 覆盖。
- `customer_service_agent/retrieval.py`
  - `_analyze_query_with_chat` 异常分支接入 `logging.getLogger(__name__).warning(..., exc_info=True)`。
- `customer_service_agent/chunking.py`
  - `num_tokens_from_string` 拆分 `ImportError` 和其它异常，后者打 warning。
- 测试：补充对应失败/边界用例。
- 文档：更新本目录 confirmation.md。

## 具体步骤（TDD 顺序）

1. 写测试锁定 host 守门：默认 loopback 通过；`--host 0.0.0.0` 在没有 `ALLOW_REMOTE_ADMIN=1` 时抛 `RuntimeError`；env 为 1 时通过并打 warning。
2. 写测试锁定 `read_json` / `read_multipart_file` 在 Content-Length 超限时回 413 且不读 body。
3. 写测试锁定 `send_error_json` 在内部异常时返回 `{"error": "internal error"}`，但 `AdminValidationError` / `AdminNotFoundError` 等仍回原文案。
4. 写测试锁定 `safe_upload_name` 对 `.` / `..` 输入返回安全占位（如 `upload`）；写测试锁定 upload 路径 resolve 后必须落在 `upload_dir` 内。
5. 写测试锁定 `chunking.num_tokens_from_string` 在 `ImportError` 下静默回退，在其它异常下走 warning 路径。
6. 写测试锁定 `retrieval._analyze_query_with_chat` 异常时仍返回 `None`（行为不变），并能验证 log 调用次数。
7. 实现 `config.py` 两个新字段 + env 解析。
8. 实现 `admin_server.py` 四处改动。
9. 实现 `retrieval.py` 和 `chunking.py` 两处改动。
10. 跑聚焦测试 → 全量 `pytest` → `ruff` → `check-config`。
11. 填 `confirmation.md`，记录结果和遗留风险。

## 设计要点

### host 守门
- 在 `run_admin_server` 入口前置 `ensure_loopback_or_explicit_opt_in(host)`：
  - host 命中 `{"127.0.0.1", "::1", "localhost"}` 直接通过。
  - 其它值检查 `os.environ.get("ALLOW_REMOTE_ADMIN") == "1"`；命中则 stderr 打 warning 后通过，否则 raise `RuntimeError("non-loopback host requires ALLOW_REMOTE_ADMIN=1 ...")`。
- 守门函数放在 `admin_server.py` 顶层，单独可测。

### 请求体限额
- 在 `read_json` / `read_multipart_file` 顶部先校验 `Content-Length`，超限直接 `raise AdminValidationError(...)`（已映射到 400）或新增 `AdminPayloadTooLargeError` → 413。
- 选 413 更准确，新增异常类型。所有相关 handler 已经通过 `send_error_json` 统一处理，扩展即可。
- 默认值：
  - `admin_max_json_bytes` = 10 MB（FAQ payload 都很小，10 MB 是宽裕值）。
  - `admin_max_request_bytes` = 200 MB（文档上传，与 MinerU 实际可处理量相称）。
- 两个值都从 `Settings` 拿，可通过 env 覆盖。

### 异常脱敏
- `send_error_json` 拿到 `INTERNAL_SERVER_ERROR` 分支时：
  - 走 `traceback.format_exc()` 写到 stderr（沿用 `print(..., flush=True)` 风格，保持轻依赖）。
  - 返回给前端的 body 改成 `{"error": "internal error"}` 固定文案。
- 已识别的业务异常（`AdminValidationError` / `AdminNotFoundError` / `AiSuggestionError` / `ImportCandidateError`）仍回原 message——这些信息对用户操作是必要的（如"文件类型不支持"）。
- SSE 路径 1666 行同样改造：error 事件 payload 不带 raw exc。

### safe_upload_name 守门
- 基名为 `.` / `..` / 空时返回固定 `"upload"`。
- 在 admin_server.py 实际写文件的两处加 `(upload_dir / safe_name).resolve().is_relative_to(upload_dir.resolve())`，不满足直接报 400。

### 日志策略
- `retrieval.py` / `chunking.py` 用 module 级 `logger = logging.getLogger(__name__)`。
- 不在 module load 时 `basicConfig`；由调用方/CLI 决定 handler。

## 预期效果

- 误传 `--host 0.0.0.0` 启动失败并提示需要的 env，杜绝最常见的误暴露。
- 上传/JSON 请求超限直接 413，进程不会被大 body 灌满内存。
- 500 类错误前端拿到统一 message，详细信息只进日志。
- 任意拼接路径基名被守门，落地路径必须在 `upload_dir` 之内。
- 检索意图分类回退路径有日志线索可查。
- tiktoken 真出现 bug 时不会被静默吞掉。

## 需要用户确认的问题

1. **`ALLOW_REMOTE_ADMIN=1` 这个 env 名是否合适**？还是希望换成别的（如 `CSA_ALLOW_REMOTE`）？
2. **限额默认值**：JSON 10 MB / 上传 200 MB 是否合理？是否需要更严格（如 50 MB 上传）？
3. **异常脱敏是否需要保留 exception type 名**？例如返回 `{"error": "internal error", "code": "InternalError"}`，方便前端区分 500 vs 400？还是完全模糊？
4. **日志输出**：当前项目大量用 `print(..., flush=True)`，没有统一 logger 配置。新增 `logging` 用法是否 OK？还是希望沿用 `print` 风格？

## 暂不包含

- 不做 admin API token / Basic auth（属于"暴露到 LAN/公网"才需要的工作量，与本次"localhost 守门"分开）。
- 不拆 `db.py` / `admin_server.py`（架构重构，留下一阶段）。
- 不抽 `ImportService`（架构重构，留下一阶段）。
- 不动 settings_snapshot 返回内容（保留前端 reveal UX）。
- 不动 SQL 拼接（review 中的 SQL "MEDIUM" 经核对实际为误报）。

## 验证命令

- `source /home/adam/miniconda3/etc/profile.d/conda.sh && conda run -n customer-service-agent python -m pytest -q`
- `source /home/adam/miniconda3/etc/profile.d/conda.sh && conda run -n customer-service-agent python -m ruff check .`
- `source /home/adam/miniconda3/etc/profile.d/conda.sh && conda run -n customer-service-agent python -m customer_service_agent.cli check-config`
- `node --check customer_service_agent/static/admin.js`（本次未改前端，留作回归）
