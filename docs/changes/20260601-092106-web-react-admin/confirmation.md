# 用户确认记录

## 2026-06-01 09:21

### 背景

会话开始时工作区处于"大改造进行中"状态:老静态后台已删,React `web/` 全量未跟踪,后端 13 个文件改动 + `mcp_server.py` / `import_questions.py` 未提交,构建产物 `static/dist/` 未跟踪;且 React 重写这件事缺 `docs/changes/` 记录。后端经核验为绿(`ruff` 通过、`pytest` 223 全过)。

### 本次确认范围

用户选择"先存档建基线"——这一轮不加新功能,把未提交工作整理成干净基线:

1. 补齐 React 迁移的回顾式变更文档(本目录 `update-plan.md`)。
2. 做一次 checkpoint 提交。

### 2 项口径确认

- **构建产物 `static/dist/` 进 Git**：保证 clone 后直接跑 `admin` 即有界面(部署链路无 node 构建步骤);接受"源码改后忘 build 会不一致"的风险,后续可改 gitignore + 构建步骤。
- **提交粒度 = 单个 checkpoint**：一次性提交全部未提交工作,commit message 分条说明。因 `admin_server.py` 同时被前端托管与多项后端能力改动覆盖,硬拆易出现中间不可编译状态,故不拆分。

### 提交前安全审计结论(已执行)

- 敏感文件全部被 `.gitignore` 拦截:`.env`、`.env.*`、`system_prompt.txt`、`data/uploads/`、`*.jsonl/csv/pdf/docx/xlsx`、`.playwright-cli/`、微信 token。
- 待提交源码(`web/src`、`import_questions.py`、`mcp_server.py`、`scripts/screenshot.py`)无硬编码密钥(命中均为表单字段名/空默认值)。
- `static/dist` bundle 未使用构建期 `import.meta.env`;用 `.env` 5 个真实敏感值反查 bundle 均 0 命中。

### 完成记录

- 见提交 commit 与 `update-plan.md`。提交后该批工作转为基线,后续开发在其上进行。
