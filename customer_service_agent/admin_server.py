from __future__ import annotations

import json
import mimetypes
import re
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
from customer_service_agent.db import Database, build_import_candidate_faq_row
from customer_service_agent.import_ai import ImportAiAssistant, ImportCandidateError
from customer_service_agent.import_models import detect_file_type
from customer_service_agent.llm import ChatClient, EmbeddingClient
from customer_service_agent.markdown_import import chunk_messages, parse_wechat_messages


class AdminValidationError(ValueError):
    pass


class AdminNotFoundError(KeyError):
    pass


VALID_FAQ_STATUSES = {"usable", "needs_review", "disabled"}
VALID_IMPORT_PARSE_MODES = {"by_days", "by_gap"}


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


def merge_existing_faq_metadata(payload: dict[str, Any], existing: dict[str, Any] | None) -> dict[str, Any]:
    """保存 FAQ 时补齐前端未提交但会影响管理记录的旧字段。"""
    if existing is None:
        return payload
    merged = dict(payload)
    for key in ("source_file", "source_group", "source_date", "evidence", "confidence", "sensitivity"):
        if key not in merged:
            merged[key] = existing.get(key)
    return merged


def normalize_import_parse_options(payload: dict[str, Any]) -> dict[str, Any]:
    """规范化导入解析参数，天数范围固定在 1 到 7 天。"""
    parse_mode = str(payload.get("parse_mode", "by_days")).strip() or "by_days"
    if parse_mode not in VALID_IMPORT_PARSE_MODES:
        raise AdminValidationError("parse_mode must be by_days or by_gap")
    try:
        chunk_days = int(payload.get("chunk_days", 1))
    except (TypeError, ValueError) as exc:
        raise AdminValidationError("chunk_days must be an integer") from exc
    return {"parse_mode": parse_mode, "chunk_days": min(max(chunk_days, 1), 7)}


