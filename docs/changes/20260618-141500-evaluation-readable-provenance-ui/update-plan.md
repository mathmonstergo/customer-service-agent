# 评测工作台中文化与来源追溯

## 目标

让评测工作台候选来源可读、可复制、可追溯，并统一平台抽屉宽度与中文文案。

## 影响范围

* 评测结果候选表与批量回归面板。
* 评测用例编辑抽屉。
* FAQ/文档抽屉复用与宽度统一。
* 后端评测候选 payload（如需补 FAQ 可读字段）。
* 前端/后端测试和 code-spec。

## 初步步骤

1. 确认 UI 方案：复用抽屉、复制 icon、统一宽度策略。已确认采用复制 icon。
2. 检查 FAQ/文档/切片抽屉按钮布局。已检查，文档级和切片级按钮需 icon 化。
3. 修复文档抽屉 Chunker 选择器暗色主题可读性问题。
4. 检查 FAQ/文档候选 payload 是否足够支持可读摘要。
5. 实现候选行中文化、查看按钮、复制 ID。
6. 实现评测页挂载 FAQ/文档抽屉并定位切片。
7. 统一抽屉宽度并调整 FAQ/文档内部布局。
8. 补充测试和验证。

## 需要用户确认

* 已确认：ID 右侧复制 icon，不把点击 ID 本身作为复制主交互。
* 已确认并落地：FAQ/评测等普通抽屉统一到 `520px`；文档切片抽屉因顶部操作和切片浏览器信息密度较高，先用 `560px` 过渡。

## 验证记录

* `web`: `npm test`
* `web`: `npm run lint`
* `web`: `npm run build`
* 后端：`conda run -n customer-service-agent python -m ruff check .`
* 后端：`conda run --no-capture-output -n customer-service-agent python -m pytest -q`
* 后端：`conda run -n customer-service-agent python -m customer_service_agent.cli check-config`
* 仓库：`git diff --check`
* 本地页面资源：Vite dev server 在 `http://127.0.0.1:5174/static/dist/` 返回 200。
* 浏览器限制：Chrome DevTools MCP 因当前环境缺少 X server 未能启动有界面浏览器；未完成真实浏览器截图检查。

## 实施结果

* 评测候选表中文化 `排序 / 分数 / 召回通道`，策略名 `retrieval_hybrid_v1` 展示为 `混合检索 v1`。
* 指标卡保留 `Recall@K / MRR / Top1` 等检索领域通用缩写，解释信息放在 hover/title 中。
* FAQ 候选 payload 增加 `question / answer / category / tags`，前端候选摘要优先展示问题和答案。
* 候选行增加 `查看 FAQ / 查看切片`，复用已有 FAQ/文档抽屉；文档候选带 `source_chunk_id` 时定位到对应审核切片。
* 来源 ID、切片 ID 降为排查信息，并在右侧提供 `Copy` icon 复制。
* 用例抽屉高级字段改为 `期望来源 ID / 期望切片 ID`。
* 批量回归面板改为中文启用用例计数和中文排名文案。
* 抽屉宽度使用共享常量；FAQ/评测抽屉为 `520px`，文档抽屉为 `560px`。
* 文档抽屉 Chunker 原生 select 替换为暗色兼容的 Popover/Button 菜单。
* 文档和切片工具栏按钮改为 icon/短文案组合，icon button 补齐 title 和手型光标。
* 平台功能按钮语义整理：
  * 开始/运行类使用 `Play + 短文字`，文档抽屉“开始解析”已切换为播放 icon。
  * 关闭类使用经典 `X` icon；取消表单仍保留“取消”文字。
  * 保存类使用 `Save + 保存/保存修改`。
  * Embedding 类统一使用 `Waypoints + Embedding`，包括 FAQ、文档、切片内重新生成切片向量，不再用刷新 icon。
* 文档删除从 `confirm()` 改为复用现有 `Dialog` 确认。
