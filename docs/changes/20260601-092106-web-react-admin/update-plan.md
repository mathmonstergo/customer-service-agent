# React 管理后台迁移 + 基线归档计划（回顾式）

> 本文件是**回顾式补档**：相关代码已在 2026-05-26 ~ 05-28 期间陆续完成并自测通过，但当时未按 AGENTS.md 在动工前建立 `docs/changes/` 记录。2026-06-01 经用户确认，把这批未提交工作整理成一次 checkpoint 提交建立干净基线，本目录补齐该批改动的计划与确认记录。

## 背景结论

- 老的管理后台是手写静态页（`customer_service_agent/static/admin.{html,css,js}`），随着 FAQ / 文档 / 问答 / 设置功能增多，单文件 JS 维护成本变高，富内容（MinerU 图片/表格/公式、流式问答、流程调试）难以继续在原生 DOM 拼接里扩展。
- 决定把后台整体重写为 React SPA，保留"工具型、信息密集、显式状态"的定位（见 AGENTS.md UI 规则），不做营销式页面。
- 重写过程中顺带补齐了几项一直缺的后端能力（见下"捆绑改动"），它们与新前端的页面是配套关系。

## 修改目标

1. 用 React + TypeScript + Vite 重建管理后台,覆盖文档管理 / FAQ 管理 / 智能问答三大页,信息层级和操作流程对齐既有功能。
2. 后端 `admin_server.py` 从"托管手写静态页"改为"托管 Vite 构建产物 SPA + 提供配套 JSON API"。
3. 把此前 `20260525-122848-document-ui-and-assets` 计划中的 MinerU 资产富内容展示需求,在 React 版里落地(老 admin.js 已删,该计划未在原载体实现)。
4. 建立一次干净的 checkpoint 基线,后续开发在其上进行。

## 影响范围

### 前端（新增 `web/`，未跟踪 → 本次纳入）

- 技术栈:React 19、Vite 8、TypeScript、Tailwind v4、Radix UI、TanStack Query、zustand、react-router(HashRouter)、framer-motion、react-markdown + remark-gfm、sonner、cmdk、react-dropzone。
- 入口:`web/src/main.tsx`(真实入口,接 `AppShell` + 三页路由 + QueryClient);`web/src/App.tsx` 是 Vite 模板残留死文件(无人 import),连同 `App.css`、`assets/{react,vite}.svg`、`assets/hero.png` 均为模板残留,后续可清理。
- 页面:
  - `pages/documents/`：文档列表、上传弹窗、文档抽屉、切片浏览(`chunk-browser`)。
  - `pages/faqs/`：FAQ 列表、抽屉、统计条。
  - `pages/assistant/`：会话列表、流式消息流、输入区、流程调试抽屉、供应商抽屉(`provider-drawer`)、`use-chat-stream`。
- 公共:`components/layout/`(app-shell/sidebar/topbar)、`components/shared/`(命令面板、文件上传、`source-block-preview`、标签输入)、`components/ui/`(原子件)、`api/`(client/hooks/schemas)、`lib/`(sse、sse-assistant、`sanitize`、labels、motion、cn)、`store/`(assistant/ui)。
- 构建:`vite.config.ts` `base: '/static/dist/'`,`outDir: '../customer_service_agent/static/dist'`。

### 构建产物（`customer_service_agent/static/dist/`，本次纳入）

- 经用户确认**提交构建产物**:内部工具 + 简历展示场景,保证 `clone → 跑 admin` 即有界面,部署链路无 node 构建步骤。
- 风险口径:源码改动后若忘记 `pnpm build`,committed dist 会与源码不一致 —— 后续若加部署构建步骤可改为 gitignore。

### 后端 `admin_server.py`（已跟踪，本次改动）

- SPA 托管:`static_path()` —— `/` 返回 `static/dist/index.html`;`/static/dist/<子路径>` 限定在 `static/dist/` 内返回 Vite 产物。
- 配套 JSON API（与上述页面一一对应）:
  - 供应商探测:`probe_chat_provider` / `list_chat_provider_models` / `_chat_client_for_payload` → `/api/assistant/probe`、`/api/assistant/models`。
  - MinerU 资产:`get_import_asset` → `/api/import/files/<file_id>/assets/<relpath>`,用既有 path-traversal 防护,落在 `data/uploads/mineru-assets/` 内。
  - 启用/停用:`set_import_file_disabled` / `set_import_chunk_disabled` → `/api/import/files/<id>/disabled`、`/api/import/chunks/<id>/disabled`。
  - 逐切片问题生成 / 向量:`generate_import_file_questions` / `embed_import_chunk` → `/api/import/files/<id>/generate-questions`、`/api/import/chunks/<id>/embed`。

## 捆绑改动（与前端配套，一并纳入本次 checkpoint）

- **DB schema**（`sql/001_init.sql`，全部 `ADD COLUMN IF NOT EXISTS` 向后兼容）:
  - `import_files.is_disabled`
  - `import_chunks`：`is_disabled` + `questions` / `questions_status` / `questions_model` / `questions_updated_at` / `questions_error`
- **`db/imports.py`**：`set_import_file_disabled` / `set_import_chunk_disabled` / `set_import_chunk_questions`。
- **`import_questions.py`**（新增）：从切片生成候选问题,默认进待审核态,不直接进可检索。
- **`document_parser.py`**：`_mineru_table_html` —— 从 MinerU 结果抽取表格 HTML。
- **`chunking.py`**：`_has_content` —— 过滤空块。
- **MCP server**（`mcp_server.py` + `rag_tool.stream_answer` + cli `mcp` 子命令 + 依赖 `mcp>=1.6,<2.0`）：已有独立文档 `docs/changes/20260522-025224-mcp-server/`,本次仅随基线一并提交其 `confirmation.md`。

## 删除

- `customer_service_agent/static/admin.{html,css,js}`：被 React SPA 取代。
- `tests/test_admin_table_layout.py`：针对老静态表格布局,载体已删。

## 验证

- `python -m pytest` → **223 passed**。
- `python -m ruff check customer_service_agent tests` → All checks passed。
- 待提交内容安全审计:`.env` / `system_prompt.txt` / 上传原件 / 微信 token / `*.jsonl,csv` 等均被 `.gitignore` 拦截;`web/` 源码与新增 py 文件无硬编码密钥;`static/dist` bundle 用 `.env` 真实敏感值反查均 0 命中。

## 暂不包含（后续可做）

- 清理 `App.tsx` 等 Vite 模板残留死文件。
- 重新 `pnpm build` 校验 committed dist 与当前源码一致性(本次按"归档当前可跑状态"提交,未重建)。
- 前端 README 用项目说明替换 Vite 模板默认内容。
- 部署文档补充前端构建/产物说明。
