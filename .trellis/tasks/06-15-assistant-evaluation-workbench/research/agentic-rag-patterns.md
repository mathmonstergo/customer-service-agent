# Agentic RAG 成熟项目调研

调研时间：2026-06-15

## 调研问题

成熟项目如何定义 agentic RAG？相对普通 RAG，它们多了哪些组件？这些组件对本项目的“问答效果验收工作台”有什么影响？

## Sources

* LangGraph: https://docs.langchain.com/oss/python/langgraph/agentic-rag
* LlamaIndex RAG overview: https://docs.llamaindex.ai/en/stable/understanding/rag/
* LlamaIndex agents: https://docs.llamaindex.ai/en/stable/understanding/agent/
* Haystack agents: https://docs.haystack.deepset.ai/docs/agents
* Haystack retrievers: https://docs.haystack.deepset.ai/docs/retrievers
* Dify Agent node: https://docs.dify.ai/en/guides/workflow/node/agent
* AutoGen AgentChat agents: https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/tutorial/agents.html
* CrewAI agents: https://docs.crewai.com/concepts/agents

## 普通 RAG 的共同定义

普通 RAG 通常是固定流水线：资料加载、切分/索引、用户 query 检索、把相关上下文交给 LLM 生成答案。

LlamaIndex 的 RAG overview 把 RAG 解释为：用户查询作用在 index 上，index 过滤出最相关 context，然后 context、query 和 prompt 一起交给 LLM 生成回答。它也把 RAG 拆为 Loading、Indexing、Storing、Querying、Evaluation 五个阶段，并强调 retriever、router、postprocessor、response synthesizer 等组件。

Haystack 的 retriever 文档也采用类似口径：retriever 从 Document Store 里选择匹配 query 的文档，为每个文档分配相关性分数并返回 top candidates。它把普通检索细分为 BM25/keyword、dense embedding、sparse embedding、hybrid retrieval、multi-query retrieval 等策略。

结论：普通 RAG 的核心被评估对象主要是“给定 query，检索出了什么、分数如何、最终回答是否使用这些上下文”。它通常不是自主决定是否检索、是否换工具、是否循环重试。

## Agentic RAG 的共同定义

agentic RAG 的核心不是某一种检索算法，而是把 RAG 作为 agent 可调用的工具或动作，放进一个由 LLM 驱动的决策循环里。agent 会根据任务状态决定是否检索、调用哪个工具、如何构造检索 query、是否需要重写问题、是否继续下一步，直到满足停止条件或达到迭代上限。

### LangGraph

LangGraph 的 custom RAG agent 教程明确说 retrieval agents 适用于“希望 LLM 决定是否从 vectorstore 检索上下文，还是直接回复用户”的场景。教程中的 agentic RAG graph 包含：

* retriever tool：把向量检索封装为工具。
* generate_query_or_respond：LLM 决定调用检索工具还是直接回复。
* grade_documents：用结构化输出判断检索文档是否相关。
* rewrite_question：文档不相关时改写原始问题。
* generate_answer：相关时基于检索上下文生成答案。
* conditional edges：根据 tool_calls、相关性评分等条件路由到不同节点。

这代表一种成熟 agentic RAG 结构：检索不是必经步骤，而是工具调用；失败后不是直接无命中，而是可以进入问题改写和再次检索。

### LlamaIndex

LlamaIndex 对 agent 的定义是：由 LLM 驱动的半自主软件，接受任务后执行一系列步骤；它拥有一组 tools，这些 tools 可以是普通函数，也可以是完整的 LlamaIndex query engines；每一步 agent 选择最合适的工具，完成后判断任务是否结束，否则回到循环开始。

映射到 RAG：query engine / retriever 不再只是固定链路节点，而是 agent 工具箱中的一个工具。agentic RAG 因而需要记录“选择了哪个 query engine、为何选择、输入参数是什么、结果是否足够、是否继续下一步”。

### Haystack

Haystack agent 文档把 AI agent 定义为能够理解输入、检索信息、生成回复、执行动作的系统，并强调它比 chatbot 多了主动规划、选择工具、执行任务、根据新信息调整过程的能力。Haystack 的 Agent component 管理完整 tool-calling loop：调用 LLM、调用工具、更新 state、直到停止条件满足。

