# 评测工作台中文化与来源追溯

## Goal

把效果验收工作台从“技术字段可见”提升到“业务用户可理解、可追溯、可操作”：候选来源要能看懂、能打开对应 FAQ/文档切片、能复制内部 ID 排查，同时统一抽屉宽度和中文文案，减少 `source_id/chunk_id/retrieval_hybrid_v1/Recall@K` 等内部术语对用户的干扰。

## What I already know

* 用户确认需要继续处理评测工作台的可读性和追溯问题。
* 用户希望：
  * `查看 FAQ` 打开既有 FAQ 抽屉；
  * `查看文档切片` 打开既有文档抽屉，并定位到对应切片；
  * `复制 ID` 放在 ID 旁边的经典复制 icon 上，hover 后鼠标是手型；
  * 不建议只让用户点击 ID 本身复制，避免和查看/选中文本冲突；
  * 整个平台抽屉宽度尽量统一到效果验收抽屉当前的 `520px`；
  * 如果改窄 FAQ/文档抽屉，需要重新规划按钮和布局，不能挤乱。
* 当前抽屉宽度：
  * 效果验收用例抽屉：`520px`
  * 别名词典抽屉：`520px`
  * 会话供应商抽屉：`520px`
  * 智能问答调试抽屉：`560px`
  * FAQ 抽屉：`680px`
  * 文档抽屉：`820px`
* 当前全局 UI store 已有：
  * `openFaqId/setOpenFaqId`
  * `openImportFileId/setOpenImportFileId`
  * `currentChunkIndex/setCurrentChunkIndex`
* 当前评测候选表只显示 `source/chunk` 内部 ID，且 `位置 / 摘要` 可能因为 payload 缺少可读字段而显示 `--`。
* 当前后端 `retrieval_eval_item_payload()` 已透传 document-like 字段，但 FAQ 候选还可能缺少问题/答案摘要。
* 用户确认复制 ID 采用 ID 右侧复制 icon，不采用点击 ID 本身复制。
* 用户确认可以优先统一抽屉宽度；同时要求先检查 FAQ/切片抽屉，特别是切片顶部按钮，必要时把按钮优化为单 icon + hover 文案。
* 已检查现有抽屉：
  * FAQ 抽屉顶部主要是标题、状态、`AI 优化`；底部有关闭、Embedding、保存修改。
  * 文档抽屉顶部操作较多：Chunker、开始解析、Embedding、生成假设问题、下载、启用/禁用、删除。
  * 切片工具栏也有多个文本按钮：重新向量、启用/禁用、编辑原文/退出编辑。
  * 文档抽屉从 `820px` 收窄后，文档级和切片级按钮是最容易挤压的区域。
* 用户发现文档抽屉里的 Chunker 原生下拉框没有暗色主题兼容，弹出层白底导致文字不可读。
* 用户补充平台 UI 规则：
  * 按钮风格必须统一，优先参考成熟产品用 icon 代替冗长文字；
  * 难理解的动作可以使用“简短文字 + icon”；
  * 不同页面、不同抽屉也要遵循同一套按钮制作规则；
  * 抽屉、弹窗、页面提示等元素也需要高度统一；
  * 开发新内容前必须先找已有类似控件/按钮，不直接创造新结构。

## Assumptions

* 第一版不新做详情弹窗，优先复用已有 FAQ/文档抽屉样式。
* 复制 ID 是排查能力，不作为候选行的主操作。
* 抽屉宽度统一应通过共享常量或统一默认值实现，避免每个页面散落 magic number。
* FAQ/文档抽屉改窄后，内部信息布局可能需要改为更纵向、更紧凑的工具型布局。

## Requirements

* 评测候选表主信息必须中文化：
  * `rank` -> `排序`
  * `score` -> `分数`
  * `channels` -> `召回通道`
  * `source/chunk` -> `来源 ID / 切片 ID`
  * `retrieval_hybrid_v1` -> `混合检索 v1`
  * `未标注` -> `待设置期望命中`
