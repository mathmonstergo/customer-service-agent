# P0 前端验收修复

- 时间：2026-06-01 10:52
- 类型：验收后的小修（bug 修复 + a11y + 品牌），非架构改动
- 来源：承接 `../20260601-102613-frontend-acceptance/acceptance-and-optimization.md` 的 P0 清单
- 范围：纯前端（`web/`）+ 重建后的 `dist`，不动后端 / schema / API / 检索 / AI 逻辑

## 改了什么

### P0-① 切片标题竖排（最显眼的渲染缺陷）
- 现象：文档抽屉切片 #1 标题"用户使用手册"每字一行竖排。
- 根因（已用真实数据确认）：MinerU 把 PDF 封面的疏排标题解析成单字之间夹空行的文本
  （`source_text` 实为 `用\n\n户\n\n使\n\n用\n\n手\n\n册\n\n…`），前端用 `whitespace-pre-wrap` 渲染就成了竖排。
- 修法：在 `web/src/components/shared/source-block-preview.tsx` 增加纯展示层的 `deverticalizeCjk()`，
  只把"连续 ≥2 个单字（汉字/假名/谚文）行（中间可夹空行）"横向合并，普通段落 / 目录原样保留；
  应用于 `title` 与默认文本两个渲染分支。
- 边界：**只动展示，不动存储**。`source_text` 与向量未改，不改变文字内容本身（同一批字符，仅去掉逐字换行）。
- 遗留（建议后续，非本次）：`source_text` 里同样的 `\n\n` 也进了 embedding，根因在解析/规整层。
  若要根治需在导入流程做文本规整 + 重新 embedding（属"较大改动"，需另起确认 + 有成本），本次不做。

### P0-② DialogTitle / Description a11y 报错（清空控制台）
- 现象：打开文档抽屉时控制台报 `DialogContent requires a DialogTitle`。
- 根因：`DocumentDrawer` / `FaqDrawer` 在数据加载完成前返回 `DrawerInnerSkeleton`，该骨架没有 `DrawerTitle`，
  Radix 在加载窗口内检测不到标题即告警（数据到位后标题才出现，但告警已触发）。
- 修法：
  - 给两个 `DrawerInnerSkeleton` 各加一个 `sr-only` 的 `DrawerTitle`（屏幕阅读器可读、视觉隐藏）。
  - 修标题告警后浮现出 Radix 的第二条建议 `Missing Description…`；在 `drawer.tsx` / `dialog.tsx` 的
    `DialogPrimitive.Content` 上显式加 `aria-describedby={undefined}`（Radix 官方关掉该提示的方式，
    放在 `{...props}` 前，消费方仍可自行传 `aria-describedby` 关联描述）。`aria-labelledby`（标题关联）保持不变。
- 其它抽屉（debug-drawer / provider-drawer）标题本就无条件渲染，且同样受益于上面的 Content 级修复。

### P0-③ 页面标题品牌化
- `web/index.html`：`<title>web</title>` → `<title>客服助手 · 知识库后台</title>`；`lang="en"` → `lang="zh-CN"`。

## 改动文件
- `web/index.html`
- `web/src/components/shared/source-block-preview.tsx`
- `web/src/components/ui/drawer.tsx`
- `web/src/components/ui/dialog.tsx`
- `web/src/pages/documents/document-drawer.tsx`
- `web/src/pages/faqs/faq-drawer.tsx`
- `customer_service_agent/static/dist/**`（`npm run build` 产物，沿用"dist 入库"基线决定）

## 验证（Playwright headless，对生产 dist）
- `tsc -b && vite build` 通过，无类型错误；dist 仅 1 个 JS + 1 个 CSS，index.html 引用一致。
- 文档抽屉：标题渲染为连续"用户使用手册"（断言 `"用\n户"` 不再出现）；正文横向正常。
- 文档抽屉 + FAQ 抽屉：本轮打开周期内 **console error/warning 均为 0**（DialogTitle 与 Description 两条告警都已消除）。
- 浏览器标签标题为"客服助手 · 知识库后台"。

## 测试策略
- 按用户要求：**暂不补单测**，先让用户在界面上验收效果，确认后再决定补测，避免改动未定型就写测试白费。

## 未做（等用户验收/确认）
- 验收报告里的 P1 / P2 项（问答延迟、"0 条消息"按类型渲染、切片/embedding 列说明、FAQ 双保存模型、
  置信度/AI 优化说明等）均未动。
- 上述 source_text 根因规整 + 重新 embedding。
