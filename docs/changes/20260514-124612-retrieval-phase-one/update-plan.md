# 第一阶段检索召回能力建设计划

## 背景结论

当前项目已经具备 FAQ 管理、文档导入、MinerU 解析、人工审核、统一 `knowledge_chunks` 表和基础向量检索能力。对照 RAGFlow、LightRAG 等项目后，主要差距不是单个模型能力，而是检索链路缺少可评测、可调参、可回放的产品化闭环。

RAGFlow 值得借鉴的是：文档解析、结构化切块、混合检索、重排、检索测试、知识图谱和流程调试被拆成可独立运行的阶段。LightRAG 值得借鉴的是：图谱索引用于实体、关系和多跳问题的召回扩展，而不是替代普通向量检索。

本项目第一阶段不直接做完整知识图谱，优先补齐“检索评测中心 + 意图识别层 + 混合召回 + 重排预留”的基础能力。这样可以先证明召回质量提升，再进入父子 chunk 和轻量 KG。

完整调研结论已沉淀到本目录的 `research-notes.md`，后续继续开发时优先读取该文件，不需要重新从 RAGFlow、LightRAG 等项目开始调查。

## 修改目标

第一阶段目标是把当前“单路向量召回”升级为“可解释、可评测、可逐步增强”的检索链路。

核心目标：

1. 建立检索评测数据模型，支持记录测试问题、期望命中知识、问题类型和评测结果。
2. 增加轻量意图识别层，把用户问题分为 FAQ 精准问答、文档说明/SOP、故障排查、实时状态询问、闲聊/无知识库问题等类型。
3. 增加混合召回接口雏形，至少支持向量召回与全文/关键词召回的候选合并。
4. 在智能问答调试抽屉中展示意图识别、召回来源、融合分数和无答案判断依据。
5. 为后续父子 chunk、rerank 和知识图谱扩召回预留数据结构与链路节点。

## 影响范围

- 数据库：新增检索评测用表；可能为 `knowledge_chunks` 增加检索统计或关键词辅助字段。
- 后端检索：新增意图识别模块、混合召回模块和评测运行逻辑。
- 智能问答：在 `/api/assistant/chat-stream` 的流程中插入 query analysis / retrieval planning 节点。
- 管理后台：第一版只做最小可用的检索评测页面或接口；如果涉及 UI 布局，需要另行确认布局和交互。
- 测试：覆盖意图识别、混合召回排序、评测指标计算、智能问答事件流。

## 智能问答会话界面补充范围

用户已给出最终设计图，并确认以下 UI 口径：

1. 右侧“流程调试”是覆盖式抽屉，不参与主 grid 列宽，不挤压左侧历史和中间聊天窗口。
2. 不做 LLM 生成百分比进度条；当前后端只能拿到流式 token/文本片段，不能拿到真实完成百分比。
3. 新建对话必须先弹出会话设置弹窗，支持填写会话名称和会话级系统提示词。
4. 会话设置弹窗居中展示，底层复用已有玻璃雾化遮罩。
5. 左侧会话历史卡片 hover 时浮出铅笔按钮，点击后打开当前会话设置弹窗。
6. 会话级系统提示词随 `/api/assistant/chat-stream` 请求传给后端；为空时只回退到本地 `system_prompt.txt`，没有该文件时不再使用代码硬编码默认提示词。

## 意图识别层初步设计

需要做，但第一版应保持轻量，避免引入一个不可控的“黑盒路由器”。

建议采用规则优先、LLM 兜底的两段式：

1. 规则层：识别错误码、订单/后台实时状态、操作路径、转人工、闲聊、敏感信息等高确定性类型。
2. LLM/小模型层：只在规则不确定时输出结构化 JSON，包括 `intent`、`confidence`、`query_rewrite`、`must_not_answer_realtime`、`preferred_sources`。

第一版意图枚举建议：

- `faq_exact`：标准客服问答，优先 FAQ 和候选问法。
- `procedure`：平台使用手册、SOP、操作步骤，优先文档 chunk。
- `troubleshooting`：报错、失败、无法生成、无法登录等故障排查，扩大召回并允许多来源。
- `realtime_status`：查询实时进度、账号状态、后台处理结果，必须提示无法直接确认实时状态。
- `chitchat_or_out_of_scope`：闲聊或知识库外问题，减少无意义检索。
- `sensitive_or_forbidden`：密钥、内部配置、客户隐私等敏感问题，直接拒答或转人工。

