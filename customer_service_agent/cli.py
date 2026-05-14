from __future__ import annotations

import argparse
import json
import sys

from customer_service_agent.config import Settings
from customer_service_agent.db import Database
from customer_service_agent.faq_loader import import_faqs
from customer_service_agent.llm import ChatClient, EmbeddingClient
from customer_service_agent.rag import RagService, load_system_prompt
from customer_service_agent.rag_tool import RagTool


def build_parser() -> argparse.ArgumentParser:
    """构建命令行入口，约束是只暴露本地维护需要的受控命令。"""
    parser = argparse.ArgumentParser(prog="customer-service-agent")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check-config")
    sub.add_parser("init-db")
    sub.add_parser("sync-knowledge-chunks")
    import_parser = sub.add_parser("import-faq")
    import_parser.add_argument("--path", default="data/faqs.jsonl")
    search_parser = sub.add_parser("search")
    search_parser.add_argument("question", nargs="?")
    ask_parser = sub.add_parser("ask")
    ask_parser.add_argument("question", nargs="?")
    tool_search_parser = sub.add_parser("tool-search")
    tool_search_parser.add_argument("question", nargs="?")
    tool_answer_parser = sub.add_parser("tool-answer")
    tool_answer_parser.add_argument("question", nargs="?")
    sub.add_parser("wechat-login")
    sub.add_parser("wechat-service")
    admin_parser = sub.add_parser("admin")
    admin_parser.add_argument("--host", default="127.0.0.1")
    admin_parser.add_argument("--port", type=int, default=8765)
    return parser


def build_rag(settings: Settings) -> RagService:
    return RagService(
        embeddings=EmbeddingClient.from_settings(settings),
        db=Database(settings.database_url),
        chat=ChatClient.from_settings(settings),
        system_prompt=load_system_prompt(),
        top_k=settings.rag_top_k,
        min_score=settings.rag_min_score,
    )


def build_rag_tool(settings: Settings) -> RagTool:
    return RagTool(
        embeddings=EmbeddingClient.from_settings(settings),
        db=Database(settings.database_url),
        chat=ChatClient.from_settings(settings),
        system_prompt=load_system_prompt(),
        top_k=settings.rag_top_k,
        min_score=settings.rag_min_score,
    )


def print_json(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    """执行 CLI 命令，所有数据库写入都走 Database 封装。"""
    args = build_parser().parse_args(argv)
    settings = Settings.load()

    if args.command == "check-config":
        print("config ok")
        return 0
    if args.command == "init-db":
        Database(settings.database_url).init_schema()
        print("database schema ok")
        return 0
    if args.command == "sync-knowledge-chunks":
        count = Database(settings.database_url).sync_ready_faq_knowledge_chunks()
        print(f"synced {count} ready faq knowledge chunks")
        return 0
    if args.command == "import-faq":
        count = import_faqs(
            args.path,
            Database(settings.database_url),
            EmbeddingClient.from_settings(settings),
        )
        print(f"imported {count} faq rows")
        return 0
    if args.command == "search":
        question = args.question or input("question: ")
        embedding = EmbeddingClient.from_settings(settings).embed(question)
        docs = Database(settings.database_url).search(
            embedding,
            top_k=settings.rag_top_k,
            min_score=settings.rag_min_score,
        )
        for doc in docs:
            print(f"{doc.score:.2f} {doc.id} {doc.question}")
        return 0
    if args.command == "ask":
        question = args.question or input("question: ")
        print(build_rag(settings).answer(question))
        return 0
    if args.command == "tool-search":
        question = args.question or input("question: ")
        print_json(build_rag_tool(settings).search(question).to_dict())
        return 0
    if args.command == "tool-answer":
        question = args.question or input("question: ")
        print_json(build_rag_tool(settings).answer(question).to_dict())
        return 0
    if args.command == "wechat-login":
        from customer_service_agent.wechat_service import login_wechat

        login_wechat(settings)
        return 0
    if args.command == "wechat-service":
        from customer_service_agent.wechat_service import run_service

        run_service(settings)
        return 0
    if args.command == "admin":
        from customer_service_agent.admin_server import run_admin_server

        run_admin_server(settings, host=args.host, port=args.port)
        return 0

    raise AssertionError(f"Unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
