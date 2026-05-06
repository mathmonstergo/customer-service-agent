# Customer Service Agent

本项目是一个本地客服知识库与 RAG 服务，使用 PostgreSQL + pgvector 做 FAQ 检索，并通过 OpenAI-compatible 接口调用聊天模型和 embedding 模型。

仓库不会包含真实 FAQ 问答数据、客户资料、生产提示词或本地密钥。真实数据请放在本地 ignored 文件中，例如 `data/faqs.jsonl`、`*.csv`、`.env`、`system_prompt.txt`。

## 主要能力

- 本地 FAQ 管理页面：新增、编辑、筛选、批量操作 FAQ。
- 保存问答和生成 embedding 分离：保存只写入正文与元数据，不会自动向量化。
- AI 辅助编辑：可保守优化问题/答案措辞，并生成相似问法。
- PostgreSQL + pgvector 检索：支持向量搜索和 RAG 答案生成。
- RAG 工具模式：可作为上游客服智能体的只读知识检索工具。
- 微信服务模式：保留个人微信登录和长运行消息处理能力。

## 项目结构

- `customer_service_agent/cli.py`：命令行入口，包含配置检查、数据库初始化、FAQ 导入、搜索、问答、微信登录、后台管理页启动。
- `customer_service_agent/db.py`：数据库 schema 初始化、FAQ 写入、embedding 状态维护、pgvector 搜索。
- `customer_service_agent/rag.py`：检索增强生成逻辑。
- `customer_service_agent/rag_tool.py`：面向上游客服智能体的结构化 RAG 工具接口。
- `customer_service_agent/admin_server.py`：本地 FAQ 管理页面和 API。
- `customer_service_agent/ai_assist.py`：AI 辅助优化与相似问法生成。
- `customer_service_agent/llm.py`：OpenAI-compatible chat / embedding 客户端封装。
- `customer_service_agent/wechat_client.py`：个人微信客户端封装。
- `customer_service_agent/wechat_service.py`：微信消息长运行服务。
- `scripts/install_user_service.sh`：根据模板安装 user-level systemd 服务。
- `systemd/customer-service-agent.service.template`：systemd 用户服务模板。

## 系统依赖

Ubuntu / Debian:

```bash
sudo apt-get update
sudo apt-get install -y postgresql postgresql-contrib postgresql-16-pgvector
sudo systemctl enable --now postgresql
```

确认 pgvector 可用：

```bash
sudo -u postgres psql -tAc "SELECT name FROM pg_available_extensions WHERE name = 'vector';"
```

## Conda 环境

```bash
conda env create -f environment.yml
conda run -n customer-service-agent python --version
```

## 本地配置

复制模板并填写真实配置：

```bash
cp .env.example .env
cp system_prompt.example.txt system_prompt.txt
```

必填环境变量：

- `DATABASE_URL`
- `CHAT_BASE_URL`
- `CHAT_API_KEY`
- `CHAT_MODEL`
- `EMBEDDING_BASE_URL`
- `EMBEDDING_API_KEY`
- `EMBEDDING_MODEL`

可选配置：

- `EMBEDDING_DIMENSIONS`：embedding 维度，默认 `1024`。
- `WECHAT_TOKEN_FILE`：微信 token 路径，默认 `/home/adam/.wxbot/token.json`。
- `WECHAT_MESSAGE_CHUNK_SIZE`：微信回复分段长度，默认 `1800`。
- `RAG_TOP_K`：检索返回数量，默认 `5`。
- `RAG_MIN_SCORE`：检索最低分数，默认 `0.35`。

注意：

- `.env` 不要提交。
- `system_prompt.txt` 不要提交。
- `*.jsonl`、`*.csv` 等 FAQ 数据文件不要提交。
- 本仓库默认只提交代码、模板和说明，不提交真实业务数据。

检查配置：

```bash
conda run -n customer-service-agent python -m customer_service_agent.cli check-config
```

## 本地 FAQ 管理页面

启动管理页面：

```bash
conda run -n customer-service-agent python -m customer_service_agent.cli admin --host 127.0.0.1 --port 8765
```

浏览器打开：

```text
http://127.0.0.1:8765
```

管理页面仅供本地使用，不包含登录系统。页面支持：

