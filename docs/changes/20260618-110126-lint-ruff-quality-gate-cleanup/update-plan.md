# 全仓 lint 和 ruff 质量门清理

## 修改目标

让项目恢复全仓质量门：后端 `ruff check .` 和前端 `npm run lint` 都能通过，后续功能交付不用再区分“本次相关文件通过、全仓既有失败”。

## 影响范围

* `.trellis/scripts/common/*` 的 ruff 清理。
* `web/src/components/ui/*` 的 Fast Refresh 合规拆分。
* 少量前端页面中的 React Hooks lint 修复。

## 具体步骤

1. 已复现并记录当前 ruff / eslint 失败。
2. 已修复 `.trellis/scripts/common/*` ruff 问题。
3. 已修复 UI 基础组件非组件导出导致的 Fast Refresh 问题。
4. 已修复页面中的 `set-state-in-effect` 和 deps warning。
5. 已运行全量验证命令。
6. 已把 Fast Refresh 组件导出约定补充到 `.trellis/spec/frontend/quality.md`。

## 预期效果

`conda run -n customer-service-agent python -m ruff check .` 和 `npm run lint` 从失败恢复为通过。

## 验证结果

* `conda run -n customer-service-agent python -m ruff check .`：通过。
* `npm run lint`（`web/`）：通过。
* `npm run build`（`web/`）：通过，Vite 保留单 chunk 超 500 kB 的体积 warning。
* `conda run --no-capture-output -n customer-service-agent python -m pytest -q`：242 passed。
* `conda run -n customer-service-agent python -m customer_service_agent.cli check-config`：通过。
* `git diff --check`：通过。

说明：最初直接用 `conda run -n customer-service-agent python -m pytest -q` 时 conda 捕获输出，长时间没有进度显示；改用 `--no-capture-output` 后全量测试正常完成。

## 确认记录

用户确认按推荐方式继续：把全仓 lint/ruff 清理作为下一阶段独立任务推进。
