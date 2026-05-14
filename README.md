# 内部知识库管理系统

本项目是一个本地优先的内部知识库与 RAG 管理工具，用于维护 FAQ、导入文档、生成向量、调试智能问答流程，并通过 PostgreSQL + pgvector 提供检索能力。

系统定位是内部工具：资料先进入审核和解析流程，确认后的内容再生成 embedding 并参与问答检索。

## 功能概览

- FAQ 管理：维护标准问答，支持列表、自动生成、人工审核和 embedding 生成。
- 文档管理：上传原件，解析 PDF / Word / Excel / Markdown 等资料，查看切片，并为已解析文档生成切片 embedding。
- 统一知识单元：FAQ 和文档切片会写入 `knowledge_chunks`，为后续混合检索、KG 和编排流打基础。
- 智能问答：左侧对话历史，中间流式聊天，右侧流程调试抽屉；当前默认使用基础 RAG。
- 设置管理：本地维护 LLM、Embedding、MinerU、数据库和微信相关配置。
- 微信服务：外部IM入口对话测试。

## 快速开始

创建 conda 环境：

```bash
conda env create -f environment.yml
conda run -n customer-service-agent python --version
```

复制本地配置模板：

```bash
cp .env.example .env
cp system_prompt.example.txt system_prompt.txt
```

至少填写这些环境变量：

```text
DATABASE_URL
CHAT_BASE_URL
CHAT_API_KEY
CHAT_MODEL
EMBEDDING_BASE_URL
EMBEDDING_API_KEY
EMBEDDING_MODEL
EMBEDDING_DIMENSIONS
```

初始化数据库并启动后台：

```bash
conda run -n customer-service-agent python -m customer_service_agent.cli check-config
conda run -n customer-service-agent python -m customer_service_agent.cli init-db
conda run -n customer-service-agent python -m customer_service_agent.cli admin --host 127.0.0.1 --port 8765
```

浏览器打开：

```text
http://127.0.0.1:8765/admin.html
```

## 数据库依赖

需要 PostgreSQL 和 pgvector。Ubuntu / Debian 示例：

```bash
sudo apt-get update
sudo apt-get install -y postgresql postgresql-contrib postgresql-16-pgvector
sudo systemctl enable --now postgresql
```

确认 pgvector 可用：

```bash
sudo -u postgres psql -tAc "SELECT name FROM pg_available_extensions WHERE name = 'vector';"
```

如果数据库和用户还不存在：

```sql
CREATE USER customer_service_agent WITH PASSWORD '<password>';
CREATE DATABASE customer_service_agent OWNER customer_service_agent;
```

## 页面预览

![FAQ 管理页面预览 1](docs/assets/faq-management-page-1.png)

![FAQ 管理页面预览 2](docs/assets/faq-management-page-2.png)


## 主要目录

- `customer_service_agent/admin_server.py`：本地管理后台 API。
- `customer_service_agent/static/`：管理后台 HTML / CSS / JS。
- `customer_service_agent/db.py`：数据库读写、统一知识单元和 pgvector 检索。
- `customer_service_agent/document_parser.py`：文档解析与切块。
- `customer_service_agent/import_ai.py`：从切片生成候选 FAQ。
- `customer_service_agent/rag.py`：RAG 答案生成。
- `customer_service_agent/rag_tool.py`：上游智能体调用的只读工具接口。
- `customer_service_agent/wechat_service.py`：外部IM对话测试(微信)长运行服务。
- `sql/001_init.sql`：数据库 schema。