- FAQ 列表、搜索、状态筛选、embedding 状态筛选。
- 右侧抽屉式编辑问答。
- 新建和保存 FAQ。
- 单条或批量生成 embedding。
- AI 优化描述和生成相似问法。

保存 FAQ 只会保存正文和元数据，不会自动生成 embedding。需要点击单条 `生成 embedding`，或使用侧边栏批量生成 embedding。

页面预览：

![FAQ 管理页面预览 1](docs/assets/faq-management-page-1.png)

![FAQ 管理页面预览 2](docs/assets/faq-management-page-2.png)

## AI 辅助编辑

AI 辅助使用项目已有的 OpenAI-compatible Chat Completions 配置：

- `CHAT_BASE_URL`
- `CHAT_API_KEY`
- `CHAT_MODEL`

前端点击“优化描述”或“生成相似问法”后，会调用：

```text
POST /api/ai/optimize
```

后端会让模型返回 JSON：

```json
{
  "optimized_question": "优化后的标准问题",
  "optimized_answer": "优化后的答复",
  "similar_questions": ["相似问法 1", "相似问法 2"]
}
```

提示词约束是保守改写：只优化表达、结构、清晰度和客服口吻，不新增业务事实，不改变原始答复含义。AI 建议不会自动覆盖当前内容，需要人工点击应用并保存。

## 数据库初始化和 FAQ 导入

如果数据库和用户还不存在，先创建：

```bash
sudo -u postgres psql
CREATE USER customer_service_agent WITH PASSWORD '<choose-a-strong-password>';
CREATE DATABASE customer_service_agent OWNER customer_service_agent;
\q
```

初始化 schema：

```bash
conda run -n customer-service-agent python -m customer_service_agent.cli init-db
```

导入本地 FAQ JSONL：

```bash
conda run -n customer-service-agent python -m customer_service_agent.cli import-faq --path data/faqs.jsonl
```

## 本地检索和问答测试

向量搜索：

```bash
conda run -n customer-service-agent python -m customer_service_agent.cli search "如何处理用户反馈的问题？"
```

RAG 问答：

```bash
conda run -n customer-service-agent python -m customer_service_agent.cli ask "如何处理用户反馈的问题？"
```

## RAG 工具模式

推荐把本项目作为上游客服智能体的只读 FAQ / SOP RAG 工具。上游智能体负责判断是否直接回复、是否追问、是否调用其他后端工具、是否转人工。本项目只返回知识命中和可选答案草稿，不负责开户、重置密码、刷新缓存、派发任务、修改业务数据或直接给终端用户发消息。

结构化 FAQ 搜索：

```bash
conda run -n customer-service-agent python -m customer_service_agent.cli tool-search "如何处理用户反馈的问题？"
```

结构化答案草稿：

```bash
conda run -n customer-service-agent python -m customer_service_agent.cli tool-answer "如何处理用户反馈的问题？"
```

两个命令都会输出单个 JSON 对象：

- `tool-search` 返回检索到的 FAQ 文档。
- `tool-answer` 返回 `answer_draft` 和同一批来源文档，方便上游智能体做最终决策。

## 微信登录和服务

微信登录是独立手动步骤，成功后会写入 `WECHAT_TOKEN_FILE`：

```bash
conda run -n customer-service-agent python -m customer_service_agent.cli wechat-login
```

登录成功后，可以启动长运行服务：

```bash
conda run -n customer-service-agent python -m customer_service_agent.cli wechat-service
```

## systemd 用户服务

安装渲染后的用户服务：

```bash
./scripts/install_user_service.sh
```

允许用户服务在登出后继续运行：

```bash
sudo loginctl enable-linger "$USER"
```

启动和查看服务：

```bash
systemctl --user start customer-service-agent.service
systemctl --user status customer-service-agent.service
journalctl --user -u customer-service-agent.service -f
```

常用操作：

```bash
systemctl --user restart customer-service-agent.service
systemctl --user stop customer-service-agent.service
```

安装脚本会把当前仓库路径、`.env` 路径和 `customer-service-agent` conda 环境中的 Python 路径写入 `~/.config/systemd/user/customer-service-agent.service`。

## 验证

```bash
conda run -n customer-service-agent ruff check .
conda run -n customer-service-agent python -m customer_service_agent.cli --help
```

开发时也可以运行测试：

```bash
conda run -n customer-service-agent pytest -q
```
