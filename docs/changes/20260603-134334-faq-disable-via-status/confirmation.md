# 确认记录

## 背景（为什么有这份交接文档）
- 本特性开发期间，推理网关多次返回 524，agent resume 经常无法续上对话，上下文被 `/clear`。
- 用户明确要求：**开发过程要记录好过程文档，否则其他 AI 无法无缝衔接**。
- 据此：本次产出以「磁盘上的交接文档」为第一交付物（见 `update-plan.md`），文件不依赖对话上下文，断线也不丢。

## 据此决定
- 续接上一会话未完成的「FAQ 禁用归一到 status 三态」：本次只补齐**前端**（faq-drawer 构建阻塞 + faq-list 归一）并完成**迁移 + 自检**。
- 不写新测试，先让用户浏览器验收效果再决定是否补测（沿用 [[feedback-lightweight-verification]]）。
- **不主动 git commit**；如何分批提交（工作树混有多特性）由用户明确指示（沿用本项目既有惯例）。
- 通用 UI 口径不为 FAQ 单场景硬编码（[[feedback-generic-ui-not-scenario-specific]]）：三态/圆点走统一字典与 `embedDotTone`。

## 关键定位（本次新查明）
- 构建阻塞根因：`faq-drawer.tsx` 仍 import 已被删除的 `useToggleFaqDisabled` → `tsc` 失败。非文案问题。
- 「禁用即时生效」由检索 SQL `COALESCE(fq.status, kc.status)='usable'` 实时读 `faq_documents.status` 保证。

## 安全 / 数据
- 迁移幂等、只删废弃布尔列 + 归一杂散 status，FAQ 正文与 60 条数据条数无损。
- 禁用闭环测试「拉全量→改 disabled→精确回写原值」，验毕已恢复，真实数据零残留。
- 未触及 `.env`、system_prompt、上传原件、微信 token。

## 待用户确认
- 浏览器验收结果（三态下拉 / Embedding 按钮 / 批量 Embedding / Waypoints 图标）。
- 是否提交、以及如何切分多特性的未提交改动。
