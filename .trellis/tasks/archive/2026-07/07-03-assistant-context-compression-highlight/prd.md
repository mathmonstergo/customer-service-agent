# 智能问答上下文压缩和定位高亮

## Goal

把智能问答从“单轮 RAG 问答”升级为简版多轮问答：同一会话内后续问题能参考最近对话和压缩摘要，同时保持 RAG 项目本身轻量、可作为其他 agent 的工具调用；并优化聊天界面定位体验，点击右侧问题定位或来源标签后滚动到对应位置并短暂高亮。

## What I already know

* 用户希望实现“有上下文 + 上下文压缩”的简版问答，最新要求改为参考本地 `/home/adam/GenericAgent` 项目的上下文管理。
* GenericAgent 的核心模式是每轮注入 `### [WORKING MEMORY]`，用 `<history>` 保留近期 `[USER]` / `[Agent]` 短历史，用 `<earlier_context>` 折叠更早内容，不引入跨任务长期记忆。
* 用户明确后续这个 RAG 会作为其他 agent 的工具，因此本项目只做简单问答能力，不做复杂 agent 记忆系统。
* 官方 Codex manual 描述了线程上下文、上下文窗口，以及长任务中通过 compact 总结相关信息并丢弃较不相关细节来继续工作；也区分了长期 memories 和线程内上下文。
* 当前后端 `/api/assistant/chat-stream` 只接收当前 `question` 和可选会话级 provider，后端 `build_user_prompt(question, docs)` 只拼当前问题和当前检索来源。
* 当前 `ChatClient` 只发送 system prompt + 单条 user prompt，没有历史 messages。
* 当前前端会话消息存在 Zustand localStorage 中，`useChatStream` 可以在发送时读取当前会话历史。
* 当前右侧消息导航调用 `scrollToMessage(id)` 只滚动，不高亮。
* 当前来源 chips 只调用 `setDebugDrawerOpen(true)`，右侧流程抽屉只展示最近一次 assistant 消息的全部 sources，没有目标 source，也不会滚动到具体 SourceCard。

## Requirements

* 同一会话内发送问题时，payload 需要携带简版对话上下文。
* 上下文只用于当前请求 prompt，不进入数据库，不作为长期记忆，不跨会话共享。
* 上下文压缩采用轻量策略：保留最近若干轮原文，较早消息压缩成一段摘要。
* 第一版压缩可在前端发送前完成，避免新增后端持久化和后台压缩任务。
* 后端需要接受上下文字段，并把“压缩摘要 + 最近对话”按 GenericAgent 风格格式化进最终 RAG prompt。
* 后端仍以当前问题做检索，不因为上下文改写检索策略，避免扩大改动面。
* 后端回答仍必须优先基于知识库来源；上下文只能帮助理解指代和连续追问。
* 点击右侧具体聊天条时，滚动到对应用户提问后，该提问 body 背景短暂高亮闪一下。
* 点击回答下方来源标签时，打开流程详情抽屉，滚动到匹配的来源卡片，并让来源卡片短暂高亮闪一下。
* 来源标签的分组行为可以保留，但点击某个分组时要定位到该分组下的第一条匹配来源。

## Acceptance Criteria

* [ ] `AssistantStreamPayload` 支持会话上下文结构，且 provider 覆盖逻辑不受影响。
* [ ] 后端 prompt 中能看到压缩摘要和最近对话，单测覆盖格式化结果。
* [ ] 发送第 N 轮问题时，前端会带上最近对话和早期摘要；没有历史时不发送无意义上下文。
* [ ] 后端安全拒答、模型失败和空回答路径仍能正常返回 SSE。
* [ ] 点击右侧问题导航能滚动到对应 user message，并在到位后短暂高亮。
* [ ] 点击来源 chip 能打开流程详情，滚动到具体来源卡片，并短暂高亮。
* [ ] 前端测试、lint、build 通过；后端相关 pytest / ruff 通过。

## Technical Approach

第一版推荐采用“前端构造简版上下文 + 后端 prompt 格式化”的路径：