Haystack 的 tools 体系可以把 Python function、Haystack component、完整 pipeline、MCP server 暴露成工具。对 RAG 来说，retriever 或 retrieval pipeline 可以被包装成 tool，成为 agent 循环的一部分。

### Dify

Dify 的 Agent node 描述为“给 LLM 对工具的自主控制权”，让模型迭代决定使用哪些工具以及何时使用。它支持 Function Calling 和 ReAct 两类策略；ReAct 采用 Thought -> Action -> Observation 循环。Dify 明确暴露最大迭代次数、memory、final answer、tool outputs、reasoning trace、iteration count、success status、agent logs 等输出。

这说明低代码平台也把 agentic 能力产品化为“策略、工具配置、迭代上限、记忆、轨迹和日志”，而不是只提供一次检索结果。

### AutoGen / CrewAI

AutoGen 的 AssistantAgent 是内置 agent，可以使用 tools；一次 run 会保存 messages，其中包含 ToolCallRequestEvent、ToolCallExecutionEvent、ToolCallSummaryMessage 等“思考过程”和最终响应。它还支持 workbench、agent-as-tool、parallel tool calls、max_tool_iterations、structured output。

CrewAI 的 Agent 以 role、goal、tools、memory、reasoning、max_iter、knowledge_sources 等参数为核心。它把 RagTool / knowledge_sources 作为处理大资料和领域知识的推荐方式，同时支持 step_callback 观察每一步。

这类多 agent 框架说明：agentic RAG 常常还会扩展到多 agent 协作、agent-as-tool、任务委派、长期/短期记忆、工具执行缓存和轨迹回放。

## 相对普通 RAG 多出的组件

1. Planner / tool selector：决定是否检索、调用哪个检索器或业务工具。
2. Tool registry / schema：把 retriever、query engine、API、数据库查询、MCP server 等暴露为可调用工具。
3. Query generation / rewrite / expansion：把用户问题转换为更适合工具或检索器的参数，失败后可改写重试。
4. Router / strategy selection：在 FAQ、文档切片、知识图谱、外部 API、不同 retriever 之间选择或并行调用。
5. Relevance grader / self-checker：判断检索结果是否相关、是否足以回答、是否需要继续检索。
6. Iterative loop / stopping condition：支持多步 Thought/Action/Observation 或 tool iteration，并需要最大迭代次数、停止原因和失败原因。
7. State / memory：保存对话上下文、工具中间结果、跨步骤状态和长期知识。
8. Action execution：不仅检索，还可能调用业务 API、数据库、HTTP、代码执行、人工确认。
9. Observability trace：记录每一步模型决策、工具调用参数、工具输出、错误、耗时、token、最终答案。
10. Human-in-the-loop / guardrails：对高风险工具调用、敏感信息、权限边界进行拦截或人工审核。

## 对本项目评测工作台的影响

当前 MVP 仍应做“检索评测工作台”，不实现 agentic planner / tool loop。原因是已有后端能力和数据库表都围绕 `retrieval_eval_cases`、单条 run、hybrid retrieval 指标展开，先把标准问题集、期望命中、Recall@K、MRR、Top1 hit 跑通，能最快服务知识库验收。

但页面和数据命名应避免写死为“只有向量检索”：

* run 结果建议保留 `strategy` / `run_type` 口径，例如 `retrieval_hybrid_v1`，未来可扩展为 `agentic_rag_v1`。
* UI 可称为“运行策略”或“评测类型”，不要只叫“向量策略”。
* 运行详情可以先展示 query analysis、query rewrite、vector/keyword 候选、score、retrieval_channels；未来同一详情区域可追加 tool calls、reasoning trace、iteration count、stopping reason。
* 当前第一版只做单条运行。批量运行全部 active 用例可以后置，因为它还需要队列/并发、失败重试、运行汇总和批量进度状态。
* 第一版的评价指标聚焦 retrieval correctness：expected source/chunk hit、Recall@K、MRR、Top1 hit、失败类型。未来 agentic 指标可追加 tool selection correctness、tool argument correctness、retrieval retry effectiveness、grounded answer score、policy/guardrail outcome。

## 建议收敛

推荐继续采用当前 PRD 的 Approach A：检索评测工作台。

MVP 不做 agentic 执行器，但在字段和页面文案上预留“运行策略/运行轨迹”的扩展点。这样第一版不会被 agentic 范围拖大，同时不会把后续 agentic RAG 评测锁死在普通检索模型里。
