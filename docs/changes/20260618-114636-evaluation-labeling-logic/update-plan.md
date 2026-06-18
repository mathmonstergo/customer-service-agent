# 评测工作台标注逻辑优化

## 修改目标

解决评测工作台中期望 source/chunk 需要手填内部 ID 的平台逻辑问题，让用户可以通过可读候选来源完成标注、查看和回溯。

## 影响范围

* 评测用例抽屉。
* 评测运行结果候选表。
* 后端评测候选 payload。
* 必要时补充 FAQ/文档切片可读元数据或跳转信息。

## 具体步骤

1. 梳理当前评测工作台的标注断点。
2. 已和用户确认 MVP 范围：优先做从候选结果标注期望命中。
3. 已更新 PRD 和确认记录。
4. 已实现后端候选 payload 可读字段。
5. 已实现前端候选一键设为期望命中。
6. 已调整用例编辑抽屉，弱化裸 ID 输入。
7. 已补充测试并运行质量门。

## 预期效果

用户可以不理解内部 ID，也能创建评测用例、运行检索、从候选中标注正确目标，并在之后复查期望命中。

## 当前决策

本轮先做“从一次运行候选结果中标注期望命中”，暂不做“新建用例时搜索 FAQ/文档切片并选择目标”。

一键标注采用单一粒度：标注 source 时清空 chunk 期望；标注 chunk 时清空 source 期望，避免后端指标优先级造成误读。

## 验证结果

* `conda run -n customer-service-agent python -m ruff check .`：通过。
* `conda run --no-capture-output -n customer-service-agent python -m pytest -q`：243 passed。
* `conda run -n customer-service-agent python -m customer_service_agent.cli check-config`：通过。
* `npm run lint`（`web/`）：通过。
* `npm run build`（`web/`）：通过，Vite 保留单 chunk 超 500 kB 的体积 warning。
* `git diff --check`：通过。