意图识别结果不应单独决定答案，只决定检索策略、过滤条件、上下文预算和安全提示。

## 具体步骤

1. 确认第一阶段范围：先做后端能力和最小评测接口，还是同步做管理后台评测页面。
2. 写测试锁定意图识别输出结构、规则命中和未知问题兜底。
3. 新增 `retrieval.py` 或等价模块，包含 query analysis、候选召回、融合排序和评测指标。
4. 新增检索评测表和数据库读写方法。
5. 实现向量召回 + 关键词召回的混合候选合并，先用 RRF 或简单加权，保留 rerank 插槽。
6. 把智能问答流式事件从“基础 RAG”升级为“意图识别 -> 混合召回 -> 上下文构造 -> 回答生成”。
7. 增加聚焦测试和必要的手工验证记录。

## 预期效果

- 开发者能用固定测试问题验证检索修改是否提升，而不是凭感觉调参。
- 用户问题先进入意图识别，实时状态、敏感问题和闲聊不会被普通 RAG 链路误处理。
- 文档 chunk 和 FAQ 可以通过不同召回通道进入统一候选池。
- 后续增加父子 chunk、rerank、KG 时，不需要重写智能问答主链路。

## 暂不包含

- 不在第一阶段实现完整知识图谱、社区报告或多跳推理。
- 不在第一阶段重做文档切块为父子 chunk。
- 不接入新的外部向量库、ES 或 Redis。
- 不暴露公网服务；权限、审计和生产部署能力单独进入后续生产化阶段。

## 用户已确认的实施口径

1. 第一阶段先做后端检索评测和智能问答链路改造，暂不做完整管理后台 UI。
2. 意图识别第一版采用“规则优先 + Chat 模型兜底”。
3. 检索评测集第一版先支持用户手工录入真实客服问题；后续再考虑从现有 FAQ 自动生成种子用例。

## 完成记录

- 已新增 `customer_service_agent/retrieval.py`，包含轻量意图识别、Chat 模型兜底解析、RRF 候选融合和检索评测指标计算。
- 已新增 `retrieval_eval_cases` 和 `retrieval_eval_runs` 表，用于保存手工评测问题、期望命中、运行候选和指标。
- 已新增数据库关键词召回方法 `search_knowledge_text`，从 `knowledge_chunks` 的 `source_title`、`content`、`search_text` 召回候选。
- 已把智能问答事件流从单路向量检索升级为：输入问题 -> 意图识别 -> 向量化 -> 混合召回 -> 命中来源 -> 流式回答。
- 已在混合召回事件里输出向量候选数、关键词候选数、融合后候选、召回通道、融合分数、向量分数和关键词分数。
- 已新增检索评测用例的最小后端接口：`GET /api/retrieval/eval-cases`、`POST /api/retrieval/eval-cases`。
- 已记录完整调研结论到 `research-notes.md`。
- 已新增 `retrieval_aliases` 表和最小后端接口：`GET /api/retrieval/aliases`、`POST /api/retrieval/aliases`，用于人工维护标准词和别名。
- 已把关键词召回从单个 `ILIKE` 升级为“错误码识别 + 领域词抽取 + 别名词典扩展 + 多词 SQL 加权打分”。
- 已新增 `POST /api/retrieval/eval-cases/{case_id}/run`，可运行单条评测用例并把候选、意图、query terms 和 Recall/MRR 指标写入 `retrieval_eval_runs`。
- 已新增检索工作台前端入口和页面：可维护评测用例、运行单条评测、查看最近一次候选与指标、维护别名词典。
- 已增强智能问答调试抽屉：展示意图识别详情、query terms、向量/关键词候选数、召回通道、融合分数、向量分数和关键词分数。
- 已修复关键词 SQL 中 `%` 被 psycopg 当作非法占位符的问题，所有 SQL 字符串字面量通配符改为 `%%`。
- 已把智能问答右侧流程调试改为覆盖式抽屉，不再挤压左侧历史和中间聊天窗口。
- 已新增会话设置弹窗：新建对话和编辑历史会话均可设置会话名与会话级系统提示词。
- 已把会话级系统提示词透传到 `/api/assistant/chat-stream`，后端为空时仅使用本地 `system_prompt.txt` 配置。
- 已删除智能问答链路里的代码硬编码默认系统提示词；没有会话提示词和 `system_prompt.txt` 时，不发送 `system` 消息。
- 已按用户要求不实现 LLM 生成百分比进度条，仅保留流式回答和执行节点状态。

