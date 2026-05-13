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
from urllib.parse import parse_qs, quote, unquote, urlparse

from customer_service_agent.ai_assist import AiAssistant, AiSuggestionError
from customer_service_agent.config import Settings
from customer_service_agent.db import Database, build_import_candidate_faq_row
from customer_service_agent.document_parser import (
    MINERU_BATCH_FILE_URL,
    MINERU_BATCH_RESULT_URL_TEMPLATE,
    MineruClient,
    MineruParseError,
    build_import_chunks_from_blocks,
    extract_blocks_from_mineru_payload,
)
from customer_service_agent.import_dedupe import compare_candidate_duplicate
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


def _normalize_parse_progress(value: Any) -> dict[str, Any]:
    """规范化解析进度字段，兼容数据库 JSONB 和旧字符串记录。"""
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {"state": value.strip()}
        if isinstance(parsed, dict):
            return parsed
    return {}


def _state_from_import_status(status: Any) -> str:
    """把导入文件状态映射为前端轮询状态，避免页面理解 FAQ 审核状态。"""
    mapping = {
        "pending": "pending",
        "processing": "running",
        "needs_review": "done",
        "completed": "done",
        "failed": "failed",
        "unsupported": "unsupported",
    }
    return mapping.get(str(status or "pending"), "pending")


def _parse_progress_percent(progress: dict[str, Any]) -> int:
    """根据 MinerU 页数进度计算百分比，缺少页数时按状态给默认值。"""
    try:
        total_pages = int(progress.get("total_pages") or 0)
        extracted_pages = int(progress.get("extracted_pages") or 0)
    except (TypeError, ValueError):
        total_pages = 0
        extracted_pages = 0
    if total_pages > 0:
        return min(max(round(extracted_pages * 100 / total_pages), 0), 100)
    state = str(progress.get("state") or "")
    if state in {"done", "finished", "success", "completed"}:
        return 100
    return 0


def settings_payload_to_env(payload: dict[str, Any]) -> dict[str, str]:
    """把设置页 payload 规范化成运行时环境键值，并复用 Settings 校验关键约束。"""
    env_values = {
        "DATABASE_URL": str(payload.get("database_url", "")).strip(),
        "CHAT_BASE_URL": str(payload.get("chat_base_url", "")).strip(),
        "CHAT_API_KEY": str(payload.get("chat_api_key", "")).strip(),
        "CHAT_MODEL": str(payload.get("chat_model", "")).strip(),
        "EMBEDDING_BASE_URL": str(payload.get("embedding_base_url", "")).strip(),
        "EMBEDDING_API_KEY": str(payload.get("embedding_api_key", "")).strip(),
        "EMBEDDING_MODEL": str(payload.get("embedding_model", "")).strip(),
        "EMBEDDING_DIMENSIONS": str(payload.get("embedding_dimensions", "")).strip(),
        "WECHAT_TOKEN_FILE": str(payload.get("wechat_token_file", "")).strip(),
        "WECHAT_MESSAGE_CHUNK_SIZE": str(payload.get("wechat_message_chunk_size", "")).strip(),
        "RAG_TOP_K": str(payload.get("rag_top_k", "")).strip(),
        "RAG_MIN_SCORE": str(payload.get("rag_min_score", "")).strip(),
        "UPLOAD_DIR": str(payload.get("upload_dir", "")).strip(),
        "MINERU_API_MODE": "standard",
        "MINERU_API_TOKEN": str(payload.get("mineru_api_token", "")).strip(),
        "MINERU_PARSE_TIMEOUT_SECONDS": str(
            payload.get("mineru_parse_timeout_seconds", "")
        ).strip(),
        "MINERU_USE_KB_PACKAGER": "true" if payload.get("mineru_use_kb_packager") else "false",
    }
    try:
        Settings.from_env(env_values)
    except Exception as exc:
        raise AdminValidationError(str(exc)) from exc
    return env_values


