"""MCP server：把 KB 的 search/answer 暴露给上游 agent。

设计要点：
- transport 仅做 stdio（Claude Desktop / 多数 agent CLI 通用）
- search 一次性返回融合 + rerank 后的候选 chunk
- answer 通过 progress notification 流式推送 delta，最后 tool result 返回完整答案 + 来源
- 每次调用复用 Database.record_query_event 打点；失败不影响主链路
- requester 身份优先级：tool args > env (MCP_REQUESTER_TYPE/ID) > 默认 ("mcp", None)
- stdio 协议通道占用 stdout，日志全部走 stderr；禁止 print()
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Callable, Mapping

import mcp.types as mcp_types
from mcp.server.lowlevel import Server

from customer_service_agent.config import Settings
from customer_service_agent.db import Database
from customer_service_agent.llm import ChatClient, EmbeddingClient
from customer_service_agent.rag import load_system_prompt
from customer_service_agent.rag_tool import RagTool


logger = logging.getLogger(__name__)


MCP_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "search",
        "description": "在企业知识库做混合检索（向量 + 关键词 + 可选 rerank），返回 top_k 候选 chunk 与来源信息。不生成最终回答。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "用户问题原文，建议直接传 agent 收到的查询字符串。",
                },
                "requester_type": {
                    "type": "string",
                    "description": "调用方类型，比如 agent / writer-bot / analyst；写入查询打点供后台看板分析。",
                },
                "requester_id": {
                    "type": "string",
                    "description": "调用方 ID。例如 agent 实例名 / 用户 ID。",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "answer",
        "description": "在企业知识库做混合检索后，让模型流式生成最终回答；通过 progress notification 推送 delta，最后返回完整答案与来源。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "用户问题原文。",
                },
                "system_prompt": {
                    "type": "string",
                    "description": "可选会话级系统提示词，覆盖 KB 默认提示词。",
                },
                "requester_type": {"type": "string"},
                "requester_id": {"type": "string"},
            },
            "required": ["query"],
        },
    },
]


def resolve_requester(
    args: Mapping[str, Any],
    *,
    env: Mapping[str, str] | None = None,
) -> tuple[str, str | None]:
    """解析 requester 身份；args > env > 默认 ('mcp', None)。"""
    env = env if env is not None else os.environ
    requester_type = str(args.get("requester_type") or "").strip()
    requester_id_raw = args.get("requester_id")
    requester_id = str(requester_id_raw).strip() if requester_id_raw else ""

    if not requester_type:
        requester_type = str(env.get("MCP_REQUESTER_TYPE") or "").strip()
    if not requester_id:
        requester_id = str(env.get("MCP_REQUESTER_ID") or "").strip()

    return (requester_type or "mcp", requester_id or None)


def _record_event(database: Any, event: dict[str, Any]) -> None:
    """打点写入失败仅记 warning，主路径不受影响。"""
    record = getattr(database, "record_query_event", None)
    if record is None:
        return
    try:
        record(event)
    except Exception as exc:
        logger.warning("mcp record_query_event failed: %s", exc, exc_info=True)


async def handle_search(
    args: Mapping[str, Any],
    *,
    rag_tool: Any,
    database: Any,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """search 工具业务逻辑：调 rag_tool.search → 打点 → 返回结构化结果。"""
    query = str(args.get("query") or "").strip()
    if not query:
        raise ValueError("search tool requires non-empty 'query'")

    requester_type, requester_id = resolve_requester(args, env=env)

    result = rag_tool.search(query)
    payload = result.to_dict() if hasattr(result, "to_dict") else dict(result)
    documents = payload.get("documents") or []
    top_score = payload.get("top_score")
    hit_count = len(documents)
    chunk_ids = [str(doc.get("id") or "") for doc in documents if doc.get("id")]

    _record_event(
        database,
        {
            "query": query,
            "intent": None,
            "retrieved_chunk_ids": chunk_ids,
            "top_score": top_score,
            "hit_count": hit_count,
            "rerank_used": False,
            "latency_ms": None,
            "requester_type": requester_type,
            "requester_id": requester_id,
            "metadata": {"flow": "mcp_search"},
        },
    )

    return {
        "query": query,
        "documents": documents,
        "top_score": top_score,
        "hit_count": hit_count,
        "top_k": payload.get("top_k"),
        "min_score": payload.get("min_score"),
    }


async def handle_answer(
    args: Mapping[str, Any],
    *,
    rag_tool: Any,
    database: Any,
    env: Mapping[str, str] | None = None,
    session: Any | None = None,
    progress_token: str | int | None = None,
) -> dict[str, Any]:
    """answer 工具业务逻辑：流式生成回答，逐 delta 通过 progress notification 推送。"""
    query = str(args.get("query") or "").strip()
    if not query:
        raise ValueError("answer tool requires non-empty 'query'")

    requester_type, requester_id = resolve_requester(args, env=env)

    final_payload: dict[str, Any] | None = None
    progress = 0.0

    for event in rag_tool.stream_answer(query):
        if event.get("type") == "delta":
            text = str(event.get("text") or "")
            progress += 1
            if session is not None and progress_token is not None and text:
                try:
                    await session.send_progress_notification(
                        progress_token=progress_token,
                        progress=progress,
                        total=None,
                        message=text,
                    )
                except Exception as exc:
                    logger.warning("mcp progress notification failed: %s", exc, exc_info=True)
        elif event.get("type") == "final":
            final_payload = dict(event)

    if final_payload is None:
        final_payload = {
            "answer_draft": "",
            "documents": [],
            "top_score": None,
            "hit_count": 0,
            "top_k": None,
            "min_score": None,
            "has_context": False,
        }

    documents = final_payload.get("documents") or []
    chunk_ids = [str(doc.get("id") or "") for doc in documents if doc.get("id")]

    _record_event(
        database,
        {
            "query": query,
            "intent": None,
            "retrieved_chunk_ids": chunk_ids,
            "top_score": final_payload.get("top_score"),
            "hit_count": int(final_payload.get("hit_count") or 0),
            "rerank_used": False,
            "latency_ms": None,
            "requester_type": requester_type,
            "requester_id": requester_id,
            "metadata": {"flow": "mcp_answer"},
        },
    )

    return {
        "query": query,
        "answer": final_payload.get("answer_draft", ""),
        "documents": documents,
        "top_score": final_payload.get("top_score"),
        "hit_count": int(final_payload.get("hit_count") or 0),
        "top_k": final_payload.get("top_k"),
        "min_score": final_payload.get("min_score"),
    }


def build_mcp_server(
    *,
    settings: Any,
    rag_tool_factory: Callable[[], Any],
    database_factory: Callable[[], Any],
    env: Mapping[str, str] | None = None,
) -> Server:
    """构造 MCP server 实例，把工具 handler 挂到 SDK 装饰器上。"""
    server: Server = Server("customer-service-kb")

    @server.list_tools()
    async def list_tools() -> list[mcp_types.Tool]:
        return [
            mcp_types.Tool(
                name=tool["name"],
                description=tool["description"],
                inputSchema=tool["inputSchema"],
            )
            for tool in MCP_TOOL_DEFINITIONS
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[mcp_types.ContentBlock]:
        rag_tool = rag_tool_factory()
        database = database_factory()
        session = None
        progress_token = None
        try:
            ctx = server.request_context
            session = ctx.session
            meta = getattr(ctx, "meta", None)
            progress_token = getattr(meta, "progressToken", None) if meta else None
        except Exception:
            session = None
            progress_token = None

        if name == "search":
            payload = await handle_search(arguments, rag_tool=rag_tool, database=database, env=env)
        elif name == "answer":
            payload = await handle_answer(
                arguments,
                rag_tool=rag_tool,
                database=database,
                env=env,
                session=session,
                progress_token=progress_token,
            )
        else:
            raise ValueError(f"unknown tool: {name}")

        text = json.dumps(payload, ensure_ascii=False, indent=2)
        return [mcp_types.TextContent(type="text", text=text)]

    return server


def _default_rag_tool_factory(settings: Settings) -> Callable[[], RagTool]:
    def factory() -> RagTool:
        embeddings = EmbeddingClient.from_settings(settings)
        chat = ChatClient.from_settings(settings)
        db = Database(settings.database_url)
        try:
            system_prompt = load_system_prompt()
        except FileNotFoundError:
            system_prompt = ""
        return RagTool(
            embeddings=embeddings,
            db=db,
            chat=chat,
            system_prompt=system_prompt,
            top_k=settings.rag_top_k,
            min_score=settings.rag_min_score,
        )

    return factory


def _default_database_factory(settings: Settings) -> Callable[[], Database]:
    def factory() -> Database:
        return Database(settings.database_url)

    return factory


def run_stdio(settings: Settings) -> None:
    """启动 MCP stdio server；阻塞直到客户端断开。

    关键约束：stdout 是 MCP 协议通道，不能写日志或 print；本函数把 logging
    显式配置到 stderr，避免污染协议流。
    """
    import anyio
    from mcp.server.stdio import stdio_server

    logging.basicConfig(
        stream=__import__("sys").stderr,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    server = build_mcp_server(
        settings=settings,
        rag_tool_factory=_default_rag_tool_factory(settings),
        database_factory=_default_database_factory(settings),
        env=os.environ,
    )

    async def _serve() -> None:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )

    anyio.run(_serve)
