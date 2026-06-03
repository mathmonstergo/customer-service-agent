# FAQ 禁用归一到 status 三态 + 检索读实时状态

> 交接文档（handoff）。本次会话因网关 524 多次中断、上下文被 `/clear`，本文用于让任意 AI/人无缝接续。
> 起始 HEAD：`1ffe052`（工作树为未提交状态，混有多特性改动，见末尾「遗留风险」）。
> 时间：2026-06-03。

## 1. 目标
把 FAQ 的「禁用」从一个正交布尔列 `is_disabled` 收敛进 `status` 字段，形成**三态**：
- `usable`（可用，唯一会被检索召回）
- `needs_review`（待复核，暂存态，不召回）
- `disabled`（禁用，不召回）

前端「禁用」不再是独立按钮，而是**在状态下拉里选「禁用」再保存**。检索改为**读实时 `status`**，禁用即时生效（无需重嵌/重同步）。

## 2. 设计决策与口径（务必理解，别推翻）
- **只有 FAQ 用 status 表达禁用**；**文档(`import_files`)与切片(`import_chunks`)仍保留 `is_disabled` 布尔列**。两套机制并存是有意为之，不要统一。
- 检索 SQL（`db/knowledge.py` 向量路 `_search_knowledge_*` line ~270、关键词路 line ~312）对 FAQ 用
  `WHERE COALESCE(fq.status, kc.status) = %(status)s`，即**实时 JOIN `faq_documents` 读 `fq.status`**，而非 `knowledge_chunks` 里快照的 `kc.status`。检索固定按 `status='usable'` 取，所以 `needs_review` 与 `disabled` 都不召回。
  - 这是「禁用即时生效」的实现：改 status 即生效，不依赖重新 embedding。
  - 文档/切片仍 `COALESCE(imp.is_disabled,false)=false AND COALESCE(ic.is_disabled,false)=false`。
- 三态文案集中在 `web/src/lib/labels.ts` 的 `faqStatusLabel`：可用/待复核/禁用。禁止页面里写英文 raw 值。

## 3. 改动清单（按文件）
**后端（上一会话已完成，本次已验证）**
- `sql/001_init.sql`：`ALTER TABLE faq_documents DROP COLUMN IF EXISTS is_disabled;` + 把非三态 status 归一为 `needs_review`（幂等，可重复跑）。文档/切片表仍 `ADD COLUMN IF NOT EXISTS is_disabled`。
- `customer_service_agent/admin_server.py`：`VALID_FAQ_STATUSES={"usable","needs_review","disabled"}`；FAQ 路由不再收发 `is_disabled`。
- `customer_service_agent/db/knowledge.py`：检索读实时 `fq.status`（见上）。
- `customer_service_agent/db/imports.py`：仅文档/切片的 `set_import_*_disabled` 保留 `is_disabled`（与 FAQ 无关）。

**前端（本次会话完成）**
- `web/src/pages/faqs/faq-drawer.tsx`：**构建阻塞根因**——曾 `import { useToggleFaqDisabled }`，但该 hook 已在后端去 is_disabled 时从 `hooks.ts` 删除 → `tsc` 编译失败。已修：
  - 删除 `useToggleFaqDisabled` import/调用、`onToggleDisabled`、底部独立「禁用/启用」按钮、未用的 `Power/PowerOff` 图标。
  - 状态下拉由 `usable/needs_review/draft/archived` 改为 `usable/needs_review/disabled`。
  - header `StatusDot` 与标签：`faq.is_disabled` → `faq.status === 'disabled'`。
- `web/src/pages/faqs/faq-list.tsx`：`mapStatus` 去死分支 `draft/archived`，新增 `disabled→muted`。
- `web/src/lib/labels.ts`、`web/src/pages/FaqsPage.tsx`：三态文案/筛选项（上一会话已改，本次确认干净）。
- `web/src/pages/faqs/faq-drawer.tsx`（追加，2026-06-03 验收后）：**编辑态保存成功自动关闭抽屉**——`onSave` 成功分支里非新建走 `onClose()`；新建态仍走 `onCreated(saved.id)` 保持打开以便接着生成 embedding。（`faqDirty` 无人读作关闭拦截，且 `setOpenFaqId` 会顺带归零，故直接关闭安全。）
- `customer_service_agent/static/dist/*`：`npm run build` 产物（hash 每次构建变，以 `index.html` 实际引用为准；构建后记得清 `assets/` 下未被引用的旧产物）。

## 4. 当前进度
- [x] 后端：撤 FAQ 的 is_disabled + status 归一 + 检索读实时 status
- [x] 前端：faq-drawer 三态 + 禁用走状态下拉（去独立按钮）；faq-list mapStatus 归一
- [x] `npm run build` 通过（`tsc -b` 零类型错误，证明全仓无 is_disabled 类型残留）
- [x] 应用迁移：`faq_documents.is_disabled` 已删除；遗留 `product_request`(1) 已归一为 `needs_review`；60 条数据无损
- [x] 后端自检：服务起、`/api/faqs` 返回 status 无 is_disabled、状态筛选计数 usable58/needs_review2/disabled0、禁用闭环（改 disabled→移出 usable→精确恢复）跑通
- [ ] **浏览器验收**（127.0.0.1:8765 硬刷新）：三态下拉、Embedding 按钮(Waypoints 图标)、批量 Embedding —— 待用户/AI 用视觉 MCP 截图确认
- [ ] **git commit** —— 本项目惯例不主动提交，待用户明确指示

## 5. 续作指南（环境 + 命令 + 验收）
**⚠️ 环境坑（必读）**：仓库内 `.venv` 是空的（缺 `dotenv` 等），**不要用**。正确解释器是 conda 环境：
```
~/miniconda3/envs/customer-service-agent/bin/python
```
DB 是本地 Postgres `faq_rag`（连接串在 `.env` 的 `DATABASE_URL`）。`python`/`python3` 不在 PATH。

**常用命令**
```bash
PY=~/miniconda3/envs/customer-service-agent/bin/python
cd ~/projects/customer-service-agent
# 应用/重跑迁移（幂等）
$PY -m customer_service_agent.cli init-db
# 起后台管理服务
$PY -m customer_service_agent.cli admin --port 8765
# 前端构建（产物进 customer_service_agent/static/dist）
cd web && npm run build
# 后端 lint（项目标准：必须干净）
~/miniconda3/envs/customer-service-agent/bin/ruff check customer_service_agent/
```

**验收口径（已脚本化验证过的）**
- `GET /api/faqs` → items 含 `status`、无 `is_disabled`；`status_counts={usable:58,needs_review:2}`。
- `GET /api/faqs?status=usable|needs_review|disabled` → 58 / 2 / 0。
- 禁用闭环：拉完整记录→POST `/api/faqs`(带全字段 + `status:'disabled'`)→该条移出 usable 进 disabled→再 POST 恢复原 status。**务必精确恢复，勿污染 60 条真实数据**。

## 6. 安全 / 数据
- 迁移只删一个待废弃布尔列 + 归一杂散 status，不动 FAQ 正文；60 条数据条数无损。
- 禁用闭环测试用「拉全量→改→精确回写原值」，验毕已恢复，真实数据零残留。
- 未触及 `.env`、system_prompt、上传原件、微信 token。

## 7. 遗留风险（交接给用户决策，勿擅动）
- 工作树未提交，且**混有多个特性**：本次 FAQ 三态，外加 06-01 的 `chunk-embedding-status`、`p0-frontend-fixes`、`frontend-acceptance`（三者 docs 也未提交）。建议按特性分批 commit，避免一次大杂烩；具体如何切分由用户定。