def settings_to_tenant_settings(settings: Settings) -> dict[str, Any]:
    """把 Settings 转成可持久化的租户配置，保留布尔和数字类型。"""
    return {
        "database_url": settings.database_url,
        "chat_base_url": settings.chat_base_url,
        "chat_api_key": settings.chat_api_key,
        "chat_model": settings.chat_model,
        "embedding_base_url": settings.embedding_base_url,
        "embedding_api_key": settings.embedding_api_key,
        "embedding_model": settings.embedding_model,
        "embedding_dimensions": settings.embedding_dimensions,
        "wechat_token_file": str(settings.wechat_token_file),
        "wechat_message_chunk_size": settings.wechat_message_chunk_size,
        "rag_top_k": settings.rag_top_k,
        "rag_min_score": settings.rag_min_score,
        "upload_dir": str(settings.upload_dir),
        "mineru_api_token": settings.mineru_api_token or "",
        "mineru_parse_timeout_seconds": settings.mineru_parse_timeout_seconds,
        "mineru_use_kb_packager": settings.mineru_use_kb_packager,
    }


def write_tenant_settings(settings_file: Path, values: dict[str, Any], tenant_id: str = "default") -> None:
    """写入本地租户设置文件，保留未来多租户配置的扩展结构。"""
    payload: dict[str, Any] = {}
    if settings_file.exists():
        try:
            loaded = json.loads(settings_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise AdminValidationError(f"Invalid settings file: {settings_file}") from exc
        if isinstance(loaded, dict):
            payload = loaded
    tenants = payload.get("tenants")
    if not isinstance(tenants, dict):
        tenants = {}
    tenants[tenant_id] = values
    payload["version"] = 1
    payload["active_tenant_id"] = tenant_id
    payload["tenants"] = tenants
    settings_file.parent.mkdir(parents=True, exist_ok=True)
    settings_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    settings_file.chmod(0o600)


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


def format_sse_event(event: dict[str, Any]) -> str:
    """把任务进度事件格式化成浏览器 EventSource 可读的 SSE 文本。"""
    event_type = str(event.get("type", "message"))
    payload = json.dumps(jsonable(event), ensure_ascii=False)
    return f"event: {event_type}\ndata: {payload}\n\n"


@dataclass
class AdminApp:
    settings: Settings
    db: Database | None = None
    embeddings: EmbeddingClient | None = None
    chat: ChatClient | None = None
    settings_file: Path = Path("data/settings.local.json")
    tenant_id: str = "default"

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

    def settings_snapshot(self) -> dict[str, Any]:
        """给本地设置弹窗返回当前运行配置，密钥只在本机管理页显式查看时使用。"""
        return {
            "database_url": self.settings.database_url,
            "chat_base_url": self.settings.chat_base_url,
            "chat_api_key": self.settings.chat_api_key,
            "chat_model": self.settings.chat_model,
            "embedding_base_url": self.settings.embedding_base_url,
            "embedding_api_key": self.settings.embedding_api_key,
            "embedding_model": self.settings.embedding_model,
            "embedding_dimensions": self.settings.embedding_dimensions,
            "wechat_token_file": str(self.settings.wechat_token_file),
            "wechat_message_chunk_size": self.settings.wechat_message_chunk_size,
            "rag_top_k": self.settings.rag_top_k,
            "rag_min_score": self.settings.rag_min_score,
            "upload_dir": str(self.settings.upload_dir),
            "mineru_api_token": self.settings.mineru_api_token or "",
            "mineru_parse_timeout_seconds": self.settings.mineru_parse_timeout_seconds,
            "mineru_use_kb_packager": self.settings.mineru_use_kb_packager,
        }

    def update_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        """保存设置页配置到本地租户文件，并刷新当前管理进程使用的配置对象。"""
        env_values = settings_payload_to_env(payload)
        next_settings = Settings.from_env(env_values)
        write_tenant_settings(
            self.settings_file,
            settings_to_tenant_settings(next_settings),
            tenant_id=self.tenant_id,
        )
        self.settings = next_settings
        self.embeddings = None
        self.chat = None
        if self.db is not None and getattr(self.db, "database_url", None) != self.settings.database_url:
            self.db = None
        return self.settings_snapshot()

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

    def create_import_file(self, filename: str, content: bytes, *, auto_parse: bool = True) -> dict[str, Any]:
        """保存上传原件；文档管理可选择先只入库，后续由用户手动解析。"""
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
        if not auto_parse:
            return record
        if parser == "markdown_chat":
            return self._parse_markdown_import(record, content)
        if parser == "mineru":
            return self._parse_mineru_import(record, stored_path)
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

    def _parse_mineru_import(self, record: dict[str, Any], stored_path: Path) -> dict[str, Any]:
        """调用 MinerU 解析上传文件，并生成导入审核切块。"""
        try:
            blocks = self._mineru_client().parse_file(stored_path)
            chunk_rows = build_import_chunks_from_blocks(record["id"], blocks)
        except MineruParseError as exc:
            self.database().update_import_file_summary(
                record["id"],
                status="failed",
                error=str(exc),
            )
            raise AdminValidationError(f"MinerU parse failed: {exc}") from exc

        self.database().replace_import_chunks(record["id"], chunk_rows)
        summary = self.database().update_import_file_summary(
            record["id"],
            status="needs_review",
            message_count=0,
            chunk_count=len(chunk_rows),
            candidate_count=0,
            error=None,
        )
        return {**record, **summary}

    def _mineru_client(self) -> MineruClient:
        """创建 MinerU 客户端，集中使用项目内写死的官方批量接口。"""
        return MineruClient(
            api_token=getattr(self.settings, "mineru_api_token", None),
            batch_file_url=MINERU_BATCH_FILE_URL,
            batch_result_url_template=MINERU_BATCH_RESULT_URL_TEMPLATE,
            timeout_seconds=self.settings.mineru_parse_timeout_seconds,
            use_kb_packager=getattr(self.settings, "mineru_use_kb_packager", True),
        )

    def start_import_parse_job(self, file_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """提交文档解析任务，关键约束是 MinerU 长任务不在请求内同步等待。"""
        record = self.database().get_import_file(file_id)
        if record is None:
            raise AdminNotFoundError(f"Import file not found: {file_id}")
        if record.get("parser") == "markdown_chat":
            parsed = self.reparse_import_file(file_id, payload)
            return self._import_parse_status_payload(parsed, state="done", progress={"state": "done"})
        if record.get("parser") != "mineru":
            raise AdminValidationError("only MinerU files can start parse jobs")
        stored_path = Path(record["stored_path"])
        if not stored_path.exists():
            raise AdminValidationError("stored upload file is missing")

        status = self._mineru_client().start_file(stored_path)
        progress = self._mineru_progress_payload(status)
        summary = self.database().update_import_file_summary(
            file_id,
            status="processing",
            parse_batch_id=status.batch_id,
            parse_file_name=status.file_name,
            parse_progress=progress,
            error=None,
        )
        return self._import_parse_status_payload({**record, **summary}, state=status.state, progress=progress)

    def get_import_parse_status(self, file_id: str) -> dict[str, Any]:
        """查询文档解析状态；完成时落盘切片，进行中时只更新进度。"""
        record = self.database().get_import_file(file_id)
        if record is None:
            raise AdminNotFoundError(f"Import file not found: {file_id}")
        if record.get("parser") != "mineru" or record.get("status") != "processing":
            return self._import_parse_status_payload(record)

        batch_id = str(record.get("parse_batch_id") or "").strip()
        file_name = str(record.get("parse_file_name") or record.get("original_name") or "").strip()
        if not batch_id or not file_name:
            return self._import_parse_status_payload(record)

        status = self._mineru_client().get_task_status(batch_id, file_name)
        progress = self._mineru_progress_payload(status)
        if status.state in {"done", "finished", "success", "completed"}:
            return self._finish_mineru_parse_job(record, status, progress)
        if status.state in {"failed", "error", "cancelled", "canceled"}:
            summary = self.database().update_import_file_summary(
                file_id,
                status="failed",
                parse_progress=progress,
                error=status.error or "MinerU parse failed",
            )
            return self._import_parse_status_payload({**record, **summary}, state=status.state, progress=progress)

        summary = self.database().update_import_file_summary(
            file_id,
            status="processing",
            parse_progress=progress,
            error=None,
        )
        return self._import_parse_status_payload({**record, **summary}, state=status.state, progress=progress)

    def _finish_mineru_parse_job(self, record: dict[str, Any], status: Any, progress: dict[str, Any]) -> dict[str, Any]:
        """处理 MinerU 完成状态，下载结果并替换文档切片。"""
        try:
            payload = self._mineru_client().download_task_result(status)
            blocks = extract_blocks_from_mineru_payload(
                payload,
                source_file=record.get("original_name") or status.file_name,
                use_kb_packager=getattr(self.settings, "mineru_use_kb_packager", True),
            )
            chunk_rows = build_import_chunks_from_blocks(record["id"], blocks)
        except MineruParseError as exc:
            summary = self.database().update_import_file_summary(
                record["id"],
                status="failed",
                parse_progress=progress,
                error=str(exc),
            )
            return self._import_parse_status_payload({**record, **summary}, state="failed", progress=progress)

        self.database().replace_import_chunks(record["id"], chunk_rows)
        summary = self.database().update_import_file_summary(
            record["id"],
            status="needs_review",
            message_count=0,
            chunk_count=len(chunk_rows),
            candidate_count=0,
            parse_progress=progress,
            error=None,
        )
        return self._import_parse_status_payload({**record, **summary}, state=status.state, progress=progress)

    def _mineru_progress_payload(self, status: Any) -> dict[str, Any]:
        """把 MinerU 原始进度整理成前端可直接消费的 JSON。"""
        progress = dict(getattr(status, "progress", None) or {})
        progress["state"] = getattr(status, "state", None) or progress.get("state") or "pending"
        return progress

    def _import_parse_status_payload(
        self,
        record: dict[str, Any],
        *,
        state: str | None = None,
        progress: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """构造文档解析轮询响应，状态和百分比保持稳定字段名。"""
        raw_progress = progress if progress is not None else record.get("parse_progress")
        normalized_progress = _normalize_parse_progress(raw_progress)
        current_state = state or normalized_progress.get("state") or _state_from_import_status(record.get("status"))
        normalized_progress.setdefault("state", current_state)
        return {
            "file": record,
            "status": record.get("status"),
            "state": current_state,
            "progress": normalized_progress,
            "percent": _parse_progress_percent(normalized_progress),
            "error": record.get("error"),
        }

    def reparse_import_file(self, file_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """按用户选择的解析参数重新切分已上传文件。"""
        record = self.database().get_import_file(file_id)
        if record is None:
            raise AdminNotFoundError(f"Import file not found: {file_id}")
        if record.get("parser") not in {"markdown_chat", "mineru"}:
            raise AdminValidationError("only Markdown chat or MinerU files can be reparsed")
        stored_path = Path(record["stored_path"])
        if not stored_path.exists():
            raise AdminValidationError("stored upload file is missing")
        if record.get("parser") == "mineru":
            return self._parse_mineru_import(record, stored_path)
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

    def get_import_file_for_download(self, file_id: str) -> tuple[dict[str, Any], Path]:
        """返回可下载的原件路径，关键约束是必须来自已登记导入文件。"""
        record = self.database().get_import_file(file_id)
        if record is None:
            raise AdminNotFoundError(f"Import file not found: {file_id}")
        stored_path = Path(record["stored_path"])
        if not stored_path.exists():
            raise AdminValidationError("stored upload file is missing")
        return record, stored_path

    def delete_import_file(self, file_id: str) -> dict[str, Any]:
        """删除导入文件记录和本地原件，数据库级联清理切片与候选 FAQ。"""
        record = self.database().delete_import_file(file_id)
        if record is None:
            raise AdminNotFoundError(f"Import file not found: {file_id}")
        stored_path = Path(record.get("stored_path") or "")
        if stored_path.exists():
            stored_path.unlink()
        return {"deleted": True, "id": file_id}

    def list_import_candidates(self, chunk_id: str) -> dict[str, Any]:
        """返回某个切块下的候选 FAQ 列表。"""
        return {"items": self.database().list_import_candidates(chunk_id)}

    def list_import_file_candidates(self, file_id: str) -> dict[str, Any]:
        """返回某个导入文件下的全部候选 FAQ，供文件级审核视图使用。"""
        return {"items": self.database().list_import_file_candidates(file_id)}

    def generate_import_candidates(self, chunk_id: str) -> dict[str, Any]:
        """调用 AI 为切块生成候选 FAQ，结果仍需人工审核。"""
        chunk = self.database().get_import_chunk(chunk_id)
        if chunk is None:
            raise AdminNotFoundError(f"Import chunk not found: {chunk_id}")
        suggestions = ImportAiAssistant(self.chat_client()).generate_candidates(chunk["source_text"])
        rows = []
        for suggestion in suggestions:
            duplicate = compare_candidate_duplicate(
                {
                    "question": suggestion.question,
                    "answer": suggestion.answer,
                },
                self.database().list_import_dedupe_references(chunk["id"]),
            )
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
                    "duplicate_level": duplicate.level,
                    "duplicate_score": duplicate.score,
                    "duplicate_target_id": duplicate.target_id,
                    "duplicate_reason": duplicate.reason,
                    "status": "pending",
                }
            )
        return {"items": self.database().create_import_candidates(chunk, rows)}

    def create_import_generation_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        """创建批量候选生成任务，去重切块 id 后交给数据库做幂等判断。"""
        raw_ids = payload.get("chunk_ids", [])
        if not isinstance(raw_ids, list):
            raise AdminValidationError("chunk_ids must be a list")
        chunk_ids = list(dict.fromkeys(str(item).strip() for item in raw_ids if str(item).strip()))
        if not chunk_ids:
            raise AdminValidationError("chunk_ids is required")
        return self.database().create_import_generation_job(chunk_ids)

    def iter_import_generation_events(self, job_id: str):
        """顺序执行生成任务并产出可用于 SSE 的进度事件。"""
        job = self.database().get_import_generation_job(job_id)
        if job is None:
            raise AdminNotFoundError(f"Import generation job not found: {job_id}")
        for item in self.database().list_import_generation_job_items(job_id):
            if item["status"] == "skipped":
                yield {
                    "type": "skipped",
                    "job_id": job_id,
                    "chunk_id": item["chunk_id"],
                    "reason": item.get("reason"),
                }
                continue
            if item["status"] != "queued":
                continue
            self.database().update_import_generation_job_item(item["id"], status="processing")
            yield {"type": "processing", "job_id": job_id, "chunk_id": item["chunk_id"]}
            try:
                result = self.generate_import_candidates(item["chunk_id"])
                candidate_count = len(result["items"])
                self.database().update_import_generation_job_item(
                    item["id"],
                    status="generated",
                    candidate_count=candidate_count,
                    error=None,
                )
                yield {
                    "type": "generated",
                    "job_id": job_id,
                    "chunk_id": item["chunk_id"],
                    "candidate_count": candidate_count,
                }
            except Exception as exc:
                self.database().update_import_generation_job_item(
                    item["id"],
                    status="failed",
                    error=str(exc),
                )
                yield {
                    "type": "failed",
                    "job_id": job_id,
                    "chunk_id": item["chunk_id"],
                    "error": str(exc),
                }
        self.database().update_import_generation_job_summary(job_id, "completed")
        yield {"type": "done", "job_id": job_id}

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
        """将候选 FAQ 保存为标准问答，并立即生成 embedding。"""
        candidate = self.database().get_import_candidate(candidate_id)
        if candidate is None:
            raise AdminNotFoundError(f"Import candidate not found: {candidate_id}")
        faq_row = build_import_candidate_faq_row(candidate)
        saved = self.database().save_faq_text(faq_row)
        embedded = self.embed_faq(saved["id"])
        marked = self.database().mark_import_candidate_saved(candidate_id, saved["id"])
        return {
            **marked,
            "embedding_status": embedded.get("embedding_status"),
            "embedding_error": embedded.get("embedding_error"),
        }

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
                if parsed.path == "/api/settings":
                    self.send_json(app.settings_snapshot())
                    return
                if parsed.path == "/api/import/files":
                    self.send_json(app.list_import_files(parse_qs(parsed.query)))
                    return
                if parsed.path.startswith("/api/import/files/") and parsed.path.endswith("/download"):
                    file_id = parsed.path.removeprefix("/api/import/files/").removesuffix("/download")
                    record, stored_path = app.get_import_file_for_download(file_id)
                    self.send_download(stored_path, record.get("original_name") or stored_path.name)
                    return
                if parsed.path.startswith("/api/import/files/") and parsed.path.endswith("/chunks"):
                    file_id = parsed.path.removeprefix("/api/import/files/").removesuffix("/chunks")
                    self.send_json(app.list_import_chunks(file_id))
                    return
                if parsed.path.startswith("/api/import/files/") and parsed.path.endswith("/parse-status"):
                    file_id = parsed.path.removeprefix("/api/import/files/").removesuffix("/parse-status")
                    self.send_json(app.get_import_parse_status(file_id))
                    return
                if parsed.path.startswith("/api/import/files/") and parsed.path.endswith("/candidates"):
                    file_id = parsed.path.removeprefix("/api/import/files/").removesuffix("/candidates")
                    self.send_json(app.list_import_file_candidates(file_id))
                    return
                if parsed.path.startswith("/api/import/chunks/") and parsed.path.endswith("/candidates"):
                    chunk_id = parsed.path.removeprefix("/api/import/chunks/").removesuffix("/candidates")
                    self.send_json(app.list_import_candidates(chunk_id))
                    return
                if parsed.path.startswith("/api/import/generation-jobs/") and parsed.path.endswith("/events"):
                    job_id = parsed.path.removeprefix("/api/import/generation-jobs/").removesuffix("/events")
                    self.send_sse(app.iter_import_generation_events(job_id))
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
                    auto_parse = parse_qs(parsed.query).get("parse", ["true"])[0].lower() != "false"
                    self.send_json(app.create_import_file(filename, content, auto_parse=auto_parse))
                    return
                payload = self.read_json()
                if parsed.path == "/api/settings":
                    self.send_json(app.update_settings(payload))
                    return
                if parsed.path.startswith("/api/import/files/") and parsed.path.endswith("/reparse"):
                    file_id = parsed.path.removeprefix("/api/import/files/").removesuffix("/reparse")
                    self.send_json(app.reparse_import_file(file_id, payload))
                    return
                if parsed.path.startswith("/api/import/files/") and parsed.path.endswith("/parse-jobs"):
                    file_id = parsed.path.removeprefix("/api/import/files/").removesuffix("/parse-jobs")
                    self.send_json(app.start_import_parse_job(file_id, payload))
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
                if parsed.path == "/api/import/generation-jobs":
                    self.send_json(app.create_import_generation_job(payload))
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

        def do_DELETE(self) -> None:
            parsed = urlparse(self.path)
            try:
                if parsed.path.startswith("/api/import/files/"):
                    file_id = parsed.path.removeprefix("/api/import/files/")
                    self.send_json(app.delete_import_file(file_id))
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

        def send_download(self, path: Path, filename: str) -> None:
            """发送已上传原件，文件名通过 RFC 5987 编码避免中文乱码。"""
            if not path.exists():
                raise AdminNotFoundError(str(path))
            content = path.read_bytes()
            content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quote(filename)}")
            self.end_headers()
            self.wfile.write(content)

        def send_json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
            content = json.dumps(jsonable(payload), ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def send_sse(self, events: Any) -> None:
            """发送生成任务进度事件流，供前端 EventSource 消费。"""
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            for event in events:
                self.wfile.write(format_sse_event(event).encode("utf-8"))
                self.wfile.flush()

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