## 验证记录

- `conda run -n customer-service-agent python -m pytest tests/test_retrieval.py tests/test_db.py tests/test_admin_server.py tests/test_rag.py -q`：`54 passed`
- `conda run -n customer-service-agent python -m pytest -q`：`169 passed`
- `conda run -n customer-service-agent python -m ruff check .`：`All checks passed!`
- `conda run -n customer-service-agent python -m customer_service_agent.cli check-config`：`config ok`
- `node --check customer_service_agent/static/admin.js`：通过
- `conda run -n customer-service-agent python -m customer_service_agent.cli init-db`：`database schema ok`
- 关键词增强和评测运行补充验证：
  - `conda run -n customer-service-agent python -m pytest tests/test_retrieval.py tests/test_db.py tests/test_admin_server.py tests/test_rag.py -q`：`57 passed`
  - `conda run -n customer-service-agent python -m pytest -q`：`172 passed`
  - `conda run -n customer-service-agent python -m ruff check .`：`All checks passed!`
  - `conda run -n customer-service-agent python -m customer_service_agent.cli check-config`：`config ok`
  - `node --check customer_service_agent/static/admin.js`：通过
  - `conda run -n customer-service-agent python -m customer_service_agent.cli init-db`：`database schema ok`
- 前端接入补充验证：
  - `conda run -n customer-service-agent python -m pytest tests/test_admin_table_layout.py -q`：`47 passed`
  - `node --check customer_service_agent/static/admin.js`：通过
  - `conda run -n customer-service-agent python -m pytest tests/test_admin_server.py tests/test_retrieval.py tests/test_db.py -q`：`54 passed`
  - `conda run -n customer-service-agent python -m pytest -q`：`174 passed`
  - `conda run -n customer-service-agent python -m ruff check .`：`All checks passed!`
  - `conda run -n customer-service-agent python -m customer_service_agent.cli check-config`：`config ok`
  - 本地后台命令可启动并输出 `Customer Service Agent admin: http://127.0.0.1:8765`；当前工具环境中 Chrome MCP 缺少 X server，且 `curl` 无法访问该 PTY 会话里的监听端口，因此未完成浏览器截图验证。
- 会话界面与 `%` 占位符修复补充验证：
  - `conda run -n customer-service-agent python -m pytest tests/test_admin_table_layout.py tests/test_admin_server.py tests/test_db.py::test_search_knowledge_text_sql_escapes_percent_literals_for_psycopg tests/test_db.py::test_search_knowledge_text_sql_reads_keyword_fields -q`：`85 passed`
  - `node --check customer_service_agent/static/admin.js`：通过
  - `python3 -m http.server 8891` + Playwright headless 打开 `/admin.html`：已进入智能问答页，确认新建弹窗可输入会话名和系统提示词、编辑按钮可打开同一弹窗、右侧调试栏 computed style 为 `position: absolute` 且主 grid 为两列。静态服务器下 `/api/*` 404 属于未启动后端 API 的预期现象。
  - `conda run -n customer-service-agent python -m pytest -q`：`177 passed`
  - `conda run -n customer-service-agent python -m ruff check .`：`All checks passed!`
  - `conda run -n customer-service-agent python -m customer_service_agent.cli check-config`：`config ok`
  - `conda run -n customer-service-agent python -m customer_service_agent.cli admin --host 127.0.0.1 --port 8765`：后台已启动，`GET http://127.0.0.1:8765/admin.html` 返回页面 HTML。
  - 删除代码硬编码默认系统提示词补充验证：
    - `conda run -n customer-service-agent python -m pytest tests/test_admin_server.py::test_admin_app_assistant_system_prompt_has_no_code_default tests/test_llm.py::test_chat_client_omits_empty_system_prompt tests/test_llm.py::test_chat_client_stream_omits_empty_system_prompt -q`：`3 passed`
    - `conda run -n customer-service-agent python -m pytest -q`：`180 passed`
    - `conda run -n customer-service-agent python -m ruff check .`：`All checks passed!`
    - `conda run -n customer-service-agent python -m customer_service_agent.cli check-config`：`config ok`
    - 已重启 `http://127.0.0.1:8765/admin.html` 本地后台并确认页面 HTML 可访问。