def safe_upload_name(filename: str) -> str:
    """清理上传文件名，只保留本地存储需要的安全字符。"""
    name = Path(filename).name.strip() or "upload"
    return re.sub(r"[^0-9A-Za-z._\-\u4e00-\u9fff]+", "_", name)


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
        faq_id = str(payload.get("id", "")).strip()
        existing = self.database().get_faq(faq_id) if faq_id else None
        row = normalize_faq_payload(merge_existing_faq_metadata(payload, existing))
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

    def list_import_files(self, params: dict[str, list[str]]) -> dict[str, Any]:
        """列出导入文件，供导入审核左栏使用。"""
        return self.database().list_import_files(
            query=params.get("query", [""])[0],
            status=params.get("status", [""])[0] or None,
            limit=min(max(int(params.get("limit", ["50"])[0]), 1), 100),
            offset=max(int(params.get("offset", ["0"])[0]), 0),
        )

    def create_import_file(self, filename: str, content: bytes) -> dict[str, Any]:
        """保存上传原件并按识别出的解析器处理第一期 Markdown。"""
        if not content:
            raise AdminValidationError("uploaded file is empty")
        file_type, parser = detect_file_type(filename)
        file_id = f"imp_{uuid.uuid4().hex[:12]}"
        safe_name = safe_upload_name(filename)
        upload_dir = Path(self.settings.upload_dir)
        upload_dir.mkdir(parents=True, exist_ok=True)
        stored_path = upload_dir / f"{file_id}_{safe_name}"
        stored_path.write_bytes(content)

        status = "pending" if parser != "unsupported" else "unsupported"
        record = self.database().create_import_file(
            {
                "id": file_id,
                "original_name": safe_name,
                "stored_path": str(stored_path),
                "file_type": file_type,
                "parser": parser,
                "status": status,
            }
        )
        if parser == "markdown_chat":
            return self._parse_markdown_import(record, content)
        return record

    def _parse_markdown_import(
        self,
        record: dict[str, Any],
        content: bytes,
        *,
        parse_mode: str = "by_days",
        chunk_days: int = 1,
    ) -> dict[str, Any]:
        """解析 Markdown 微信聊天记录，生成可追溯时间切块。"""
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            self.database().update_import_file_summary(record["id"], status="failed", error="文件必须是 UTF-8 编码")
            raise AdminValidationError("uploaded Markdown must be UTF-8") from exc
        messages = parse_wechat_messages(text)
        chunks = chunk_messages(messages, mode=parse_mode, days=chunk_days)
        chunk_rows = [
            {
                "id": f"chunk_{uuid.uuid4().hex[:12]}",
                "file_id": record["id"],
                "chunk_index": index,
                "start_at": chunk.start_at,
                "end_at": chunk.end_at,
                "message_count": chunk.message_count,
                "keywords": json.dumps(chunk.keywords, ensure_ascii=False),
                "source_text": chunk.text,
                "status": "pending",
                "candidate_count": 0,
            }
            for index, chunk in enumerate(chunks, start=1)
        ]
        self.database().replace_import_chunks(record["id"], chunk_rows)
        summary = self.database().update_import_file_summary(
            record["id"],
            status="needs_review",
            message_count=len(messages),
            chunk_count=len(chunk_rows),
            candidate_count=0,
            error=None,
        )
        return {**record, **summary}

    def reparse_import_file(self, file_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """按用户选择的解析参数重新切分已上传文件。"""
        record = self.database().get_import_file(file_id)
        if record is None:
            raise AdminNotFoundError(f"Import file not found: {file_id}")
        if record.get("parser") != "markdown_chat":
            raise AdminValidationError("only Markdown chat files can be reparsed in phase 1")
        stored_path = Path(record["stored_path"])
        if not stored_path.exists():
            raise AdminValidationError("stored upload file is missing")
        options = normalize_import_parse_options(payload)
        return self._parse_markdown_import(
            record,
            stored_path.read_bytes(),
            parse_mode=options["parse_mode"],
            chunk_days=options["chunk_days"],
        )

    def list_import_chunks(self, file_id: str) -> dict[str, Any]:
        """返回某个导入文件的时间切块列表。"""
        return {"items": self.database().list_import_chunks(file_id)}

    def list_import_candidates(self, chunk_id: str) -> dict[str, Any]:
        """返回某个切块下的候选 FAQ 列表。"""
        return {"items": self.database().list_import_candidates(chunk_id)}

    def generate_import_candidates(self, chunk_id: str) -> dict[str, Any]:
        """调用 AI 为切块生成候选 FAQ，结果仍需人工审核。"""
        chunk = self.database().get_import_chunk(chunk_id)
        if chunk is None:
            raise AdminNotFoundError(f"Import chunk not found: {chunk_id}")
        suggestions = ImportAiAssistant(self.chat_client()).generate_candidates(chunk["source_text"])
        rows = []
        for suggestion in suggestions:
            rows.append(
                {
                    "id": f"cand_{uuid.uuid4().hex[:12]}",
                    "file_id": chunk["file_id"],
                    "chunk_id": chunk["id"],
                    "question": suggestion.question,
                    "answer": suggestion.answer,
                    "similar_questions": json.dumps(suggestion.similar_questions, ensure_ascii=False),
                    "category": suggestion.category,
                    "tags": json.dumps(suggestion.tags, ensure_ascii=False),
                    "confidence": suggestion.confidence,
                    "internal_note": suggestion.internal_note,
                    "source_excerpt": str(chunk["source_text"])[:1200],
                    "status": "pending",
                }
            )
        return {"items": self.database().create_import_candidates(chunk, rows)}

    def update_import_candidate(self, candidate_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """保存用户对候选 FAQ 的人工编辑。"""
        row = {
            "question": str(payload.get("question", "")).strip(),
            "answer": str(payload.get("answer", "")).strip(),
            "similar_questions": split_text_list(payload.get("similar_questions")),
            "category": str(payload.get("category", "") or "").strip() or None,
            "tags": split_text_list(payload.get("tags")),
            "confidence": str(payload.get("confidence", "medium")).strip() or "medium",
            "internal_note": str(payload.get("internal_note", "") or "").strip() or None,
        }
        if not row["question"] or not row["answer"]:
            raise AdminValidationError("candidate question and answer are required")
        return self.database().update_import_candidate(candidate_id, row)

    def save_import_candidate(self, candidate_id: str) -> dict[str, Any]:
        """将候选 FAQ 保存为标准问答，embedding 仍保持独立生成。"""
        candidate = self.database().get_import_candidate(candidate_id)
        if candidate is None:
            raise AdminNotFoundError(f"Import candidate not found: {candidate_id}")
        faq_row = build_import_candidate_faq_row(candidate)
        saved = self.database().save_faq_text(faq_row)
        return self.database().mark_import_candidate_saved(candidate_id, saved["id"])

    def ignore_import_candidate(self, candidate_id: str) -> dict[str, Any]:
        """忽略不适合沉淀为知识库的候选 FAQ。"""
        return self.database().mark_import_candidate_ignored(candidate_id)


def static_path(path: str) -> Path:
    """把允许访问的管理页静态路径映射到本地文件。"""
    static_dir = Path(__file__).with_name("static")
    if path in {"", "/", "/admin.html"}:
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
                if parsed.path == "/api/import/files":
                    self.send_json(app.list_import_files(parse_qs(parsed.query)))
                    return
                if parsed.path.startswith("/api/import/files/") and parsed.path.endswith("/chunks"):
                    file_id = parsed.path.removeprefix("/api/import/files/").removesuffix("/chunks")
                    self.send_json(app.list_import_chunks(file_id))
                    return
                if parsed.path.startswith("/api/import/chunks/") and parsed.path.endswith("/candidates"):
                    chunk_id = parsed.path.removeprefix("/api/import/chunks/").removesuffix("/candidates")
                    self.send_json(app.list_import_candidates(chunk_id))
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
                if parsed.path == "/api/import/files":
                    filename, content = self.read_multipart_file()
                    self.send_json(app.create_import_file(filename, content))
                    return
                payload = self.read_json()
                if parsed.path.startswith("/api/import/files/") and parsed.path.endswith("/reparse"):
                    file_id = parsed.path.removeprefix("/api/import/files/").removesuffix("/reparse")
                    self.send_json(app.reparse_import_file(file_id, payload))
                    return
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
                if parsed.path.startswith("/api/import/chunks/") and parsed.path.endswith("/generate"):
                    chunk_id = parsed.path.removeprefix("/api/import/chunks/").removesuffix("/generate")
                    self.send_json(app.generate_import_candidates(chunk_id))
                    return
                if parsed.path.startswith("/api/import/candidates/") and parsed.path.endswith("/save"):
                    candidate_id = parsed.path.removeprefix("/api/import/candidates/").removesuffix("/save")
                    self.send_json(app.save_import_candidate(candidate_id))
                    return
                if parsed.path.startswith("/api/import/candidates/") and parsed.path.endswith("/ignore"):
                    candidate_id = parsed.path.removeprefix("/api/import/candidates/").removesuffix("/ignore")
                    self.send_json(app.ignore_import_candidate(candidate_id))
                    return
                if parsed.path.startswith("/api/import/candidates/"):
                    candidate_id = parsed.path.removeprefix("/api/import/candidates/")
                    self.send_json(app.update_import_candidate(candidate_id, payload))
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

        def read_multipart_file(self) -> tuple[str, bytes]:
            """读取单文件上传表单，当前只接受字段名 file。"""
            content_type = self.headers.get("Content-Type", "")
            boundary_match = re.search(r"boundary=(.+)", content_type)
            if not boundary_match:
                raise AdminValidationError("multipart boundary is required")
            boundary = boundary_match.group(1).strip('"').encode("utf-8")
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            for part in body.split(b"--" + boundary):
                if b'name="file"' not in part:
                    continue
                header, _, content = part.partition(b"\r\n\r\n")
                filename_match = re.search(
                    rb'filename="([^"]+)"',
                    header,
                )
                if not filename_match:
                    raise AdminValidationError("uploaded file name is required")
                filename = filename_match.group(1).decode("utf-8", errors="replace")
                return filename, content.rstrip(b"\r\n-")
            raise AdminValidationError("multipart field file is required")

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
            elif isinstance(exc, AdminValidationError | AiSuggestionError | ImportCandidateError):
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