* 前端在 `useChatStream` 发送前读取当前会话消息。
* 保留最近 5 轮用户/助手消息原文。
* 更早消息按角色和顺序压缩成一段短摘要，采用本地规则压缩，不额外调用模型。
* payload 新增 `conversation_context`，包含 `summary` 和 `recent_messages`。
* 后端新增纯函数格式化上下文，并把它以 `### [WORKING MEMORY]` / `<earlier_context>` / `<history>` 结构插入 `build_user_prompt`。
* UI 高亮使用短暂状态，例如 `highlightedMessageId` / `highlightedSourceKey`，配合 CSS animation 或 Framer Motion class。

## Candidate Approaches

### Approach A: 前端轻量压缩 + 后端 prompt 拼接 (Recommended)

前端发送请求时根据 Zustand 内当前会话生成上下文。后端只验证、截断并格式化进 prompt。

优点：最小改动，不增加数据库 schema，不需要后台任务，符合“RAG 作为 agent 工具”的轻量定位。
代价：摘要是启发式压缩，不如模型摘要自然；localStorage 被清理后上下文丢失。

### Approach B: 后端接收完整历史并压缩

前端发送最近完整历史，后端统一截断、摘要和格式化。

优点：上下文策略集中在后端，后续其他 agent 调用同一 API 时更一致。
代价：payload 更大，后端逻辑更多；如果要模型压缩会引入额外模型调用和失败路径。

### Approach C: 持久化会话摘要

把会话摘要保存到后端或前端 store，随着每轮回答增量更新。

优点：多轮体验更强，后续可扩展成长期任务上下文。
代价：更接近 memory 系统，需要持久化、更新时机、隐私和清理策略，不符合当前“简单版”目标。

## Recommendation

采用 Approach A。它和 GenericAgent 的上下文管理思想一致：保留近期高价值原文，旧内容折叠成摘要，避免上下文窗口被完整 transcript 占满；但不实现 GenericAgent 的长期记忆、working checkpoint 工具或全局 memory 注入。

## Out of Scope

* 不做跨会话长期记忆。
* 不新增数据库 schema 保存对话历史或摘要。
* 不引入 LangChain / agent framework / tool calling 编排。
* 不默认把整段历史用于检索改写或实体记忆。
* 不做模型驱动的摘要压缩任务。
* 不改变知识库导入、KG、评测工作台主流程。

## Definition of Done

* 用户确认 MVP 方案和边界：采用方案 A，最近 5 轮保留原文。
* `docs/changes/20260703-assistant-context-compression-highlight/` 记录计划和确认。
* 后端新增或更新单测覆盖 prompt 上下文格式化。
* 前端新增或更新测试覆盖上下文 payload 构造和高亮目标选择逻辑。
* `conda run -n customer-service-agent python -m pytest ...`、`ruff check`、`pnpm test`、`pnpm lint`、`pnpm build` 通过。
* 完成后提交 git commit。

## Technical Notes

* 可能修改：
  * `customer_service_agent/rag.py`
  * `customer_service_agent/admin_server.py`
  * `tests/test_admin_server.py` 或 `tests/test_rag.py`
  * `web/src/api/schemas.ts`
  * `web/src/pages/assistant/use-chat-stream.ts`
  * `web/src/pages/assistant/message-stream.tsx`
  * `web/src/pages/assistant/debug-drawer.tsx`
  * 新增前端 helper/test 文件
* GenericAgent 参考：
  * `/home/adam/GenericAgent/ga.py` `_get_anchor_prompt()`：注入 `### [WORKING MEMORY]`、`<earlier_context>`、`<history>`。
  * `/home/adam/GenericAgent/ga.py` `_fold_earlier()`：把更早历史折叠成较短的上下文。
  * `/home/adam/GenericAgent/ga.py` `turn_end_callback()`：把 assistant 输出压成 `[Agent] <summary>`。
  * `/home/adam/GenericAgent/assets/tools_schema.json` `update_working_checkpoint`：说明 working memory 是短期 notepad，本任务不实现该工具。
