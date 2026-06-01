# 用户确认记录

## 2026-05-25 12:28:48

### 范围确认

- 三件事一批做完：
  - **A 批 UX**：文档抽屉重新打开自动恢复轮询 + 主界面文档列表加无文字轻量进度条
  - **B 批 资产闭环**：MinerU 图片 / 表格图 / 公式图 / table HTML 端到端展示在切片预览 + 切片可点击查看 PDF 原页

### 4 项设计口径

- **切片预览容器**：`<pre>` 改为 `<div>`（可嵌 `<img>` / `<table>`）
- **PDF 原页预览**：用浏览器内置 PDF.js，`<iframe src="...#page=N">`，不引前端库
- **table XSS 防护**：手写最小 sanitize（过滤 `<script>` / `<iframe>` / `<style>` / `on*` 属性），不引 DOMPurify
- **资产 URL**：`/api/import/files/<file_id>/assets/<path>`（和现有 `/chunks` `/download` 一致）

### 已存在口径回顾

- 不动 MinerU 解析层、不动 DB schema、零新前端依赖
- 资产文件已落盘 `data/uploads/mineru-assets/<safe(file_id)>/...`，路由复用 `ensure_upload_path_within` 防 path traversal
- `list_import_chunks` 已 `SELECT *` 返回 `source_blocks` JSONB，前端直接读即可

### 计划文档
- `docs/changes/20260525-122848-document-ui-and-assets/update-plan.md`

## 完成记录（2026-05-25）

### 落地范围

**A 批（UX 闭环）**
- `openDocumentDrawer` 重新打开抽屉时，按 `parse_progress.state ∈ {running, processing, parsing, waiting-for-parse, pending}` 自动恢复 `pollDocumentParseStatus`；不动 `closeDocumentDrawer`（关抽屉停轮询合理，云端 MinerU 任务不受影响）
- `renderDocumentRows` 行内加 `documentRowProgressBar`：状态文字下方一条 2px 蓝色细线，按 `extracted_pages/total_pages` 算 percent，无页数时给 8% 占位

**B 批（资产闭环）**
- 后端：`AdminApp.get_import_asset(file_id, asset_relpath)` + 路由 `GET /api/import/files/<id>/assets/<path>`，`ensure_upload_path_within` 防 traversal，复用现有 `send_static`
- 前端：`<pre id="chunkPreviewText">` → `<div id="chunkPreviewBody">`，`renderChunkBodyHtml` 按 `source_blocks` 中每个 block 的 `block_type` 派发渲染 image/figure/table/equation/text
- 表格 sanitize：`DOMParser` + 删 `<script>/<iframe>/<style>/<link>/<object>/<embed>` + 去 `on*` 和 `href/src/formaction` 属性
- PDF 预览模态框：`<iframe src="/api/import/files/<id>/download#page=N">` 利用浏览器内置 PDF.js，零前端依赖
- 切片资产 URL：`assetUrl(fileId, relpath)` 按段 encodeURIComponent，避免中文/空格破坏路径

### 测试与校验
- `tests/test_admin_server.py` 新增 4 条 asset 用例（happy / traversal / missing file / unknown file_id）
- `tests/test_admin_table_layout.py` 同步：`chunkPreviewText` → `chunkPreviewBody` 断言
- `pytest -q` → **261 passed**（原 257 + 新 4）
- `ruff check` → clean
- `check-config` → ok
- `node --check admin.js` → 通过

### 未亲测的部分（建议手动验证）
- 实际 `source_blocks` JSONB 字段里 evidence 的具体结构：按 `_mineru_asset_paths` 的 `img_path` / `table_img_path` / `equation_img_path` 反推；如果实际 key 不同，需要在浏览器 devtools 抓一份 `/api/import/files/<id>/chunks` 返回对齐
- table HTML 字段名：渲染按 `block.html` → `block.evidence.table_html` → `tableHtmlFromText(block.text)` 三级 fallback，但未在真实切片上验证
- PDF 预览：依赖浏览器内置 PDF.js 渲染 `#page=N` 锚点，Chrome/Firefox/Edge 都支持，但 Safari/移动浏览器可能不工作

