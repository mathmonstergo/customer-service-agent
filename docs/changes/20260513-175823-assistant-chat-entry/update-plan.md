# 智能问答入口与流式调试视图调整计划

创建时间：2026-05-13 17:58:23 CST

## 修改目标

在“智能问答”入口实现一个简洁的三栏工作台：

- 左侧：对话历史管理，支持新建会话、搜索历史、切换会话。
- 中间：ChatGPT 式聊天区域，用户输入问题后默认以流式方式返回回答。
- 右侧：可收起的流程可视化调试抽屉，展示本次问答的执行节点、状态、耗时和来源。

首版只实现当前可用的 `基础 RAG` 流程，不实现 KG、意图识别、混合检索和拖拽式自定义编排器；但后端事件结构和前端展示结构要保留后续编排流扩展点。

## 影响范围

- 后端管理 API：`customer_service_agent/admin_server.py`
- LLM 客户端：`customer_service_agent/llm.py`
- RAG 工具结构复用：`customer_service_agent/rag_tool.py`
- 静态页面：`customer_service_agent/static/admin.html`
- 前端交互：`customer_service_agent/static/admin.js`
- 前端样式：`customer_service_agent/static/admin.css`
- 测试：`tests/test_admin_server.py`、`tests/test_llm.py`、`tests/test_admin_table_layout.py`

本次不新增数据库 schema。对话历史首版存储在浏览器本地，避免把调试会话持久化为正式业务数据。

## 具体步骤

1. 增加 ChatClient 流式输出能力：优先使用 OpenAI-compatible `stream=True`，按 delta 产出文本片段。
2. 在 AdminApp 增加智能问答事件流：标准化 `meta`、`step`、`delta`、`done`、`error` 事件。
3. 增加 `POST /api/assistant/chat-stream`，返回 `text/event-stream`。
4. 事件 trace 固定为首版基础链路：`输入问题 -> 向量检索 -> 命中 FAQ -> 生成回答`。
5. `meta` 事件预留可编排信息：`flow_id`、`flow_name`、`available_nodes`，后续 KG、意图识别、混合检索节点通过该结构扩展。
6. 替换智能问答占位页为三栏布局：历史栏、聊天区、右侧调试抽屉。
7. 前端使用 `fetch` + `ReadableStream` 消费 SSE，默认所有问答走流式。
8. 前端将对话历史存入 `localStorage`，当前会话的消息、来源和 trace 可以切换查看。
9. 右侧抽屉默认打开，可收起；节点详情只展示必要信息，保持工具型简洁。
10. 补静态结构测试和后端事件流测试，再实现代码。

## 预期效果

- 用户进入智能问答后直接看到历史列表、聊天区和调试抽屉，不再是占位页。
- 发送问题后，回答内容逐段出现，不等待完整模型结果。
- 右侧可以看到本次执行到了哪个节点、命中了哪些 FAQ、分数和来源摘要。
- 后续增加 KG、意图识别、混合检索或自定义编排时，不需要重做页面骨架。

## UI Prompt

用于和另一个 AI 沟通 UI 布局的 prompt：

> 设计一个内部知识库管理系统的智能问答工作台，参考 ChatGPT 对话界面的简洁排版，但保持后台工具型风格。页面分为三栏：左侧是对话历史管理栏，包含新建对话、搜索历史和会话列表；中间是聊天主区域，顶部显示当前流程“基础 RAG”，中间展示用户与助手消息，底部固定输入框，默认流式输出回答；右侧是可收起的流程可视化调试抽屉，展示“输入问题、向量检索、命中 FAQ、生成回答”等节点的状态、耗时和摘要，点击或展开节点可查看命中来源、score、分类和标签。界面应克制、清晰、信息密度适中，不做拖拽编排器，只为未来 KG、意图识别和混合检索预留节点结构。

## 用户确认内容

- 用户确认首版采用三栏布局：左侧对话历史，中间聊天区，右侧流程可视化调试抽屉。
- 用户确认参考 OpenAI ChatGPT 的对话界面排版，但保持本项目后台风格。
- 用户确认默认全部使用流式传输。
- 用户提出未来要加入混合检索、KG、意图识别和自定义编排流；本次只做简单符合当前功能的版本，并预留扩展。

## 验证计划

- `conda run -n customer-service-agent python -m pytest tests/test_llm.py -q`
- `conda run -n customer-service-agent python -m pytest tests/test_admin_server.py -q`
- `conda run -n customer-service-agent python -m pytest tests/test_admin_table_layout.py -q`
- `conda run -n customer-service-agent python -m pytest -q`
- `conda run -n customer-service-agent python -m ruff check .`
- `node --check customer_service_agent/static/admin.js`
- 浏览器检查智能问答页面：三栏可见、右侧抽屉可收起、发送问题后中间消息流式增长、右侧节点状态更新。

## 实施记录

- 已为 `ChatClient` 增加 `stream_complete()`，使用 OpenAI-compatible `stream=True` 并过滤空 delta。
- 已增加 `POST /api/assistant/chat-stream`，返回 `text/event-stream`。
- 已增加智能问答基础 RAG 事件流，输出 `meta`、`step`、`delta`、`done`、`error` 事件。
- 已在 `meta.available_nodes` 中预留 `intent_detection`、`keyword_search`、`kg_query`、`rerank`、`quality_check` 等后续编排节点。
- 已将智能问答占位页替换为左侧历史、中间聊天、右侧流程调试抽屉三栏布局。
- 已用 `fetch` + `ReadableStream` 消费 SSE，默认所有智能问答请求走流式接口。
- 已用 `localStorage` 保存首版本地对话历史，未新增数据库 schema。

## 验证记录

- `conda run -n customer-service-agent python -m pytest tests/test_llm.py tests/test_admin_server.py tests/test_admin_table_layout.py -q`：73 passed。
- `conda run -n customer-service-agent python -m pytest -q`：146 passed。
- `conda run -n customer-service-agent python -m ruff check .`：All checks passed。
- `conda run -n customer-service-agent python -m customer_service_agent.cli check-config`：config ok。
- `node --check customer_service_agent/static/admin.js`：通过。
- Playwright headless 检查：
  - 智能问答三栏分别为 260px、820px、360px。
  - 模拟 SSE 后，中间聊天区显示流式回答“请等待 10 分钟后刷新。”。
  - 右侧来源数显示 1 条，trace 显示“向量检索 / 命中 1 条 FAQ”。
  - 调试抽屉收起后宽度从 360px 变为 46px。