* 候选来源主文案应优先展示可读信息：
  * FAQ：FAQ 问题 + 答案摘要；
  * 文档：文档名 + 页码/章节/切片摘要；
  * 缺失时才退回 ID。
* 候选行应提供追溯操作：
  * FAQ 候选显示 `查看 FAQ`；
  * 文档候选显示 `查看切片`；
  * 打开文档抽屉时尽量定位到对应审核切片；
  * 无法定位时打开文档并给用户可读提示或保留 ID 供复制。
* 候选行 ID 显示应降低视觉优先级，并在 ID 右侧提供复制 icon：
  * icon 使用 lucide `Copy`；
  * button 有 `cursor-pointer`；
  * hover/title 标明复制对象；
  * 点击后 toast 提示复制成功/失败。
* 用例编辑抽屉的高级字段中文化：
  * `期望 source ids` -> `期望来源 ID`
  * `期望 chunk ids` -> `期望切片 ID`
  * 说明文案使用“来源/切片”，不把 source/chunk 当作用户主要概念。
* 统一抽屉宽度：
  * 默认目标宽度为 `520px`；
  * FAQ/文档抽屉改为统一宽度后，内部按钮和信息区要重新布局，避免横向挤压；
  * 若文档切片浏览器在 `520px` 下信息密度过高，可先采用 `560px` 作为过渡宽度，但需要在 PRD 记录取舍。
* 文档/切片抽屉按钮在收窄后应 icon 化：
  * 文档级操作保留必要文案的只限主要动作，次要动作改为 icon-only；
  * 切片工具栏操作改为 icon-only 或极短标签；
  * 每个 icon button 必须有 `title`/tooltip，hover 能读到“重新生成向量 / 禁用切片 / 编辑原文”等文案；
  * 危险操作（删除）仍需红色语义，避免 icon 化后误触。
* 平台级 UI 一致性：
  * 优先使用已有 `Button`、`Drawer`、`Tooltip`、`Popover`、`Badge`、`toast`；
  * icon-only 按钮必须有 `title` 或 tooltip；
  * 需要解释的主动作使用短文字 + icon；
  * 不为单个页面临时创造不一致的按钮结构；
  * 鼠标悬停在可点击 icon 上必须是手型。
* 文档抽屉 Chunker 选择器必须暗色主题可读：
  * 不继续使用会弹出白色系统菜单的原生 select，除非能稳定适配暗色主题；
  * 优先复用项目已有的暗色分段/弹出选择控件；
  * 选项文字、选中态、hover 态在暗色主题下必须可读。

## Acceptance Criteria

* [x] 评测候选中 FAQ 可点击打开既有 FAQ 抽屉。
* [x] 评测候选中文档可点击打开既有文档抽屉，并定位到对应切片。
* [x] 候选 ID 可通过复制 icon 复制，icon hover 为手型并有提示。
* [x] 候选表、用例抽屉、批量回归面板不再暴露 `source_id/vector_count/retrieval_hybrid_v1` 这类内部字段名；`Recall@K/MRR/Top1` 等检索指标专有缩写保留英文。
* [x] FAQ 候选不再只显示 ID；至少展示问题或答案摘要。
* [x] 文档候选在有页码/章节/摘要时正常展示；缺失时保留 ID 排查能力。
* [x] 抽屉宽度统一方案落地，FAQ/文档抽屉布局不出现按钮挤压或文本严重溢出。
* [x] 文档抽屉和切片工具栏的多按钮区域在统一宽度下改成更紧凑的 icon/tooltip 形式。
* [x] 文档抽屉 Chunker 下拉在暗色主题下可读，不再出现白底白字/低对比问题。
* [x] 新增或调整的按钮、抽屉、提示控件遵循同一套已有组件规则。
* [x] 前端 lint/build 通过；若改后端 payload，补充 Python 测试。