### 风险与后续
- table 的 minimal sanitize 不防御所有 XSS 向量，但 MinerU 是受信来源，cell 文本不经用户输入
- 如果 list_import_chunks 接口里 `source_blocks` 是 JSON 字符串而不是已解析的 list，前端 `Array.isArray(chunk.source_blocks)` 会失败 fall back 到纯文本——需要确认 psycopg `dict_row` 对 JSONB 的反序列化行为（应该自动 parse）
- PDF 预览只支持单页跳转，不做范围（page_start..page_end）；MinerU 切片大多在单页内

## 2026-05-25 修订（用户反馈追加）

### 用户反馈

1. **切片富渲染放错位置**：上一轮放在 FAQ 管理（`chunkPreviewBody`），用户原意是文档管理抽屉里的"切片查看"（`documentChunkContent`）需要富内容
2. **切块超 9 个无滚动**：左侧切块索引超出容器后无法滚动到后续切块
3. **切块内容无法滚动**：单切片内容超长时不可滚
4. **缺文档/切片级禁用**：要求文件级和切片级两种粒度的禁用开关，禁用项立即从 RAG 检索排除；删除文档同步清空向量

### 落地范围

**搬迁富渲染**
- `renderChunkPreview` 回退为纯文本，FAQ 那边的 `viewChunkPdfButton` 按钮 + 绑定移除
- `renderDocumentChunkContent` 改成 toolbar + 默认富预览（image/figure/table/equation 派发）+ 编辑切换模式
- 新增 `state.documentChunkEditMode`，切换切片或重开抽屉时重置

**滚动修复**
- `.document-chunk-reader` 高度提到 520px
- `.document-chunk-index` 加 `overflow-y: auto + min-height: 0`，超出可滚
- `.document-chunk-content` 去掉 overflow:hidden，内部 `.document-chunk-rich` 用 `flex:1 + overflow-y:auto` 承载富内容滚动
- `.document-chunk-toolbar` / `.document-chunk-rich` / `.document-chunk-editor` 全套新样式

**禁用开关（文件级 + 切片级）**
- `sql/001_init.sql`：import_files 和 import_chunks 各加 `is_disabled BOOLEAN NOT NULL DEFAULT false`
- DB 层：`set_import_file_disabled` / `set_import_chunk_disabled`；`delete_import_file` 在事务里先 `DELETE FROM knowledge_chunks WHERE source_type='document' AND source_id=...`
- 检索 SQL（向量 / 文本 / parent context 三处）：LEFT JOIN import_files + import_chunks，`COALESCE(imp.is_disabled, false) = false AND COALESCE(ic.is_disabled, false) = false` 过滤；FAQ 来源 COALESCE→false 不受影响
- admin_server：`set_import_file_disabled(file_id, payload)` / `set_import_chunk_disabled(chunk_id, payload)`，要求 payload 含 `is_disabled` boolean
- 路由：`POST /api/import/files/<id>/disabled`、`POST /api/import/chunks/<id>/disabled`
- 前端：列表行加"禁用 / 启用" toggle + 行级 disabled-on 视觉；抽屉 action-row 加 `toggleDocumentDisabledButton`；切片 toolbar 加 `toggleDocumentChunkDisabledButton`；切块索引按钮加 `.disabled` 样式（线删除 + 灰字）

### 测试与校验
- 新增 9 条单元测试（admin app 4 条禁用 + DB SQL 4 条断言 + schema 1 条）
- `pytest -q` → **270 passed**（261 + 9）
- `ruff check` → clean
- `check-config` → ok
- `node --check admin.js` → 通过

### 未亲测的部分（建议手动验证）
- 真实 PDF / 多切片场景下：切块超 9 个的滚动手感、富预览与编辑切换的视觉过渡
- 禁用后 RAG 检索的过滤效果：跑一次 assistant chat 或 retrieval 工作台对照确认
- 删除文档前已经生成 embedding 的情况：删完去库里 `SELECT count(*) FROM knowledge_chunks WHERE source_type='document' AND source_id=...` 应为 0

### 设计取舍记录
- 禁用走"软开关 + 检索过滤"，不删 embedding —— 启用立即生效，避免重算成本
- FAQ 那边的富渲染回退到纯文本，避免审核流程被资产噪声干扰；富内容只保留在文档管理
- 编辑模式与富预览二选一显示，避免 textarea 滚动 + 富预览滚动嵌套带来的体验冲突
