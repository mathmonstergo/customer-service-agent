from __future__ import annotations

import json
import mimetypes
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from customer_service_agent.ai_assist import AiAssistant, AiSuggestionError
from customer_service_agent.config import Settings
from customer_service_agent.db import Database
from customer_service_agent.llm import ChatClient, EmbeddingClient


class AdminValidationError(ValueError):
    pass


class AdminNotFoundError(KeyError):
    pass


VALID_FAQ_STATUSES = {"usable", "needs_review", "disabled"}


def split_text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value)
    separators = [",", "，", "\n", "；", ";"]
    for separator in separators[1:]:
        text = text.replace(separator, separators[0])
    return [item.strip() for item in text.split(separators[0]) if item.strip()]


def normalize_faq_payload(payload: dict[str, Any]) -> dict[str, Any]:
    question = str(payload.get("question", "")).strip()
    answer = str(payload.get("answer", "")).strip()
    if not question:
        raise AdminValidationError("question is required")
    if not answer:
        raise AdminValidationError("answer is required")

    faq_id = str(payload.get("id", "")).strip() or f"faq_{uuid.uuid4().hex[:12]}"
    return {
        "id": faq_id,
        "doc_type": str(payload.get("doc_type", "faq_qa")).strip() or "faq_qa",
        "source_file": payload.get("source_file"),
        "source_group": payload.get("source_group"),
        "source_date": payload.get("source_date"),
        "category": str(payload.get("category", "") or "").strip() or None,
        "question": question,
        "question_variants": split_text_list(payload.get("question_variants")),
        "answer": answer,
        "tags": split_text_list(payload.get("tags")),
        "evidence": payload.get("evidence", []),
        "confidence": str(payload.get("confidence", "high")).strip() or "high",
        "status": str(payload.get("status", "usable")).strip() or "usable",
        "sensitivity": payload.get("sensitivity"),
    }


def jsonable(value: Any) -> Any:
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [jsonable(item) for item in value]
    return value


@dataclass
class AdminApp:
    settings: Settings
    db: Database | None = None
    embeddings: EmbeddingClient | None = None
    chat: ChatClient | None = None

    def database(self) -> Database:
        if self.db is None:
            self.db = Database(self.settings.database_url)
        return self.db

    def embedding_client(self) -> EmbeddingClient:
        if self.embeddings is None:
            self.embeddings = EmbeddingClient.from_settings(self.settings)
        return self.embeddings

    def chat_client(self) -> ChatClient:
        if self.chat is None:
            self.chat = ChatClient.from_settings(self.settings)
        return self.chat

    def list_faqs(self, params: dict[str, list[str]]) -> dict[str, Any]:
        page = max(int(params.get("page", ["1"])[0]), 1)
        page_size = min(max(int(params.get("page_size", ["10"])[0]), 1), 100)
        data = self.database().list_faqs(
            query=params.get("query", [""])[0],
            status=params.get("status", [""])[0] or None,
            embedding_status=params.get("embedding_status", [""])[0] or None,
            limit=page_size,
            offset=(page - 1) * page_size,
        )
        data["page"] = page
        data["page_size"] = page_size
        return data

    def get_faq(self, faq_id: str) -> dict[str, Any]:
        row = self.database().get_faq(faq_id)
        if row is None:
            raise AdminNotFoundError(f"FAQ not found: {faq_id}")
        return row

    def save_faq(self, payload: dict[str, Any]) -> dict[str, Any]:
        row = normalize_faq_payload(payload)
        return self.database().save_faq_text(row)

    def batch_update_status(self, payload: dict[str, Any]) -> dict[str, Any]:
        """批量切换 FAQ 状态，只接受明确选择的 id 和受控状态值。"""
        raw_ids = payload.get("ids", [])
        if not isinstance(raw_ids, list):
            raise AdminValidationError("ids must be a list")
        ids = [str(item).strip() for item in raw_ids if str(item).strip()]
        if not ids:
            raise AdminValidationError("ids is required")

        status = str(payload.get("status", "")).strip()
        if status not in VALID_FAQ_STATUSES:
            raise AdminValidationError("status must be usable, needs_review, or disabled")

        rows = self.database().update_faq_statuses(ids, status)
        return {"count": len(rows), "items": rows}

    def embed_faq(self, faq_id: str) -> dict[str, Any]:
        row = self.get_faq(faq_id)
        try:
            embedding_client = self.embedding_client()
            vector = embedding_client.embed(row["embedding_text"])
            return self.database().update_faq_embedding(
                faq_id,
                vector,
                embedding_model=embedding_client.model,
                embedding_dimensions=embedding_client.dimensions,
            )
        except Exception as exc:
            return self.database().mark_embedding_failed(faq_id, str(exc))

    def embed_pending(self, payload: dict[str, Any]) -> dict[str, Any]:
        limit = min(max(int(payload.get("limit", 50)), 1), 200)
        results = []
        for row in self.database().list_embedding_candidates(limit=limit):
            results.append(self.embed_faq(row["id"]))
        return {"count": len(results), "items": results}

    def optimize(self, payload: dict[str, Any]) -> dict[str, Any]:
        question = str(payload.get("question", "")).strip()
        answer = str(payload.get("answer", "")).strip()
        if not question:
            raise AdminValidationError("question is required")
        if not answer:
            raise AdminValidationError("answer is required")
        return AiAssistant(self.chat_client()).optimize(question, answer).to_dict()


