# 文档 embedding 状态与切片编辑计划

## 修改目标

文档管理页面需要明确展示文档切片 embedding 状态，并允许用户在切片查看框内直接编辑切片原文、保存修改。保存后如果该切片已经生成过向量，需要把对应统一知识单元标记为 `stale`，提醒用户重新生成 embedding。

## 影响范围

- 数据库：新增文档级 embedding 状态统计；新增切片原文保存和 `knowledge_chunks` stale 标记逻辑。
- 管理 API：文档列表返回 embedding 摘要；新增保存切片内容接口。
- 管理 UI：文档列表、详情抽屉展示 embedding 状态；切片查看框改为可编辑 textarea，并增加保存按钮。
- 测试：覆盖数据库 SQL、后端状态/保存逻辑、静态 UI 结构和前端调用路径。

## 具体步骤

1. 写失败测试，锁定文档 embedding 摘要字段和切片保存行为。
2. 实现 `Database.list_import_file_embedding_summaries` 和 `Database.update_import_chunk_text`。
3. 让 `Database.list_import_files` 为每个文档附加 `embedding_summary`。
4. 新增 `AdminApp.update_import_chunk_text` 和 `/api/import/chunks/{chunk_id}` 保存接口。
5. 更新文档管理 UI：列表和抽屉展示向量状态；切片正文改成可编辑 textarea；保存后刷新当前切片和文件状态。
6. 用 conda 跑聚焦测试、全量测试、ruff、配置检查，并做浏览器状态检查。

## 用户确认

- 用户确认希望先实现。
- README 当前由用户自行修改，本次不触碰 README。

## 完成记录

- 文档列表新增向量状态列，文档详情抽屉新增向量状态摘要。
- 切片查看框改为仅展示和编辑切片原文，保存后刷新当前切片内容。
- 保存切片时同步更新 `import_chunks.source_text`；如该切片已有统一知识单元，则把对应 `knowledge_chunks.embedding_status` 标记为 `stale`，提示重新生成 embedding。
- 新增 `/api/import/chunks/{chunk_id}` 保存接口，空内容会被拒绝。

## 验证记录

- `conda run -n customer-service-agent python -m pytest -q`：160 passed。
- `conda run -n customer-service-agent python -m ruff check .`：All checks passed。
- `conda run -n customer-service-agent python -m customer_service_agent.cli check-config`：config ok。
- `node --check customer_service_agent/static/admin.js`：通过。
- Playwright 静态页面检查：文档行显示 `已完成 1/1`；编辑并保存切片后，textarea 保留新原文，文档向量状态更新为 `需重新生成 0/1`。
