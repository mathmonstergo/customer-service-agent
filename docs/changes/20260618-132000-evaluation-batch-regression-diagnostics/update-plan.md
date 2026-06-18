# 评测工作台批量回归与失败诊断

## 目标

把效果验收工作台从单条运行扩展为可重复批量回归，并为失败用例提供规则化诊断，服务后续切块、检索、RAGFlow/MinerU 后处理对齐工作的效果验证。

## 影响范围

* 后端管理 API：评测运行复用或扩展。
* 前端评测工作台：批量运行入口、进度、汇总、失败列表。
* 前端 schema/hooks：若新增 batch API 或 batch summary 类型则同步更新。
* 测试：后端规则测试、前端 lint/build。
* 代码规格：如新增跨层合同，更新 `.trellis/spec/`。

## 初步步骤

1. 明确 MVP 是否包含持久化批次/基线历史。已确认：本轮不包含。
2. 根据确认结果更新 PRD。已完成。
3. 读取相关 spec 并进入实现阶段。
4. 实现前端顺序批量运行、进度、汇总和失败诊断。
5. 补充测试和规格。
6. 运行质量门并分批提交。

## 需要用户确认

* 已确认：第一版先不做持久化 batch/baseline，只做当前会话内批量运行、汇总和失败诊断。

## 验证记录

* `node --test web/src/pages/evaluation/batch-diagnostics.test.ts`：先按 TDD RED 失败于缺少 `batch-diagnostics.ts`，实现后通过。
* `npm test`（`web/`）：通过，`1` 个 Node 测试通过。
* `npm run lint`（`web/`）：通过。
* `npm run build`（`web/`）：通过，并更新 `customer_service_agent/static/dist`；Vite 保留大 chunk 警告。
* `conda run -n customer-service-agent python -m ruff check .`：通过。
* `conda run --no-capture-output -n customer-service-agent python -m pytest -q`：`243 passed`。
* `conda run -n customer-service-agent python -m customer_service_agent.cli check-config`：`config ok`。
* `git diff --check`：通过。
* 浏览器验证：Vite dev server `http://127.0.0.1:5173/static/dist/#/evaluation` + admin API `http://127.0.0.1:8080`，Playwright 快照确认批量回归面板、`运行 active` 按钮、汇总指标和诊断卡渲染。
