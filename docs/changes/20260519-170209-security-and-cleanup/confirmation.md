# 用户确认记录

## 2026-05-19 17:02:09

- 用户确认本次范围限定为"安全 + 小改动"，不做架构重构（db.py / admin_server.py 拆分留下一阶段）。
- 用户确认 4 项口径：
  - 非 loopback host 的"明确同意" env 名：`ALLOW_REMOTE_ADMIN=1`。
  - 请求体积默认限额：JSON 10MB / 上传 200MB；两者通过 `Settings` 暴露，可被 env 覆盖。
  - 500 类错误响应脱敏：返回固定 `{"error": "internal error"}`；业务异常仍回原文案。
  - 新增 `logging.getLogger(__name__)` 风格写 warning；不动现有 `print` 调用。
- 计划文档：`docs/changes/20260519-170209-security-and-cleanup/update-plan.md`。

## 本阶段确认口径

- 优先做 host 守门、请求体限额、500 脱敏、`safe_upload_name` 兜底、retrieval/chunking 日志补齐 6 项。
- 不动 `settings_snapshot` 返回内容；不动数据库 schema；不动前端密钥 reveal UX。
- `_clean_*` "重复"项经核对实际为不同类型转换，本次不做。
- review 中 `list_import_files` 的 SQL 拼接告警经核对为误报，不做。

## 完成记录

按 TDD 顺序实现 6 项加固：

### config.py
- 新增 `admin_max_json_bytes`（默认 10 MB）和 `admin_max_request_bytes`（默认 200 MB）两个字段。
- `SETTINGS_ENV_FIELDS` 增加对应 env 映射：`ADMIN_MAX_JSON_BYTES` / `ADMIN_MAX_REQUEST_BYTES`。
- `from_env` 使用 `_integer_env` 解析，env 未设置时回退到默认值。

### admin_server.py
- 新增 `AdminPayloadTooLargeError` 异常类型，单独走 413 状态码。
- 新增模块级 `logger = logging.getLogger(__name__)`、`LOOPBACK_HOSTS`、`REMOTE_ADMIN_ENV` 常量。
- 新增 4 个纯函数 helper（全部带中文 docstring）：
  - `ensure_loopback_or_explicit_opt_in(host, env)`：非 loopback host 必须显式 `ALLOW_REMOTE_ADMIN=1`，否则启动失败；同意时 stderr 打 warning。
  - `ensure_request_size(content_length, max_bytes, kind)`：超限抛 `AdminPayloadTooLargeError`，不读 body。
  - `classify_error_response(exc)`：500 类异常脱敏为 `{"error": "internal error"}`，业务异常保留原文案。
  - `ensure_upload_path_within(upload_dir, candidate)`：resolve 后必须落在 upload_dir 内，覆盖 symlink 攻击。
- 修改 `safe_upload_name`：`.` / `..` / 空基名直接返回安全占位 `upload`。
- 修改 `read_json` / `read_multipart_file`（AdminHandler 内）：read body 之前调用 `ensure_request_size`。
- 修改 `send_error_json`：使用 `classify_error_response`；500 类异常写完整 traceback 到日志。
- 修改 SSE error 事件：脱敏后才发给前端，500 类异常同步打 warning。
- 修改 `run_admin_server`：启动前调用 `ensure_loopback_or_explicit_opt_in(host, os.environ)`。
- 修改 `_create_import_file` 上传保存点：`write_bytes` 之前调用 `ensure_upload_path_within`。
- 新增 imports：`logging`、`os`、`sys`、`traceback`、`Mapping`。

### retrieval.py
- 新增模块级 `logger = logging.getLogger(__name__)`。
- `_analyze_query_with_chat` 的 `except Exception` 分支补 `logger.warning(..., exc_info=True)`，避免静默吞掉 Chat 失败。

### chunking.py
- 新增模块级 `logger = logging.getLogger(__name__)`。
- `num_tokens_from_string` 拆分 `except ImportError`（静默回退，预期场景）和 `except Exception`（打 warning，真实 bug 不被吞掉）。

### 测试
- 新建 `tests/test_admin_security.py`，14 个测试覆盖 host 守门、请求体限额、异常脱敏、`safe_upload_name` 兜底、`ensure_upload_path_within` symlink 防护。
- `tests/test_config.py` 追加 2 个测试覆盖新限额字段的默认值与 env 覆盖。
- `tests/test_chunking.py` 追加 2 个测试覆盖 ImportError 静默 vs 其它异常打 warning。
- `tests/test_retrieval.py` 追加 1 个测试锁定 Chat 失败时打 warning 且仍返回 None。

### 计划之外的小决策
- 实现期间发现 Edit 工具对 `\\u4e00` 这种 Python 源码字面 escape 的 swap 不稳，多次重试都不匹配；改用一次性 Python 脚本完成 helpers 注入；脚本完成后已删除（不入仓）。

## 验证记录

- 红灯验证：实现前跑 `pytest tests/test_admin_security.py tests/test_config.py::test_settings_from_env_uses_default_admin_request_limits tests/test_config.py::test_settings_from_env_parses_admin_request_limits_from_env tests/test_chunking.py::test_num_tokens_from_string_warns_on_unexpected_tiktoken_failure tests/test_retrieval.py::test_analyze_query_with_chat_logs_warning_when_chat_fails -q`：admin_security 在 import 阶段 collect 失败（缺符号），其它 4 个失败（缺字段 / 缺 warning），符合预期。
- 绿灯验证：`source /home/adam/miniconda3/etc/profile.d/conda.sh && conda run -n customer-service-agent python -m pytest -q`：`216 passed`（197 → +19 新增）。
- 全量 lint：`source /home/adam/miniconda3/etc/profile.d/conda.sh && conda run -n customer-service-agent python -m ruff check .`：`All checks passed!`
- 配置检查：`source /home/adam/miniconda3/etc/profile.d/conda.sh && conda run -n customer-service-agent python -m customer_service_agent.cli check-config`：`config ok`
- 语法验证：`source /home/adam/miniconda3/etc/profile.d/conda.sh && conda run -n customer-service-agent python -m py_compile customer_service_agent/admin_server.py customer_service_agent/config.py customer_service_agent/chunking.py customer_service_agent/retrieval.py`：通过。
- diff 空白检查：`git diff --check`：通过。

## 风险与未做事项

- **未做 admin API 鉴权**：本次只加 host 守门 + 请求体限额 + 异常脱敏 + 上传路径校验。如果后续真要把后台暴露到 LAN/公网，必须在 `ALLOW_REMOTE_ADMIN=1` 之外再补 Bearer token 或 Basic auth；当前 env 只是让用户"明确承担风险"，不是真鉴权。
- **`settings_snapshot` 仍明文返回密钥**：前端密钥 reveal 眼睛图标依赖这个行为；未来如要做"默认 mask + 显式 reveal endpoint"是更大的 UX 改动，留下一阶段。
- **db.py / admin_server.py 拆分未做**：架构重构留下一阶段。
- **`ensure_upload_path_within` 只覆盖了主上传路径**：MinerU asset 解压路径（`asset_output_dir=Path(self.settings.upload_dir) / "mineru-assets"`）由 `document_parser.py` 内部处理，本次没有动它；如要彻底覆盖需要在解压点也加 resolve 校验，列为后续待办。
- **logger 未配置 handler**：当前依赖 Python root logger 默认行为；要看到 warning/error 需要调用方（CLI / pytest）设置 `logging.basicConfig(level=...)`。pytest 用 `caplog` 直接抓取，不依赖 handler。生产 CLI 后续可在 `cli.py` 顶部加一次 `basicConfig`。