def static_path(path: str) -> Path:
    static_dir = Path(__file__).with_name("static")
    if path in {"", "/"}:
        return static_dir / "admin.html"
    clean = unquote(path).lstrip("/")
    if clean not in {"admin.css", "admin.js"}:
        raise AdminNotFoundError(path)
    return static_dir / clean


def make_handler(app: AdminApp):
    class AdminHandler(BaseHTTPRequestHandler):
        server_version = "CustomerServiceAgentAdmin/0.1"

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            try:
                if parsed.path == "/favicon.ico":
                    self.send_response(HTTPStatus.NO_CONTENT)
                    self.end_headers()
                    return
                if parsed.path.startswith("/api/faqs/"):
                    faq_id = parsed.path.removeprefix("/api/faqs/")
                    self.send_json(app.get_faq(faq_id))
                    return
                if parsed.path == "/api/faqs":
                    self.send_json(app.list_faqs(parse_qs(parsed.query)))
                    return
                self.send_static(static_path(parsed.path))
            except Exception as exc:
                self.send_error_json(exc)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            try:
                payload = self.read_json()
                if parsed.path == "/api/faqs":
                    self.send_json(app.save_faq(payload))
                    return
                if parsed.path == "/api/faqs/batch-status":
                    # 批量状态接口只处理用户显式勾选的 FAQ。
                    self.send_json(app.batch_update_status(payload))
                    return
                if parsed.path == "/api/faqs/embed-pending":
                    self.send_json(app.embed_pending(payload))
                    return
                if parsed.path == "/api/ai/optimize":
                    self.send_json(app.optimize(payload))
                    return
                if parsed.path.startswith("/api/faqs/") and parsed.path.endswith("/embed"):
                    faq_id = parsed.path.removeprefix("/api/faqs/").removesuffix("/embed")
                    self.send_json(app.embed_faq(faq_id))
                    return
                raise AdminNotFoundError(parsed.path)
            except Exception as exc:
                self.send_error_json(exc)

        def read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            if length == 0:
                return {}
            raw = self.rfile.read(length).decode("utf-8")
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise AdminValidationError("request body must be valid JSON") from exc
            if not isinstance(payload, dict):
                raise AdminValidationError("request body must be a JSON object")
            return payload

        def send_static(self, path: Path) -> None:
            if not path.exists():
                raise AdminNotFoundError(str(path))
            content = path.read_bytes()
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def send_json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
            content = json.dumps(jsonable(payload), ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def send_error_json(self, exc: Exception) -> None:
            if isinstance(exc, AdminNotFoundError):
                status = HTTPStatus.NOT_FOUND
            elif isinstance(exc, AdminValidationError | AiSuggestionError):
                status = HTTPStatus.BAD_REQUEST
            else:
                status = HTTPStatus.INTERNAL_SERVER_ERROR
            self.send_json({"error": str(exc)}, status=status)

        def log_message(self, format: str, *args: Any) -> None:
            return

    return AdminHandler


def run_admin_server(settings: Settings, *, host: str, port: int) -> None:
    app = AdminApp(settings)
    app.database().init_schema()
    server = HTTPServer((host, port), make_handler(app))
    print(f"Customer Service Agent admin: http://{host}:{port}", flush=True)
    server.serve_forever()
