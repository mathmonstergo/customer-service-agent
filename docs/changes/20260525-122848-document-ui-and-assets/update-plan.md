# 文档解析 UX 修复 + 资产闭环计划

## 背景结论

用户反馈两条核心问题：
1. **文档解析抽屉关闭后再次打开，进度不再更新**——前端 polling 被停了不会自动恢复（云端 MinerU 任务实际不停）
2. **切片只显示文本，丢图丢表格**——MinerU 抓的 image / table_img / equation_img / table_body HTML 都已经解析、落盘到 `data/uploads/mineru-assets/<file_id>/...`，但前端 `<pre>` 文本预览根本没显示，HTTP 也没暴露资产路径

附加诉求：
- 主界面文档列表里在解析状态文字下加一条**无文字轻量进度条**
- 切片预览支持 image / table_img / equation_img 显示
- table 用 MinerU 返回的 HTML 原生渲染
- PDF 切片可点击查看 PDF 原页（页码已经在 page_start/page_end）

## 修改目标

把 KB 的"上传→解析→切片"闭环从"只有文字"做到"完整富内容"，并且 UX 不再让用户怀疑任务卡死。

## 影响范围

### A 批：UX 闭环

- `customer_service_agent/static/admin.js`
  - `selectDocumentFile`：选中文件后判断 `parse_progress.state` 是 `running` / `processing` / `parsing`，自动启动 `pollDocumentParseStatus`
  - `renderDocumentRow`（或 list 渲染处）：状态文字下加 `<div class="document-row-progress">` 子元素
- `customer_service_agent/static/admin.html`：文档列表行结构加进度条容器（如果 list 是 JS 拼接的 innerHTML，只改 JS）
- `customer_service_agent/static/admin.css`：进度条样式（细线，蓝色）

### B 批：资产路由 + 切片富内容

#### 后端
- `customer_service_agent/admin_server.py`
  - 新增 `AdminApp.get_import_asset(file_id, asset_relative_path)`：解析为 `data/uploads/mineru-assets/<safe(file_id)>/<asset_relative_path>`，用 `ensure_upload_path_within` 防 path traversal
  - 新增路由 `GET /api/import/files/<file_id>/assets/<...>`：调上面方法，调 `send_download`
  - PDF 原页：复用现有 `/api/import/files/<file_id>/download` 接口；前端用 `<iframe src="...#page=N">`
  - `list_import_chunks` / `get_import_chunk` 接口：当前已 `SELECT *` 返回所有列含 `source_blocks` JSONB；只需要前端读 source_blocks 即可，不动后端

#### 前端
- `customer_service_agent/static/admin.html`
  - `<pre id="chunkPreviewText">` 改为 `<div id="chunkPreviewBody">` 容器（保留 id 兼容，或新增 id）
- `customer_service_agent/static/admin.js`
  - `renderChunkPreview`：
    - 解析 chunk.source_blocks（JSON）
    - 对每个 block 按 block_type 渲染：
      - `text`：`<p>{text}</p>`
      - `image` / `figure`：`<figure><img src="/api/import/files/<file_id>/assets/{img_path}" /></figure>`
      - `table`：优先用 block.html 渲染；缺失时降级到 `<img src=".../table_img_path">`
      - `equation`：`<img src=".../equation_img_path">`（公式截图）
    - 如果 source_blocks 为空，退回旧行为渲染纯文本
  - 加 "查看 PDF 原页" 按钮：仅当 chunk.page_start 存在且 file.parser == "mineru" 时显示
  - 点击 → 打开模态框 `<iframe src="/api/import/files/<file_id>/download#page={page_start}">`，关闭时移除
- `customer_service_agent/static/admin.css`
  - chunk 预览图样式（max-width: 100%, 图片间距等）
  - PDF 模态框

### 测试

- `tests/test_admin_server.py`
  - `test_admin_app_get_import_asset_serves_file_within_mineru_assets`
  - `test_admin_app_get_import_asset_rejects_path_traversal`
  - `test_admin_app_get_import_asset_404_when_missing`
- `tests/test_static_admin.py`（如果有相关测试文件；没有就在 admin.js 测试不容易做，跳过——靠手动 + 浏览器测）

## 具体步骤（TDD 顺序）

### A 批
1. 写测试：暂无可测（纯 UI 行为）；手动验证
2. 改 admin.js：selectDocumentFile 自动恢复轮询
3. 改 admin.js + html + css：列表行进度条

### B 批
4. 写测试：admin_server get_import_asset 三种 case（happy / traversal / missing）
5. 实现 AdminApp.get_import_asset + 路由
6. 改 admin.js renderChunkPreview：渲染 source_blocks 富内容
7. 改 admin.html：把 `<pre>` 换成 div 容器
8. 加 PDF 原页查看模态框
9. 跑全量 pytest + ruff + check-config

