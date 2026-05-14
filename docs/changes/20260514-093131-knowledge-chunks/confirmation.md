# 用户确认记录

- 确认时间：2026-05-14 09:31 Asia/Shanghai
- 用户要求：参考 Dify、Langchain、Coze 一类平台化知识库的方式做表，核心抽象为统一可检索知识单元 `knowledge_chunks`，支持 FAQ、文档、网页、数据库等来源，并为后续混合检索、rerank 和 LLM 生成回答做准备。
- 本次执行边界：先新增统一表结构和数据库映射能力，不改变当前 FAQ RAG 的线上检索链路。