说明：文档切片抽屉按 PRD 过渡口径使用 `560px`，FAQ/评测类抽屉使用 `520px`。真实浏览器截图检查因当前 Chrome DevTools MCP 缺少 X server 未完成，已完成构建、lint、测试和页面资源 200 检查。

## Definition of Done

* 更新 `docs/changes/20260618-141500-evaluation-readable-provenance-ui/`。
* 更新 PRD 与用户确认记录。
* 如新增跨层 payload 字段，更新 `.trellis/spec/`。
* 遵守 AGENTS.md：UI 功能先确认最终功能、信息层级、主要布局和操作流程。
* 不改变检索算法和评测指标计算口径。

## Out of Scope

* 新增独立详情弹窗。
* 新增持久化评测基线/策略切换。
* 修改核心检索排序或召回算法。
* 大规模重做 FAQ/文档管理页信息架构。

## Technical Notes

* 评测页：
  * `web/src/pages/EvaluationPage.tsx`
  * `web/src/pages/evaluation/result-panel.tsx`
  * `web/src/pages/evaluation/case-drawer.tsx`
  * `web/src/pages/evaluation/batch-panel.tsx`
  * `web/src/pages/evaluation/helpers.ts`
* 抽屉：
  * `web/src/components/ui/drawer.tsx`
  * `web/src/pages/faqs/faq-drawer.tsx`
  * `web/src/pages/documents/document-drawer.tsx`
  * `web/src/pages/documents/chunk-browser.tsx`
* 全局 UI 状态：
  * `web/src/store/ui.ts`
* 后端候选 payload：
  * `customer_service_agent/admin_server.py::retrieval_eval_item_payload`
  * `AdminApp.run_retrieval_eval_case`

## Proposed Design

### Approach A: Shared Drawer Reuse + Copy Icon + Chinese Labels (Recommended)

* 评测页直接挂载并控制 `FaqDrawer`、`DocumentDrawer`。
* 候选行根据 `source_type` 显示 `查看 FAQ` 或 `查看切片`。
* ID 放入低优先级行，来源 ID/切片 ID 各自右侧放 `Copy` icon。
* 抽屉宽度抽成共享常量，如 `DRAWER_WIDTH_COMPACT = 520`，FAQ/文档抽屉先对齐该宽度并调整内部布局。

优点：复用已有抽屉体验，开发量可控，用户路径清晰。
代价：文档切片浏览器原本为 `820px` 设计，缩窄后需要局部重排。

### Approach B: Evaluation 内嵌只读预览

* 候选表点击后在评测页内展开只读 FAQ/文档摘要。
* 不打开全局抽屉。

优点：不影响 FAQ/文档抽屉宽度。
代价：会重复造一套详情预览，和用户“复用之前抽屉样式”的要求不一致。

### Recommendation

采用 Approach A。复制 ID 使用“右侧 icon 按钮”，不使用点击 ID 本身复制。ID 文本仍可选中，复制动作显式可见。

### Drawer Button Layout Decision

文档抽屉和切片工具栏在统一宽度后采用“主要动作保留短文字、次要动作 icon-only + hover 文案”的布局：

* 文档级主动作：`开始解析` 使用 `Play + 开始解析`，因为它是文档流程入口。
* Embedding 动作：FAQ、文档、切片内重新生成切片向量统一使用 `Waypoints + Embedding`，不使用刷新 icon。
* 关闭动作：使用经典 `X` icon；保存动作使用经典 `Save` icon。
* 文档级次动作：生成假设问题、下载、启用/禁用、删除优先 icon-only 或短标签，全部加 title/tooltip。
* 切片级动作：启用/禁用、编辑原文优先 icon-only，依靠状态颜色和 hover 文案说明。
* 删除等危险动作保留 danger 样式和明确 title。
* Chunker 选择器替换为暗色兼容控件，避免原生 select 弹出层在 Linux/Chrome 下白底低对比。
* 本任务形成的平台 UI 规则需要沉淀到前端 spec，后续新增页面也按同一套控件优先级执行。