## 设计要点

### Asset 路由安全

- 路径形如 `/api/import/files/imp_xxx/assets/images/img_001.png`
- 后端解析为 `{upload_dir}/mineru-assets/{safe(file_id)}/images/img_001.png`
- 用 `ensure_upload_path_within(upload_dir / "mineru-assets", candidate)` 防 `../` 逃逸
- file_id 用 `safe_upload_name` 清洗（其实是 imp_ 前缀生成的 ID，按 char-set 限制即可安全）
- Content-Type 走 `mimetypes.guess_type`，常见的 png/jpg/svg 都自动正确
- 失败：`AdminNotFoundError` → 404

### source_blocks 在前端渲染

后端 `clean_block_list` 输出形如：
```json
[
  {
    "block_type": "image",
    "text": "图片描述",
    "evidence": {
      "asset_paths": {"img_path": "images/abc.png"}
    }
  }
]
```

前端逐 block 渲染，asset 路径前缀 `/api/import/files/{file_id}/assets/`。

### Table 渲染优先级

1. 如果 block.evidence 或 block 本身有 `table_html` / `html_body` 字段，直接 innerHTML（**注意：要做 XSS sanitize**——但 MinerU 返回的是 cell 文字 + `<table>/<tr>/<td>` 标签，没有 script，所以风险可控；保险起见前端用 DOMParser 过滤掉 script/iframe/style/on* 属性）
2. 否则 fallback 到 table_img_path 图片
3. 都没有就显示 block.text

### PDF 原页查看

- 直接 `<iframe src="/api/import/files/{file_id}/download#page={page_start}">`，浏览器自带 PDF.js
- 不引新依赖；Firefox 和 Chrome 都支持 #page= 锚点
- 模态框关闭时 src 置空，避免 iframe 占用资源

### 进度条样式

```css
.document-row-progress {
  height: 2px;
  background: #e3e6ed;
  border-radius: 1px;
  margin-top: 4px;
  overflow: hidden;
}
.document-row-progress-bar {
  height: 100%;
  background: #3b82f6;
  transition: width 240ms ease;
}
```

只有 `parse_progress.state` 在 running/processing 时显示；done/failed 隐藏。

### 自动恢复轮询

```js
function selectDocumentFile(file) {
  // ... 原有逻辑
  state.currentDocumentFile = file;
  renderDocumentDrawer(file);
  const state_ = (file.parse_progress?.state || file.status || "").toLowerCase();
  if (["running", "processing", "parsing", "waiting-for-parse"].includes(state_)) {
    pollDocumentParseStatus(file.id);
  }
}
```

不动 `closeDocumentDrawer` —— 关抽屉停轮询合理。

## 验证命令

- `source /home/adam/miniconda3/etc/profile.d/conda.sh && conda run -n customer-service-agent python -m pytest -q`
- `source /home/adam/miniconda3/etc/profile.d/conda.sh && conda run -n customer-service-agent python -m ruff check customer_service_agent tests`
- `source /home/adam/miniconda3/etc/profile.d/conda.sh && conda run -n customer-service-agent python -m customer_service_agent.cli check-config`
- `node --check customer_service_agent/static/admin.js`
- 手动：用现有 imp_e1f3b35fffa6 的资产目录测试 asset 路由 + 切片预览

## 需要用户确认的问题

1. **`<pre>` 改成 `<div>` 是否破坏现有切片只读预览的格式**？现有切片编辑面板是不是同时显示 `<pre>` 和 textarea？我看了一遍只看到 `chunkPreviewText` 用于只读展示，没有冲突。**建议直接改**。
2. **PDF 原页查看用浏览器内置 PDF.js 还是单独引 PDF.js 库**？建议**用浏览器内置**（不引新依赖，#page= 锚点跳页），代价是非 Chrome/Firefox/Edge 用户体验降级。
3. **table HTML 是否做 XSS sanitize**？建议**做最小 sanitize**（过滤 `<script>` `<iframe>` `<style>` `on*` 属性），不引 DOMPurify 等大依赖。
4. **资产 URL 前缀**：`/api/import/files/<file_id>/assets/<path>` 还是 `/api/import/assets/<file_id>/<path>`？建议**前者**——和现有 `/download` `/chunks` `/parse-status` 一致都是 `/api/import/files/<id>/...`。

## 暂不包含

- 不动 MinerU 解析流程
- 不动 chunk DB schema
- 不引前端 chart / PDF 库
- 不做切片编辑器富内容（只动只读预览）
- 不做图片缩放 / 高清查看（用浏览器原生缩放）
- 不做 OCR 文字提取覆盖（保持 MinerU 默认）
