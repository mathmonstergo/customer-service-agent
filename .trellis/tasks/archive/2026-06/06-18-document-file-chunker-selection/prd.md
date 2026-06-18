# 文档导入按文件选择 chunker

## Goal

让文档导入流程支持按文件/解析任务选择 chunker，使上一阶段已经实现的 `naive`、`manual`、`qa`、`table` 后解析能力可以在混合资料导入时被实际使用，同时继续保持 MinerU 作为默认解析 provider，并保持全局 `DOCUMENT_CHUNKER_TYPE` 作为默认回退。

## Requirements

* 导入文件记录需要保存当前使用的 `chunker_type`，允许值为 `naive`、`manual`、`qa`、`table`。
* 上传导入文件时如未指定 chunker，默认使用现有全局配置 `DOCUMENT_CHUNKER_TYPE`。
* 启动解析任务时可以通过 payload 覆盖该文件的 `chunker_type`，并让本次解析使用覆盖后的值。
* MinerU 解析完成后构建切片时必须使用文件记录上的 `chunker_type`，不能只读全局配置。
* 重新解析入口需要接受同样的 `chunker_type` 覆盖能力，保证手动重跑和后台解析行为一致。
* 文档管理 UI 至少需要在文件详情抽屉中展示并允许选择 chunker，点击“开始解析”时提交选择。
* 文件列表或详情中需要能看出当前文件使用的 chunker，方便排查不同切块结果。
* 实现需要继续参考 RAGFlow 的“解析层 + 通用后处理/chunker”思路，不新增简化的自动轻量分流。

## Acceptance Criteria

* [x] `import_files` 数据模型可持久化 `chunker_type`，旧数据有兼容默认值。
* [x] `POST /api/import/files/<id>/parse-jobs` 接受 `chunker_type` 并影响该文件本次解析结果。
* [x] MinerU parse job finish 阶段按文件记录的 `chunker_type` 调用 `build_import_chunks_from_blocks`。
* [x] 文档详情抽屉可选择 `naive`、`manual`、`qa`、`table` 并提交到解析任务。
* [x] 文档列表或详情可展示当前 chunker。
* [x] 后端行为有测试覆盖，至少验证 payload 覆盖和构建切片参数选择。
* [x] 前端构建或类型检查通过；如环境缺失，需要记录原因。

## Definition of Done

* 测试优先补齐后端行为用例，并先观察新增测试失败。
* Python 修改过的新/变更函数具备中文注释或 docstring，说明做什么和关键约束。
* 运行 `python -m pytest`、`python -m ruff check .`、`python -m customer_service_agent.cli check-config`，能运行则记录结果。
* 涉及前端源码时运行项目既有前端构建/检查，并同步静态产物。
* 更新本任务对应的 `docs/changes/20260618-092037-document-file-chunker-selection/` 记录。

## Technical Approach

* 在导入文件数据库层增加 `chunker_type` 字段，并在查询/创建/summary 更新时透出。
* 后端解析入口统一使用一个校验/解析函数处理 chunker 类型，非法值返回请求错误或忽略为默认值，具体按现有 API 错误风格实现。
* `_build_document_import_chunks` 接收显式 `chunker_type`，调用 document parser 已有的 `build_import_chunks_from_blocks(..., chunker_type=...)`。
* UI 在文档详情抽屉内使用紧凑选择控件，不改变当前“上传后进入详情抽屉再解析”的主流程。
* 不做自动识别、LLM 切块路由、RAGFlow 服务接入，也不改变 MinerU provider 的默认地位。

## Decision (ADR-lite)

**Context**: 上一阶段已经让 MinerU 解析结果进入多 chunker 后处理，但只有全局配置会导致同一批混合导入无法按资料类型选择合适策略。

**Decision**: 本阶段先做文件级 `chunker_type` 持久化和解析任务覆盖，让不同资料在同一系统里明确选择 RAGFlow 风格后解析策略。

**Consequences**: 用户需要在解析前做一次明确选择；系统避免引入尚未验证的轻量自动分流。后续可以在这个字段基础上增加推荐值、批量设置或更细的 parser profile。

## Out of Scope

* 自动判断文件应使用哪个 chunker。
* LLM 直接切块或 LLM 路由 chunker。
* 接入完整 RAGFlow 服务或多解析 provider。
* 重做文档管理页面整体布局。
* 改变 FAQ 审核/向量生成的现有分离流程。

## Technical Notes

* 相关后端文件：`customer_service_agent/admin_server.py`、`customer_service_agent/db/imports.py`、`customer_service_agent/document_parser.py`。
* 相关前端文件：`web/src/pages/documents/document-drawer.tsx`、`web/src/pages/documents/document-list.tsx`、`web/src/api/hooks.ts`、`web/src/api/schemas.ts`。
* 既有配置：`DOCUMENT_CHUNKER_TYPE` / `settings.document_chunker_type`。
* 既有 chunker：`naive`、`manual`、`qa`、`table`。
