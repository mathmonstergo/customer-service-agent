# 全仓 lint 和 ruff 质量门清理

## Goal

恢复项目质量门，让后端 `ruff check .` 和前端 `npm run lint` 可以作为下一阶段开发前的可信检查命令使用，避免每次交付都需要解释既有失败。

## What I already know

* Python 项目环境使用 conda：`conda run -n customer-service-agent ...`。
* 当前 `conda run -n customer-service-agent python -m ruff check .` 失败集中在 `.trellis/scripts/common/*`。
* 当前 `npm run lint` 失败集中在：
  * `web/src/components/ui/{button,dialog,drawer,popover,status-dot,toaster,tooltip}.tsx` 的 Fast Refresh `only-export-components`。
  * `web/src/pages/FaqsPage.tsx`、`web/src/pages/assistant/provider-drawer.tsx`、`web/src/pages/documents/chunk-browser.tsx`、`web/src/pages/faqs/faq-drawer.tsx` 的 `react-hooks/set-state-in-effect`。
  * 少量 `react-hooks/exhaustive-deps` warning。
* 当前工作区在任务创建前为 clean。

## Requirements

* 修复全仓 ruff 错误，让 `conda run -n customer-service-agent python -m ruff check .` 通过。
* 修复前端 ESLint 错误/警告，让 `npm run lint` 在 `web/` 通过。
* 保持业务行为不变；只做质量门要求的结构调整和等价重写。
* 修复 React effect 相关问题时，优先消除不必要派生 state；确需同步外部输入到草稿时要避免触发 lint 规则。
* 修复 Fast Refresh 问题时，优先把非组件导出拆到相邻工具/常量文件，避免关闭规则。
* 不顺带重构 UI 布局、RAG 逻辑、文档解析逻辑或 Trellis workflow。

## Acceptance Criteria

* [ ] `conda run -n customer-service-agent python -m ruff check .` 通过。
* [ ] `npm run lint`（`web/`）通过。
* [ ] `npm run build`（`web/`）通过。
* [ ] `conda run -n customer-service-agent python -m pytest -q` 通过，或如失败需明确是环境/外部依赖问题。
* [ ] `conda run -n customer-service-agent python -m customer_service_agent.cli check-config` 通过。
* [ ] `git diff --check` 通过。

## Definition of Done

* 所有修改有明确质量门错误对应关系。
* 不新增功能，不改变业务数据 schema。
* 若发现新项目约定，更新 `.trellis/spec/`。
* 分批提交：代码修复、任务/文档记录、归档/journal。

## Technical Approach

* Python ruff：
  * `.trellis/scripts/common/__init__.py` 用显式 `__all__` / re-export 方式表达公共 API，避免 F401，同时保留兼容导入。
  * 删除确实未使用的导入，重命名歧义变量，移除无占位 f-string。
* Frontend ESLint：
  * UI 组件文件只导出组件；把 variant、primitive alias、toast API 等非组件导出迁到相邻模块或独立文件，并更新引用。
  * 对 `set-state-in-effect`，优先改成 key-based remount、派生值、或事件中初始化；保留用户编辑中的草稿不被无关 refetch 覆盖。

## Out of Scope

* 关闭或放宽 lint/ruff 规则。
* 大范围 UI 重构。
* 修改文档解析、RAG、FAQ 业务行为。
* 清理和当前质量门无关的 TODO/样式债。

## Technical Notes

* 复现命令：
  * `conda run -n customer-service-agent python -m ruff check .`
  * `npm run lint` under `web/`
* 相关规范：
  * `.trellis/spec/frontend/react-pitfalls.md`
  * `.trellis/spec/frontend/quality.md`
  * `.trellis/spec/shared/code-quality.md`
  * `.trellis/spec/shared/typescript.md`
  * `.trellis/spec/backend/quality.md`
