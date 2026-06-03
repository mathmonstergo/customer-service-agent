from __future__ import annotations

import json
import logging
import mimetypes
import os
import re
import sys
import time
import traceback
import uuid

import requests
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import parse_qs, quote, unquote, urlparse

from customer_service_agent.ai_assist import AiAssistant, AiSuggestionError
from customer_service_agent.chunking import normalize_children_delimiter, split_with_pattern
from customer_service_agent.config import Settings
from customer_service_agent.db import (
    Database,
    build_document_knowledge_chunk_row,
    build_faq_knowledge_chunk_row,
    build_import_candidate_faq_row,
)
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
from customer_service_agent.import_questions import ImportQuestionAssistant, ImportQuestionError
from customer_service_agent.import_models import detect_file_type
from customer_service_agent.llm import ChatClient, EmbeddingClient, RerankClient, build_openai_client
from customer_service_agent.markdown_import import chunk_messages, parse_wechat_messages
from customer_service_agent.rag import build_user_prompt, load_system_prompt
from customer_service_agent.retrieval import (
    EvalCaseResult,
    analyze_query,
    build_keyword_terms,
    compute_retrieval_metrics,
    fuse_retrieval_candidates,
    rerank_candidates,
)


class AdminValidationError(ValueError):
    pass


class AdminNotFoundError(KeyError):
    pass


class AdminPayloadTooLargeError(ValueError):
    """请求体超出允许大小时抛出，统一映射为 413。"""

    pass


logger = logging.getLogger(__name__)

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
REMOTE_ADMIN_ENV = "ALLOW_REMOTE_ADMIN"

VALID_FAQ_STATUSES = {"usable", "needs_review", "disabled"}
VALID_IMPORT_PARSE_MODES = {"by_days", "by_gap"}
DOCUMENT_CHILD_INDEX_OFFSET = 1


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


def normalize_retrieval_eval_case_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """规范化检索评测用例，关键约束是问题和期望命中口径必须可执行。"""
    question = str(payload.get("question", "")).strip()
    if not question:
        raise AdminValidationError("question is required")
    case_id = str(payload.get("id", "")).strip() or f"eval_{uuid.uuid4().hex[:12]}"
    return {
        "id": case_id,
        "question": question,
        "intent": str(payload.get("intent", "") or "").strip() or None,
        "expected_source_ids": split_text_list(payload.get("expected_source_ids")),
        "expected_chunk_ids": split_text_list(payload.get("expected_chunk_ids")),
        "tags": split_text_list(payload.get("tags")),
        "note": str(payload.get("note", "") or "").strip() or None,
        "status": str(payload.get("status", "active") or "active").strip() or "active",
    }


def normalize_retrieval_alias_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """规范化检索别名词条，关键约束是标准词不能为空。"""
    canonical = str(payload.get("canonical", "")).strip()
    if not canonical:
        raise AdminValidationError("canonical is required")
    return {
        "id": str(payload.get("id", "")).strip() or f"alias_{uuid.uuid4().hex[:12]}",
        "canonical": canonical,
        "aliases": split_text_list(payload.get("aliases")),
        "tags": split_text_list(payload.get("tags")),
        "status": str(payload.get("status", "active") or "active").strip() or "active",
    }


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
        "DOCUMENT_CHUNK_TOKEN_NUM": str(payload.get("document_chunk_token_num", "")).strip(),
        "DOCUMENT_CHUNK_DELIMITER": str(payload.get("document_chunk_delimiter", "")),
        "DOCUMENT_CHUNK_OVERLAP_PERCENT": str(
            payload.get("document_chunk_overlap_percent", "")
        ).strip(),
        "DOCUMENT_CHILDREN_DELIMITER": str(payload.get("document_children_delimiter", "")),
        "DOCUMENT_TABLE_CONTEXT_SIZE": str(payload.get("document_table_context_size", "")).strip(),
        "DOCUMENT_IMAGE_CONTEXT_SIZE": str(payload.get("document_image_context_size", "")).strip(),
        "RERANK_BASE_URL": str(payload.get("rerank_base_url", "")).strip(),
        "RERANK_API_KEY": str(payload.get("rerank_api_key", "")).strip(),
        "RERANK_MODEL": str(payload.get("rerank_model", "")).strip(),
        "RERANK_INPUT_SIZE": str(payload.get("rerank_input_size", "")).strip(),
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
        "document_chunk_token_num": settings.document_chunk_token_num,
        "document_chunk_delimiter": settings.document_chunk_delimiter,
        "document_chunk_overlap_percent": settings.document_chunk_overlap_percent,
        "document_children_delimiter": settings.document_children_delimiter,
        "document_table_context_size": settings.document_table_context_size,
        "document_image_context_size": settings.document_image_context_size,
        "rerank_base_url": settings.rerank_base_url,
        "rerank_api_key": settings.rerank_api_key,
        "rerank_model": settings.rerank_model,
        "rerank_input_size": settings.rerank_input_size,
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


def _isoformat(value: Any) -> str | None:
    """容忍 None / 已经是字符串的列，给前端统一的 ISO 时间戳。"""
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def safe_upload_name(filename: str) -> str:
    """清理上传文件名，只保留本地存储需要的安全字符。

    关键约束：`.` / `..` / 空基名直接返回安全占位 `upload`，避免拼接路径时被
    解释为上级目录或隐藏文件；其余只保留字母、数字、点、下划线、连字符和中文字符。
    """
    name = Path(filename).name.strip()
    if not name or name in {".", ".."}:
        return "upload"
    return re.sub(r"[^0-9A-Za-z._\-\u4e00-\u9fff]+", "_", name)


def ensure_loopback_or_explicit_opt_in(host: str, env: Mapping[str, str]) -> None:
    """启动守门：非 loopback host 必须显式 env 同意，避免误暴露无鉴权后台。

    关键约束：env 值严格判等 `"1"`，避免拼写造成意外放行；命中显式同意时
    在 stderr 打 warning 提醒当前架构无鉴权 + 无上传限额。
    """
    if host in LOOPBACK_HOSTS:
        return
    if env.get(REMOTE_ADMIN_ENV, "").strip() == "1":
        print(
            f"warning: admin server binding non-loopback host {host!r}; "
            "no auth or upload limits enforced — set up reverse proxy or auth before use",
            file=sys.stderr,
            flush=True,
        )
        return
    raise RuntimeError(
        f"non-loopback admin host {host!r} requires {REMOTE_ADMIN_ENV}=1; "
        "default-bind to 127.0.0.1 or set the env to acknowledge the exposure risk"
    )


def ensure_request_size(content_length: int, max_bytes: int, kind: str) -> None:
    """请求体大小守门，超限直接抛 AdminPayloadTooLargeError 防止读到内存。

    关键约束：必须在 read body 之前调用；超限时不读 body，直接走 413 响应。
    """
    if content_length > max_bytes:
        raise AdminPayloadTooLargeError(
            f"{kind} body exceeds limit: {content_length} > {max_bytes}"
        )


def classify_error_response(exc: Exception) -> tuple[HTTPStatus, dict[str, Any]]:
    """把异常分级为 HTTP 状态码 + 前端可见响应体。

    关键约束：500 类异常脱敏为固定文案 `internal error`，不暴露 raw message
    （SQL 细节、文件路径、内部 URL 等），完整堆栈走日志另写。已识别业务异常保留
    原文案，方便前端把"必填字段缺失"这类信息直接展示给用户。
    """
    if isinstance(exc, AdminNotFoundError):
        return HTTPStatus.NOT_FOUND, {"error": str(exc)}
    if isinstance(exc, AdminPayloadTooLargeError):
        return HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": str(exc)}
    if isinstance(exc, AdminValidationError | AiSuggestionError | ImportCandidateError):
        return HTTPStatus.BAD_REQUEST, {"error": str(exc)}
    return HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "internal error"}


def ensure_upload_path_within(upload_dir: Path, candidate: Path) -> Path:
    """resolve 后必须落在 upload_dir 内，覆盖符号链接或拼接穿越攻击。

    关键约束：返回 resolve 后的绝对路径供调用方使用；穿越时抛
    AdminValidationError 走 400，避免泄漏目标路径。
    """
    resolved_dir = upload_dir.resolve()
    resolved_candidate = candidate.resolve()
    try:
        resolved_candidate.relative_to(resolved_dir)
    except ValueError as exc:
        raise AdminValidationError(
            f"upload path escapes upload_dir: {candidate.name}"
        ) from exc
    return resolved_candidate


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


def parse_sse_event(content: str) -> dict[str, Any]:
    """解析单个 SSE 事件块，供测试校验事件名和 JSON 数据。"""
    event_name = "message"
    data_lines: list[str] = []
    for line in content.strip().splitlines():
        if line.startswith("event:"):
            event_name = line.removeprefix("event:").strip()
        elif line.startswith("data:"):
            data_lines.append(line.removeprefix("data:").strip())
    data = json.loads("\n".join(data_lines)) if data_lines else {}
    return {"event": event_name, "data": data}


def assistant_document_payload(doc: Any) -> dict[str, Any]:
    """把检索命中文档转换成智能问答调试抽屉使用的来源结构。"""
    return {
        "id": doc.id,
        "source_type": getattr(doc, "source_type", "faq"),
        "source_id": getattr(doc, "source_id", doc.id),
        "source_chunk_id": getattr(doc, "source_chunk_id", None),
        "parent_chunk_id": getattr(doc, "parent_chunk_id", None),
        "chunk_level": getattr(doc, "chunk_level", "chunk"),
        "source_title": getattr(doc, "source_title", getattr(doc, "question", "")),
        "content": getattr(doc, "content", getattr(doc, "answer", "")),
        "metadata": getattr(doc, "metadata", {}),
        "score": doc.score,
        "question": doc.question,
        "answer": doc.answer,
        "category": doc.category,
        "tags": doc.tags,
        "source_date": doc.source_date,
        "confidence": doc.confidence,
        "status": doc.status,
    }


def parent_context_documents(database: Any, docs: list[Any]) -> list[Any]:
    """命中 child 文档时读取 parent 上下文，关键约束是不重复追加已有命中。"""
    child_ids = [
        str(getattr(doc, "id"))
        for doc in docs
        if getattr(doc, "parent_chunk_id", None) and getattr(doc, "chunk_level", "") != "parent"
    ]
    if not child_ids:
        return []
    getter = getattr(database, "get_parent_context_chunks", None)
    if getter is None:
        return []
    existing_ids = {str(getattr(doc, "id", "")) for doc in docs}
    return [doc for doc in getter(child_ids) if str(getattr(doc, "id", "")) not in existing_ids]


def retrieval_eval_item_payload(candidate: Any) -> dict[str, Any]:
    """把融合候选转换为评测运行可回放的精简结构。"""
    doc = candidate.document
    return {
        "id": getattr(doc, "id", ""),
        "source_id": getattr(doc, "source_id", ""),
        "source_type": getattr(doc, "source_type", ""),
        "channels": list(candidate.channels),
        "fused_score": candidate.fused_score,
        "vector_score": candidate.vector_score,
        "keyword_score": candidate.keyword_score,
    }


def document_knowledge_rows_for_embedding(chunk: dict[str, Any], import_file: dict[str, Any]) -> list[dict[str, Any]]:
    """把审核切片转换为 RAGFlow 风格 parent/child 知识单元。"""
    parent_row = build_document_knowledge_chunk_row(
        {**chunk, "retrieval_status": "usable", "chunk_level": "parent"},
        import_file,
    )
    delimiter_children = delimiter_child_chunks(chunk)
    if delimiter_children:
        return _child_rows_from_texts(chunk, import_file, parent_row, delimiter_children)

    blocks = structured_source_blocks(chunk.get("source_blocks"))
    if len(blocks) <= 1:
        return [parent_row]

    return _child_rows_from_blocks(chunk, import_file, parent_row, blocks)


def child_knowledge_chunk_index(parent_index: int, child_index: int) -> int:
    """为 child 知识单元生成负数 chunk_index，关键约束是不与 parent 正编号冲突。"""
    parent = max(int(parent_index), 0)
    child = max(int(child_index), 0)
    paired = (parent + child) * (parent + child + 1) // 2 + child
    return -(paired + DOCUMENT_CHILD_INDEX_OFFSET)


def delimiter_child_chunks(chunk: dict[str, Any]) -> list[str]:
    """按 RAGFlow children_delimiter 规则拆分 parent 正文，单段结果不重复建 child。"""
    pattern = normalize_children_delimiter(chunk.get("children_delimiter"))
    if not pattern:
        return []
    children = split_with_pattern(str(chunk.get("source_text") or ""), pattern)
    return children if len(children) > 1 else []


def _child_rows_from_texts(
    chunk: dict[str, Any],
    import_file: dict[str, Any],
    parent_row: dict[str, Any],
    child_texts: list[str],
) -> list[dict[str, Any]]:
    """从 delimiter 子段生成 child rows，并用 parent_content 对齐 RAGFlow mom_with_weight。"""
    rows = [parent_row]
    parent_index = int(chunk.get("chunk_index", 0))
    for child_index, child_text in enumerate(child_texts, start=1):
        child_chunk = {
            **chunk,
            "id": f"{chunk['id']}_child_{child_index}",
            "source_text": child_text,
            "source_blocks": [],
            "chunk_index": child_knowledge_chunk_index(parent_index, child_index),
            "parent_chunk_id": parent_row["id"],
            "chunk_level": "child",
            "parent_content": parent_row["content"],
            "retrieval_status": "usable",
        }
        rows.append(build_document_knowledge_chunk_row(child_chunk, import_file))
    return rows


def _child_rows_from_blocks(
    chunk: dict[str, Any],
    import_file: dict[str, Any],
    parent_row: dict[str, Any],
    blocks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """从结构化 source_blocks 生成 child rows，用于无 children_delimiter 的默认精确召回。"""
    rows = [parent_row]
    parent_index = int(chunk.get("chunk_index", 0))
    for child_index, block in enumerate(blocks, start=1):
        block_text = str(block.get("text") or "").strip()
        if not block_text:
            continue
        child_meta = structured_block_metadata(block, chunk)
        child_chunk = {
            **chunk,
            **child_meta,
            "id": f"{chunk['id']}_child_{child_index}",
            "source_text": block_text,
            "source_blocks": [block],
            "chunk_index": child_knowledge_chunk_index(parent_index, child_index),
            "parent_chunk_id": parent_row["id"],
            "chunk_level": "child",
            "parent_content": parent_row["content"],
            "retrieval_status": "usable",
        }
        rows.append(build_document_knowledge_chunk_row(child_chunk, import_file))
    return rows


def structured_source_blocks(value: Any) -> list[dict[str, Any]]:
    """读取解析器来源块，关键约束是不从审核正文反向解析结构。"""
    if isinstance(value, str) and value.strip():
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return []
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def structured_block_metadata(block: dict[str, Any], parent_chunk: dict[str, Any]) -> dict[str, Any]:
    """从结构化来源块生成 child metadata，缺失字段继承 parent。"""
    section = str(block.get("section_title") or "").strip()
    section_path = [part.strip() for part in section.split(">") if part.strip()]
    page_number = _optional_int(block.get("page_number"))
    evidence = block.get("evidence") if isinstance(block.get("evidence"), dict) else {}
    if page_number is None:
        page_number = _optional_int(evidence.get("page_number"))
    source_offsets = {}
    position_tag = block.get("position_tag") or evidence.get("position_tag")
    if position_tag:
        source_offsets["position_tag"] = position_tag
    if evidence:
        source_offsets["evidence"] = dict(evidence)
    return {
        "section_path": section_path or parent_chunk.get("section_path") or [],
        "page_start": page_number if page_number is not None else parent_chunk.get("page_start"),
        "page_end": page_number if page_number is not None else parent_chunk.get("page_end"),
        "block_type": block.get("block_type") or parent_chunk.get("block_type"),
        "source_offsets": source_offsets or parent_chunk.get("source_offsets") or {},
    }


def _optional_int(value: Any) -> int | None:
    """把结构化块里的页码转为整数，非法值保持为空。"""
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def assistant_step_event(
    step_id: str,
    title: str,
    status: str,
    started_at: float,
    *,
    summary: str = "",
    **extra: Any,
) -> dict[str, Any]:
    """构造流程可视化节点事件，统一节点状态、耗时和摘要字段。"""
    return {
        "type": "step",
        "step_id": step_id,
        "title": title,
        "status": status,
        "duration_ms": max(round((time.perf_counter() - started_at) * 1000), 0),
        "summary": summary,
        **extra,
    }


@dataclass
class AdminApp:
    settings: Settings
    db: Database | None = None
    embeddings: EmbeddingClient | None = None
    chat: ChatClient | None = None
    rerank: RerankClient | None = None
    rerank_resolved: bool = False
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

    def _chat_client_for_payload(self, payload: dict[str, Any]) -> ChatClient:
        """支持单次请求覆盖 chat 供应商：三件套齐了就临时造一个，否则走全局默认。"""
        base_url = str(payload.get("chat_base_url") or "").strip()
        api_key = str(payload.get("chat_api_key") or "").strip()
        model = str(payload.get("chat_model") or "").strip()
        if base_url and api_key and model:
            return ChatClient(build_openai_client(base_url, api_key), model=model)
        return self.chat_client()

    def probe_chat_provider(self, payload: dict[str, Any]) -> dict[str, Any]:
        """用最小 chat completion 测试一次连通性，结果以 ok/error 形式回，不抛 4xx。"""
        base_url = str(payload.get("chat_base_url") or "").strip()
        api_key = str(payload.get("chat_api_key") or "").strip()
        model = str(payload.get("chat_model") or "").strip()
        if not (base_url and api_key and model):
            return {"ok": False, "error": "请填写 base_url、api_key、model 三项"}
        try:
            started = time.perf_counter()
            client = ChatClient(build_openai_client(base_url, api_key), model=model)
            sample = client.complete("", "ping")
            return {
                "ok": True,
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "model": model,
                "sample": (sample or "")[:80],
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc) or exc.__class__.__name__}

    def list_chat_provider_models(self, payload: dict[str, Any]) -> dict[str, Any]:
        """调供应商的 GET /models 列出可用模型，归一化为 {items: [{id, owned_by}]}。"""
        base_url = str(payload.get("chat_base_url") or "").strip()
        api_key = str(payload.get("chat_api_key") or "").strip()
        if not (base_url and api_key):
            return {"items": [], "ok": False, "error": "请填写 base_url 和 api_key"}
        try:
            url = base_url.rstrip("/") + "/models"
            resp = requests.get(
                url,
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=15.0,
            )
            resp.raise_for_status()
            data = resp.json()
            raw = data.get("data") if isinstance(data, dict) else None
            items: list[dict[str, str]] = []
            if isinstance(raw, list):
                for item in raw:
                    if isinstance(item, dict) and item.get("id"):
                        items.append({
                            "id": str(item["id"]),
                            "owned_by": str(item.get("owned_by") or ""),
                        })
            items.sort(key=lambda m: m["id"])
            return {"ok": True, "items": items}
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            body = exc.response.text[:200] if exc.response is not None else ""
            return {"ok": False, "items": [], "error": f"HTTP {status} {body}"}
        except Exception as exc:
            return {"ok": False, "items": [], "error": str(exc) or exc.__class__.__name__}

    def rerank_client(self) -> RerankClient | None:
        """按配置返回 RerankClient；缺一项即返回 None 让上游透传。"""
        if not self.rerank_resolved:
            self.rerank = RerankClient.from_settings(self.settings)
            self.rerank_resolved = True
        return self.rerank

    def assistant_system_prompt(self) -> str:
        """读取智能问答系统提示词；未配置时返回空值，不再注入代码硬编码提示。"""
        try:
            return load_system_prompt()
        except FileNotFoundError:
            return ""

    def assistant_system_prompt_from_payload(self, payload: dict[str, Any]) -> str:
        """读取会话级系统提示词；为空时只回退到本地配置文件，不使用代码默认值。"""
        system_prompt = str(payload.get("system_prompt", "") or "").strip()
        return system_prompt or self.assistant_system_prompt()

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
            "document_chunk_token_num": self.settings.document_chunk_token_num,
            "document_chunk_delimiter": self.settings.document_chunk_delimiter,
            "document_chunk_overlap_percent": self.settings.document_chunk_overlap_percent,
            "document_children_delimiter": self.settings.document_children_delimiter,
            "document_table_context_size": self.settings.document_table_context_size,
            "document_image_context_size": self.settings.document_image_context_size,
            "rerank_base_url": self.settings.rerank_base_url,
            "rerank_api_key": self.settings.rerank_api_key,
            "rerank_model": self.settings.rerank_model,
            "rerank_input_size": self.settings.rerank_input_size,
        }

    def update_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        """保存设置页配置到本地租户文件，关键约束是缺失字段沿用当前运行值。"""
        merged_payload = {**settings_to_tenant_settings(self.settings), **payload}
        env_values = settings_payload_to_env(merged_payload)
        next_settings = Settings.from_env(env_values)
        write_tenant_settings(
            self.settings_file,
            settings_to_tenant_settings(next_settings),
            tenant_id=self.tenant_id,
        )
        self.settings = next_settings
        self.embeddings = None
        self.chat = None
        self.rerank = None
        self.rerank_resolved = False
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

    def list_retrieval_eval_cases(self, params: dict[str, list[str]]) -> dict[str, Any]:
        """列出检索评测用例，第一版供接口和脚本手工维护样本集。"""
        return self.database().list_retrieval_eval_cases(
            status=params.get("status", [""])[0] or None,
            limit=min(max(int(params.get("limit", ["50"])[0]), 1), 100),
            offset=max(int(params.get("offset", ["0"])[0]), 0),
        )

    def create_retrieval_eval_case(self, payload: dict[str, Any]) -> dict[str, Any]:
        """创建检索评测用例，真实客服问题先作为人工样本沉淀。"""
        row = normalize_retrieval_eval_case_payload(payload)
        return self.database().create_retrieval_eval_case(row)

    def list_retrieval_aliases(self) -> dict[str, Any]:
        """列出启用检索别名，供接口和关键词扩展复用。"""
        rows = self._retrieval_aliases()
        return {"items": rows, "total": len(rows)}

    def save_retrieval_alias(self, payload: dict[str, Any]) -> dict[str, Any]:
        """保存检索别名词条，第一版只提供最小后端接口。"""
        row = normalize_retrieval_alias_payload(payload)
        return self.database().upsert_retrieval_alias(row)

    def run_retrieval_eval_case(self, case_id: str) -> dict[str, Any]:
        """运行单条检索评测，记录混合召回候选和指标。"""
        case = self.database().get_retrieval_eval_case(case_id)
        if case is None:
            raise AdminNotFoundError(f"Retrieval eval case not found: {case_id}")

        question = str(case["question"]).strip()
        analysis = analyze_query(question, self.chat_client())
        query = analysis.query_rewrite or question
        top_k = getattr(self.settings, "rag_top_k", 5)
        min_score = getattr(self.settings, "rag_min_score", 0.35)
        candidate_limit = max(top_k * 2, top_k)
        aliases = self._retrieval_aliases()
        query_terms = build_keyword_terms(query, aliases)
        query_embedding = self.embedding_client().embed(query)
        vector_docs = self.database().search_knowledge(
            query_embedding,
            top_k=candidate_limit,
            min_score=min_score,
        )
        keyword_docs = self.database().search_knowledge_text(
            query,
            top_k=candidate_limit,
            query_terms=query_terms,
        )
        fused = fuse_retrieval_candidates(
            vector_docs=vector_docs,
            keyword_docs=keyword_docs,
            top_k=top_k,
        )
        retrieved_items = [retrieval_eval_item_payload(candidate) for candidate in fused]
        expected_ids = split_text_list(case.get("expected_chunk_ids")) or split_text_list(
            case.get("expected_source_ids")
        )
        retrieved_ids = [
            item["id"] if split_text_list(case.get("expected_chunk_ids")) else item["source_id"]
            for item in retrieved_items
        ]
        metrics = compute_retrieval_metrics(
            [
                EvalCaseResult(
                    question=question,
                    expected_ids=expected_ids,
                    retrieved_ids=retrieved_ids,
                )
            ],
            k=top_k,
        )
        row = {
            "case_id": case_id,
            "strategy": "hybrid_v1",
            "retrieved_items": retrieved_items,
            "metrics": metrics,
            "analysis": {
                **analysis.to_dict(),
                "query_terms": query_terms,
                "vector_count": len(vector_docs),
                "keyword_count": len(keyword_docs),
            },
        }
        return self.database().record_retrieval_eval_run(row)

    def _retrieval_aliases(self) -> list[dict[str, Any]]:
        """读取启用别名词典；测试替身未实现该方法时返回空列表。"""
        list_aliases = getattr(self.database(), "list_retrieval_aliases", None)
        if list_aliases is None:
            return []
        return list_aliases()

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc)

    @classmethod
    def _since_from_days(cls, days: int) -> datetime:
        return cls._utc_now() - timedelta(days=max(int(days), 0))

    @staticmethod
    def _int_param(params: dict[str, Any], key: str, default: int) -> int:
        raw = params.get(key)
        if isinstance(raw, list):
            raw = raw[0] if raw else None
        if raw is None or raw == "":
            return default
        try:
            return int(raw)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _float_param(params: dict[str, Any], key: str, default: float) -> float:
        raw = params.get(key)
        if isinstance(raw, list):
            raw = raw[0] if raw else None
        if raw is None or raw == "":
            return default
        try:
            return float(raw)
        except (TypeError, ValueError):
            return default

    def analytics_overview(self) -> dict[str, Any]:
        """看板概览：今日 / 7 日 / 30 日命中率。"""
        now = self._utc_now()
        today = now - timedelta(days=1)
        last_7d = now - timedelta(days=7)
        last_30d = now - timedelta(days=30)
        return self.database().query_analytics_overview(
            today=today, last_7d=last_7d, last_30d=last_30d
        )

    def list_top_queries(self, params: dict[str, list[str]]) -> dict[str, Any]:
        """高频查询表。"""
        limit = self._int_param(params, "limit", 20)
        days = self._int_param(params, "days", 7)
        since = self._since_from_days(days)
        items = self.database().list_top_queries(limit=limit, since=since)
        return {"items": items, "since": since.isoformat(), "limit": limit}

    def list_zero_hit_queries(self, params: dict[str, list[str]]) -> dict[str, Any]:
        """零命中查询表。"""
        limit = self._int_param(params, "limit", 50)
        days = self._int_param(params, "days", 7)
        since = self._since_from_days(days)
        items = self.database().list_zero_hit_queries(limit=limit, since=since)
        return {"items": items, "since": since.isoformat(), "limit": limit}

    def list_low_score_queries(self, params: dict[str, list[str]]) -> dict[str, Any]:
        """低置信查询表。"""
        limit = self._int_param(params, "limit", 50)
        days = self._int_param(params, "days", 7)
        threshold = self._float_param(
            params, "threshold", float(getattr(self.settings, "rag_min_score", 0.35))
        )
        since = self._since_from_days(days)
        items = self.database().list_low_score_queries(
            limit=limit, since=since, threshold=threshold
        )
        return {
            "items": items,
            "since": since.isoformat(),
            "limit": limit,
            "threshold": threshold,
        }

    def list_top_referenced_chunks(self, params: dict[str, list[str]]) -> dict[str, Any]:
        """chunk 引用频次表。"""
        limit = self._int_param(params, "limit", 20)
        days = self._int_param(params, "days", 7)
        since = self._since_from_days(days)
        items = self.database().top_referenced_chunks(limit=limit, since=since)
        return {"items": items, "since": since.isoformat(), "limit": limit}

    def query_hit_rate_timeseries(self, params: dict[str, list[str]]) -> dict[str, Any]:
        """命中率时序，按日聚合。"""
        days = self._int_param(params, "days", 7)
        since = self._since_from_days(days)
        rows = self.database().query_hit_rate_timeseries(since=since)
        items = []
        for row in rows:
            total = int(row.get("total") or 0)
            hits = int(row.get("hits") or 0)
            hit_rate = (hits / total) if total else 0.0
            bucket = row.get("bucket")
            items.append(
                {
                    "bucket": bucket.isoformat() if hasattr(bucket, "isoformat") else str(bucket),
                    "total": total,
                    "hits": hits,
                    "hit_rate": hit_rate,
                }
            )
        return {"items": items, "since": since.isoformat()}

    def list_cluster_summaries(self, params: dict[str, list[str]]) -> dict[str, Any]:
        """读取最近的零命中聚类摘要。"""
        limit = self._int_param(params, "limit", 20)
        items = self.database().list_cluster_summaries(limit=limit)
        formatted = []
        for row in items:
            formatted.append(
                {
                    **row,
                    "created_at": _isoformat(row.get("created_at")),
                    "period_start": _isoformat(row.get("period_start")),
                    "period_end": _isoformat(row.get("period_end")),
                }
            )
        return {"items": formatted}

    def cluster_zero_hit_queries(self, payload: dict[str, Any]) -> dict[str, Any]:
        """触发零命中 LLM 聚类：取最近 N 天的零命中查询，让 chat 给出主题分组。"""
        days = int(payload.get("days") or 7)
        limit = int(payload.get("limit") or 200)
        since = self._since_from_days(days)
        until = self._utc_now()
        queries = self.database().list_zero_hit_queries(limit=limit, since=since)
        if not queries:
            return {"items": [], "message": "no zero-hit queries in window"}
        sample = [str(row.get("query") or "").strip() for row in queries]
        sample = [item for item in sample if item][:limit]
        prompt = "\n".join(
            [
                f"下面是过去 {days} 天 {len(sample)} 条没有命中知识库的用户查询。",
                "请按主题聚类（不超过 10 类），每类给出：",
                "- cluster_label（中文短语）",
                "- suggested_content（建议补充什么内容）",
                "- representative_queries（代表性 3-5 条原文）",
                "只输出 JSON，结构 {\"clusters\": [...]}。",
                "",
                "查询列表：",
                *[f"- {item}" for item in sample],
            ]
        )
        raw = self.chat_client().complete(
            "你是企业级知识库的内容运营助手，输出中文 JSON。",
            prompt,
        )
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise AdminValidationError(f"cluster response is not JSON: {exc}") from exc
        clusters = parsed.get("clusters") if isinstance(parsed, dict) else None
        if not isinstance(clusters, list):
            raise AdminValidationError("cluster response missing 'clusters' list")
        saved: list[dict[str, Any]] = []
        for cluster in clusters:
            if not isinstance(cluster, dict):
                continue
            label = str(cluster.get("cluster_label") or "").strip()
            if not label:
                continue
            sample_queries = [
                str(item).strip()
                for item in (cluster.get("representative_queries") or [])
                if str(item).strip()
            ]
            row = self.database().save_cluster_summary(
                {
                    "period_start": since,
                    "period_end": until,
                    "cluster_label": label,
                    "suggested_content": cluster.get("suggested_content"),
                    "event_count": len(sample_queries),
                    "sample_queries": sample_queries,
                }
            )
            saved.append(
                {
                    **row,
                    "created_at": _isoformat(row.get("created_at")),
                    "period_start": _isoformat(row.get("period_start")),
                    "period_end": _isoformat(row.get("period_end")),
                }
            )
        return {"items": saved, "total": len(saved), "window_days": days}

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
        """为 FAQ 生成向量，并同步投影到统一知识单元表。"""
        row = self.get_faq(faq_id)
        try:
            embedding_client = self.embedding_client()
            vector = embedding_client.embed(row["embedding_text"])
            updated = self.database().update_faq_embedding(
                faq_id,
                vector,
                embedding_model=embedding_client.model,
                embedding_dimensions=embedding_client.dimensions,
            )
            self.database().upsert_knowledge_chunk(
                build_faq_knowledge_chunk_row(updated),
                vector,
                embedding_model=embedding_client.model,
                embedding_dimensions=embedding_client.dimensions,
            )
            return updated
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
        ensure_upload_path_within(upload_dir, stored_path)
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
            blocks = self._mineru_client(record["id"]).parse_file(stored_path)
            chunk_rows = self._build_document_import_chunks(record["id"], blocks)
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

    def _mineru_client(self, import_file_id: str | None = None) -> MineruClient:
        """创建 MinerU 客户端，关键约束是资产按导入文件隔离存储。"""
        asset_output_dir = Path(self.settings.upload_dir) / "mineru-assets"
        if import_file_id:
            asset_output_dir = asset_output_dir / safe_upload_name(import_file_id)
        return MineruClient(
            api_token=getattr(self.settings, "mineru_api_token", None),
            batch_file_url=MINERU_BATCH_FILE_URL,
            batch_result_url_template=MINERU_BATCH_RESULT_URL_TEMPLATE,
            timeout_seconds=self.settings.mineru_parse_timeout_seconds,
            use_kb_packager=getattr(self.settings, "mineru_use_kb_packager", True),
            asset_output_dir=asset_output_dir,
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

        status = self._mineru_client(record["id"]).start_file(stored_path)
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

        status = self._mineru_client(record["id"]).get_task_status(batch_id, file_name)
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
            payload = self._mineru_client(record["id"]).download_task_result(status)
            blocks = extract_blocks_from_mineru_payload(
                payload,
                source_file=record.get("original_name") or status.file_name,
                use_kb_packager=getattr(self.settings, "mineru_use_kb_packager", True),
            )
            chunk_rows = self._build_document_import_chunks(record["id"], blocks)
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

    def _build_document_import_chunks(self, file_id: str, blocks: list[Any]) -> list[dict[str, Any]]:
        """按 RAGFlow naive chunk 配置生成文档导入审核切片。"""
        return build_import_chunks_from_blocks(
            file_id,
            blocks,
            chunk_token_num=getattr(self.settings, "document_chunk_token_num", 512),
            delimiter=getattr(self.settings, "document_chunk_delimiter", "\n。；！？"),
            overlapped_percent=getattr(self.settings, "document_chunk_overlap_percent", 0),
            children_delimiter=getattr(self.settings, "document_children_delimiter", ""),
            table_context_size=getattr(self.settings, "document_table_context_size", 0),
            image_context_size=getattr(self.settings, "document_image_context_size", 0),
        )

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
        # 附带文档级向量摘要，使解析轮询返回的 file 与列表接口同形；前端文件层圆点据此判定「已嵌入(绿)/其余(黄)」。
        file_record = record
        file_id = record.get("id")
        if file_id and "embedding_summary" not in file_record:
            file_record = {
                **record,
                "embedding_summary": self.database().get_import_file_embedding_summary(file_id),
            }
        return {
            "file": file_record,
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

    def update_import_chunk_text(self, chunk_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """保存用户编辑后的切片原文，并返回文档向量状态摘要。"""
        source_text = str(payload.get("source_text", "")).strip()
        if not source_text:
            raise AdminValidationError("source_text is required")
        item = self.database().update_import_chunk_text(chunk_id, source_text)
        return {
            "item": item,
            "embedding_summary": self.database().get_import_file_embedding_summary(item["file_id"]),
        }

    def embed_import_file(self, file_id: str) -> dict[str, Any]:
        """把解析完成的文档切片生成向量并写入统一知识单元表。"""
        record = self.database().get_import_file(file_id)
        if record is None:
            raise AdminNotFoundError(f"Import file not found: {file_id}")
        if record.get("status") not in {"needs_review", "completed"}:
            raise AdminValidationError("document must be parsed before embedding")
        chunks = self.database().list_import_chunks(file_id)
        if not chunks:
            raise AdminValidationError("parsed document has no chunks")

        # 只嵌"非绿"切片：跳过已索引(ready)与已禁用切片，避免重复消耗 embedding 调用。
        pending_chunks = [
            chunk
            for chunk in chunks
            if not chunk.get("is_disabled") and chunk.get("embedding_status") != "ready"
        ]

        embedding_client = self.embedding_client()
        rows = []
        for chunk in pending_chunks:
            for chunk_row in document_knowledge_rows_for_embedding(chunk, record):
                vector = embedding_client.embed(chunk_row["embedding_text"])
                rows.append(
                    self.database().upsert_knowledge_chunk(
                        chunk_row,
                        vector,
                        embedding_model=embedding_client.model,
                        embedding_dimensions=embedding_client.dimensions,
                    )
                )
        return {
            "file_id": file_id,
            "count": len(rows),
            "items": rows,
            "embedding_summary": self.database().get_import_file_embedding_summary(file_id),
        }

    def embed_import_chunk(self, chunk_id: str) -> dict[str, Any]:
        """对单个切片重新生成向量，不影响同文档其他切片。
        典型场景是编辑切片原文后 embedding 被标记为 stale，用户单独刷新这一片。
        """
        chunk = self.database().get_import_chunk(chunk_id)
        if chunk is None:
            raise AdminNotFoundError(f"Import chunk not found: {chunk_id}")
        record = self.database().get_import_file(chunk["file_id"])
        if record is None:
            raise AdminNotFoundError(f"Import file not found: {chunk['file_id']}")

        embedding_client = self.embedding_client()
        rows = []
        for chunk_row in document_knowledge_rows_for_embedding(chunk, record):
            vector = embedding_client.embed(chunk_row["embedding_text"])
            rows.append(
                self.database().upsert_knowledge_chunk(
                    chunk_row,
                    vector,
                    embedding_model=embedding_client.model,
                    embedding_dimensions=embedding_client.dimensions,
                )
            )
        return {
            "chunk_id": chunk_id,
            "file_id": chunk["file_id"],
            "count": len(rows),
            "items": rows,
            "embedding_summary": self.database().get_import_file_embedding_summary(chunk["file_id"]),
            "messages": [f"已重新生成切片向量 ({len(rows)} 条)"],
        }

    def get_import_file_for_download(self, file_id: str) -> tuple[dict[str, Any], Path]:
        """返回可下载的原件路径，关键约束是必须来自已登记导入文件。"""
        record = self.database().get_import_file(file_id)
        if record is None:
            raise AdminNotFoundError(f"Import file not found: {file_id}")
        stored_path = Path(record["stored_path"])
        if not stored_path.exists():
            raise AdminValidationError("stored upload file is missing")
        return record, stored_path

    def get_import_asset(self, file_id: str, asset_relpath: str) -> tuple[dict[str, Any], Path]:
        """返回 MinerU 资产文件（image / table_img / equation_img）的本地路径。

        关键约束：拼出的最终路径必须落在 `<upload_dir>/mineru-assets/<safe(file_id)>/` 之内，
        防止 `../` 逃逸；文件不存在或对应 import_file 没登记都报 404。
        """
        record = self.database().get_import_file(file_id)
        if record is None:
            raise AdminNotFoundError(f"Import file not found: {file_id}")
        asset_root = Path(self.settings.upload_dir) / "mineru-assets" / safe_upload_name(file_id)
        if not str(asset_relpath or "").strip():
            raise AdminValidationError("asset path is required")
        candidate = asset_root / asset_relpath
        resolved = ensure_upload_path_within(asset_root, candidate)
        if not resolved.exists() or not resolved.is_file():
            raise AdminNotFoundError(f"Asset not found: {asset_relpath}")
        return record, resolved

    def delete_import_file(self, file_id: str) -> dict[str, Any]:
        """删除导入文件记录和本地原件，数据库级联清理切片与候选 FAQ。

        把要展示给用户的提示文案在后端组装好放在 `messages` 数组中返回；
        前端不解析业务字段，只对 messages 数组逐条调通用 toast，保持 UI 与业务解耦。
        """
        record = self.database().delete_import_file(file_id)
        if record is None:
            raise AdminNotFoundError(f"Import file not found: {file_id}")
        stored_path = Path(record.get("stored_path") or "")
        if stored_path.exists():
            stored_path.unlink()
        chunk_count = int(record.get("_deleted_chunk_count") or 0)
        vector_count = int(record.get("_deleted_vector_count") or 0)
        messages = ["已删除文件原件"]
        if chunk_count > 0:
            messages.append(f"已清理文档切片 {chunk_count} 个")
        if vector_count > 0:
            messages.append(f"已清理向量索引 {vector_count} 条")
        return {
            "deleted": True,
            "id": file_id,
            "messages": messages,
        }

    def set_import_file_disabled(
        self, file_id: str, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        """切换文件级禁用开关，RAG 检索立即跳过该文件下所有切片。"""
        if "is_disabled" not in payload:
            raise AdminValidationError("is_disabled is required")
        is_disabled = bool(payload.get("is_disabled"))
        record = self.database().set_import_file_disabled(file_id, is_disabled)
        if record is None:
            raise AdminNotFoundError(f"Import file not found: {file_id}")
        return {"item": record}

    def set_import_chunk_disabled(
        self, chunk_id: str, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        """切换切片级禁用开关，仅作用于单个切片。"""
        if "is_disabled" not in payload:
            raise AdminValidationError("is_disabled is required")
        is_disabled = bool(payload.get("is_disabled"))
        record = self.database().set_import_chunk_disabled(chunk_id, is_disabled)
        if record is None:
            raise AdminNotFoundError(f"Import chunk not found: {chunk_id}")
        return {"item": record}

    def generate_import_file_questions(
        self, file_id: str, payload: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        """批量为文档每个切片生成假设性用户问题，落库 questions 字段。

        - 默认跳过已 `ready` 的切片；payload 传 `force=True` 时全部重算
        - 单条失败写 `questions_error` 不阻塞其余切片
        - 返回 messages 数组供前端 toast 逐条弹出（按通用 UI 约定，后端拼好文案）
        """
        force = bool((payload or {}).get("force"))
        record = self.database().get_import_file(file_id)
        if record is None:
            raise AdminNotFoundError(f"Import file not found: {file_id}")
        chunks = self.database().list_import_chunks(file_id)
        if not chunks:
            raise AdminValidationError("parsed document has no chunks")

        assistant = ImportQuestionAssistant(self.chat_client())
        ready = 0
        skipped = 0
        failed = 0
        source_title = str(record.get("original_name") or "").strip()
        for chunk in chunks:
            if not force and str(chunk.get("questions_status") or "") == "ready":
                skipped += 1
                continue
            source_text = str(chunk.get("source_text") or "").strip()
            if not source_text:
                # 没有正文（极端：只有图片资产的切片）— 标记 skipped 不算失败
                self.database().set_import_chunk_questions(
                    chunk["id"], [], model=assistant.model, status="skipped"
                )
                skipped += 1
                continue
            try:
                questions = assistant.generate_questions(
                    source_text=source_text,
                    section_path=list(chunk.get("section_path") or []),
                    source_title=source_title,
                    block_type=str(chunk.get("block_type") or "") or None,
                )
            except ImportQuestionError as exc:
                self.database().set_import_chunk_questions(
                    chunk["id"], [], model=assistant.model, status="failed", error=str(exc)
                )
                failed += 1
                continue
            self.database().set_import_chunk_questions(
                chunk["id"], questions, model=assistant.model, status="ready"
            )
            ready += 1

        messages: list[str] = []
        if ready:
            messages.append(f"已为 {ready} 个切片生成假设问题")
        if skipped:
            messages.append(f"跳过 {skipped} 个切片（已生成或无正文）")
        if failed:
            messages.append(f"{failed} 个切片生成失败")
        if not messages:
            messages.append("没有需要处理的切片")
        return {
            "file_id": file_id,
            "ready": ready,
            "skipped": skipped,
            "failed": failed,
            "messages": messages,
        }

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

    def iter_assistant_chat_events(self, payload: dict[str, Any]):
        """执行基础 RAG 问答并产出流式事件，当前链路包含意图识别和混合召回。"""
        question = str(payload.get("question", "")).strip()
        if not question:
            raise AdminValidationError("question is required")
        flow_id = str(payload.get("flow_id", "basic_rag")).strip() or "basic_rag"
        if flow_id != "basic_rag":
            raise AdminValidationError("only basic_rag flow is supported")

        available_nodes = [
            "input_question",
            "query_embedding",
            "intent_detection",
            "vector_search",
            "keyword_search",
            "hybrid_retrieval",
            "kg_query",
            "rerank",
            "source_context",
            "answer_generation",
            "quality_check",
        ]
        yield {
            "type": "meta",
            "flow_id": "basic_rag",
            "flow_name": "基础 RAG",
            "stream": True,
            "available_nodes": available_nodes,
            "enabled_nodes": [
                "input_question",
                "intent_detection",
                "query_embedding",
                "vector_search",
                "keyword_search",
                "hybrid_retrieval",
                "source_context",
                "answer_generation",
            ],
        }

        started = time.perf_counter()
        chat = self._chat_client_for_payload(payload)
        yield assistant_step_event(
            "input_question",
            "输入问题",
            "completed",
            started,
            summary=question,
        )

        intent_started = time.perf_counter()
        analysis = analyze_query(question, chat)
        yield assistant_step_event(
            "intent_detection",
            "意图识别",
            "completed",
            intent_started,
            summary=f"{analysis.intent} / {analysis.confidence}",
            analysis=analysis.to_dict(),
        )

        embedding_started = time.perf_counter()
        retrieval_query = analysis.query_rewrite or question
        query_embedding = self.embedding_client().embed(retrieval_query)
        yield assistant_step_event(
            "query_embedding",
            "向量化",
            "completed",
            embedding_started,
            summary=f"{len(query_embedding)} 维查询向量",
            dimensions=len(query_embedding),
            query=retrieval_query,
        )

        search_started = time.perf_counter()
        top_k = getattr(self.settings, "rag_top_k", 5)
        min_score = getattr(self.settings, "rag_min_score", 0.35)
        rerank_client = self.rerank_client()
        rerank_input_size = int(getattr(rerank_client, "input_size", 0) or 0)
        candidate_limit = max(top_k * 2, top_k, rerank_input_size)
        query_terms = build_keyword_terms(retrieval_query, self._retrieval_aliases())
        vector_docs = self.database().search_knowledge(
            query_embedding,
            top_k=candidate_limit,
            min_score=min_score,
        )
        keyword_docs = self.database().search_knowledge_text(
            retrieval_query,
            top_k=candidate_limit,
            query_terms=query_terms,
        )
        fused = fuse_retrieval_candidates(
            vector_docs=vector_docs,
            keyword_docs=keyword_docs,
            top_k=candidate_limit,
        )
        rerank_used = False
        if rerank_client is not None and len(fused) > top_k:
            rerank_started = time.perf_counter()
            fused = rerank_candidates(retrieval_query, fused, client=rerank_client, top_k=top_k)
            rerank_used = True
            yield assistant_step_event(
                "rerank",
                "重排",
                "completed",
                rerank_started,
                summary=f"rerank 输入 {min(len(vector_docs) + len(keyword_docs), rerank_input_size or len(fused))} 候选，截取 top {top_k}",
                top_k=top_k,
                input_size=rerank_input_size,
                model=getattr(rerank_client, "model", None),
            )
        else:
            fused = fused[:top_k]
        docs = [candidate.document for candidate in fused]
        documents = []
        for candidate in fused:
            payload_doc = assistant_document_payload(candidate.document)
            payload_doc.update(
                {
                    "retrieval_channels": list(candidate.channels),
                    "fused_score": candidate.fused_score,
                    "vector_score": candidate.vector_score,
                    "keyword_score": candidate.keyword_score,
                }
            )
            documents.append(payload_doc)
        parent_docs = parent_context_documents(self.database(), docs)
        if parent_docs:
            docs.extend(parent_docs)
            for parent_doc in parent_docs:
                payload_doc = assistant_document_payload(parent_doc)
                payload_doc.update(
                    {
                        "retrieval_channels": ["parent_context"],
                        "fused_score": None,
                        "vector_score": None,
                        "keyword_score": None,
                    }
                )
                documents.append(payload_doc)
        yield assistant_step_event(
            "hybrid_retrieval",
            "混合召回",
            "completed",
            search_started,
            summary=f"向量 {len(vector_docs)} 条，关键词 {len(keyword_docs)} 条，融合后 {len(documents)} 条",
            top_k=top_k,
            min_score=min_score,
            candidate_limit=candidate_limit,
            vector_count=len(vector_docs),
            keyword_count=len(keyword_docs),
            query_terms=query_terms,
            documents=documents,
        )

        context_started = time.perf_counter()
        top_score = documents[0]["score"] if documents else None
        yield assistant_step_event(
            "source_context",
            "命中来源",
            "completed",
            context_started,
            summary=f"最高分 {top_score:.2f}" if top_score is not None else "未检索到可用来源",
            documents=documents,
        )

        answer_started = time.perf_counter()
        yield assistant_step_event(
            "answer_generation",
            "生成回答",
            "running",
            answer_started,
            summary="模型正在流式生成回答",
        )
        prompt = build_user_prompt(question, docs)
        answer_parts: list[str] = []
        system_prompt = self.assistant_system_prompt_from_payload(payload)
        for text in chat.stream_complete(system_prompt, prompt):
            answer_parts.append(text)
            yield {"type": "delta", "text": text}

        answer_draft = "".join(answer_parts).strip()
        if not answer_draft:
            answer_draft = "模型服务暂时没有返回有效内容，请稍后重试或转人工处理。"
            yield {"type": "delta", "text": answer_draft}
        yield assistant_step_event(
            "answer_generation",
            "生成回答",
            "completed",
            answer_started,
            summary=f"输出 {len(answer_draft)} 个字符",
        )
        yield {
            "type": "done",
            "flow_id": "basic_rag",
            "question": question,
            "answer_draft": answer_draft,
            "documents": documents,
        }
        self._record_assistant_chat_event(
            question=question,
            analysis=analysis,
            documents=documents,
            payload=payload,
            started=started,
            rerank_used=rerank_used,
        )

    def _record_assistant_chat_event(
        self,
        *,
        question: str,
        analysis: Any,
        documents: list[dict[str, Any]],
        payload: dict[str, Any],
        started: float,
        rerank_used: bool,
    ) -> None:
        """把 RAG 主路径的一次查询写入 query_analytics_events，失败不影响主流程。"""
        record = getattr(self.database(), "record_query_event", None)
        if record is None:
            return
        hit_count = len(documents)
        top_score = documents[0].get("score") if documents else None
        chunk_ids = [str(doc.get("id") or "") for doc in documents if doc.get("id")]
        requester_type = str(payload.get("requester_type") or "unknown").strip() or "unknown"
        requester_id_raw = payload.get("requester_id")
        requester_id = str(requester_id_raw).strip() if requester_id_raw else None
        latency_ms = int((time.perf_counter() - started) * 1000)
        intent = getattr(analysis, "intent", None)
        event = {
            "query": question,
            "intent": intent,
            "retrieved_chunk_ids": chunk_ids,
            "top_score": top_score,
            "hit_count": hit_count,
            "rerank_used": bool(rerank_used),
            "latency_ms": latency_ms,
            "requester_type": requester_type,
            "requester_id": requester_id,
            "metadata": {"flow": "basic_rag"},
        }
        try:
            record(event)
        except Exception as exc:
            logger.warning("query analytics record failed: %s", exc, exc_info=True)


def static_path(path: str) -> Path:
    """把允许访问的管理页静态路径映射到本地文件。

    管理后台是 React SPA（HashRouter），仅放行两类资源：
    1. `/` —— React 入口 `static/dist/index.html`
    2. `/static/dist/<任意子路径>` —— Vite 产物（含 hash 文件名 + 子目录），路径必须落在 `static/dist/` 之内
    """
    static_dir = Path(__file__).with_name("static")
    dist_dir = static_dir / "dist"
    clean = unquote(path).lstrip("/")
    if path in {"", "/"}:
        return dist_dir / "index.html"
    if clean.startswith("static/dist/"):
        rel = clean[len("static/dist/") :]
        candidate = (dist_dir / rel).resolve()
        try:
            candidate.relative_to(dist_dir.resolve())
        except ValueError:
            raise AdminNotFoundError(path)
        if candidate.exists() and candidate.is_file():
            return candidate
        raise AdminNotFoundError(path)
    raise AdminNotFoundError(path)


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
                if parsed.path == "/api/retrieval/eval-cases":
                    self.send_json(app.list_retrieval_eval_cases(parse_qs(parsed.query)))
                    return
                if parsed.path == "/api/retrieval/aliases":
                    self.send_json(app.list_retrieval_aliases())
                    return
                if parsed.path == "/api/import/files":
                    self.send_json(app.list_import_files(parse_qs(parsed.query)))
                    return
                if parsed.path.startswith("/api/import/files/") and parsed.path.endswith("/download"):
                    file_id = parsed.path.removeprefix("/api/import/files/").removesuffix("/download")
                    record, stored_path = app.get_import_file_for_download(file_id)
                    self.send_download(stored_path, record.get("original_name") or stored_path.name)
                    return
                if parsed.path.startswith("/api/import/files/") and "/assets/" in parsed.path:
                    # 资产路由：/api/import/files/<file_id>/assets/<relpath>
                    head, _, asset_relpath = parsed.path.removeprefix("/api/import/files/").partition("/assets/")
                    file_id = head
                    _record, asset_path = app.get_import_asset(file_id, unquote(asset_relpath))
                    self.send_static(asset_path)
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
                if parsed.path == "/api/analytics/overview":
                    self.send_json(app.analytics_overview())
                    return
                if parsed.path == "/api/analytics/top-queries":
                    self.send_json(app.list_top_queries(parse_qs(parsed.query)))
                    return
                if parsed.path == "/api/analytics/zero-hit":
                    self.send_json(app.list_zero_hit_queries(parse_qs(parsed.query)))
                    return
                if parsed.path == "/api/analytics/low-score":
                    self.send_json(app.list_low_score_queries(parse_qs(parsed.query)))
                    return
                if parsed.path == "/api/analytics/top-chunks":
                    self.send_json(app.list_top_referenced_chunks(parse_qs(parsed.query)))
                    return
                if parsed.path == "/api/analytics/hit-rate":
                    self.send_json(app.query_hit_rate_timeseries(parse_qs(parsed.query)))
                    return
                if parsed.path == "/api/analytics/cluster-summaries":
                    self.send_json(app.list_cluster_summaries(parse_qs(parsed.query)))
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
                if parsed.path == "/api/retrieval/eval-cases":
                    self.send_json(app.create_retrieval_eval_case(payload))
                    return
                if parsed.path.startswith("/api/retrieval/eval-cases/") and parsed.path.endswith("/run"):
                    case_id = parsed.path.removeprefix("/api/retrieval/eval-cases/").removesuffix("/run")
                    self.send_json(app.run_retrieval_eval_case(case_id))
                    return
                if parsed.path == "/api/retrieval/aliases":
                    self.send_json(app.save_retrieval_alias(payload))
                    return
                if parsed.path.startswith("/api/import/files/") and parsed.path.endswith("/reparse"):
                    file_id = parsed.path.removeprefix("/api/import/files/").removesuffix("/reparse")
                    self.send_json(app.reparse_import_file(file_id, payload))
                    return
                if parsed.path.startswith("/api/import/files/") and parsed.path.endswith("/parse-jobs"):
                    file_id = parsed.path.removeprefix("/api/import/files/").removesuffix("/parse-jobs")
                    self.send_json(app.start_import_parse_job(file_id, payload))
                    return
                if parsed.path.startswith("/api/import/files/") and parsed.path.endswith("/disabled"):
                    file_id = parsed.path.removeprefix("/api/import/files/").removesuffix("/disabled")
                    self.send_json(app.set_import_file_disabled(file_id, payload))
                    return
                if parsed.path.startswith("/api/import/files/") and parsed.path.endswith("/generate-questions"):
                    file_id = parsed.path.removeprefix("/api/import/files/").removesuffix("/generate-questions")
                    self.send_json(app.generate_import_file_questions(file_id, payload))
                    return
                if parsed.path.startswith("/api/import/files/") and parsed.path.endswith("/embed"):
                    file_id = parsed.path.removeprefix("/api/import/files/").removesuffix("/embed")
                    self.send_json(app.embed_import_file(file_id))
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
                if parsed.path == "/api/assistant/chat-stream":
                    requester_type = self.headers.get("X-Requester-Type")
                    requester_id = self.headers.get("X-Requester-Id")
                    if requester_type and not payload.get("requester_type"):
                        payload["requester_type"] = requester_type
                    if requester_id and not payload.get("requester_id"):
                        payload["requester_id"] = requester_id
                    self.send_sse(app.iter_assistant_chat_events(payload))
                    return
                if parsed.path == "/api/assistant/probe":
                    self.send_json(app.probe_chat_provider(payload))
                    return
                if parsed.path == "/api/assistant/models":
                    self.send_json(app.list_chat_provider_models(payload))
                    return
                if parsed.path == "/api/analytics/cluster-zero-hit":
                    self.send_json(app.cluster_zero_hit_queries(payload))
                    return
                if parsed.path == "/api/import/generation-jobs":
                    self.send_json(app.create_import_generation_job(payload))
                    return
                if parsed.path.startswith("/api/import/chunks/") and parsed.path.endswith("/generate"):
                    chunk_id = parsed.path.removeprefix("/api/import/chunks/").removesuffix("/generate")
                    self.send_json(app.generate_import_candidates(chunk_id))
                    return
                if parsed.path.startswith("/api/import/chunks/") and parsed.path.endswith("/disabled"):
                    chunk_id = parsed.path.removeprefix("/api/import/chunks/").removesuffix("/disabled")
                    self.send_json(app.set_import_chunk_disabled(chunk_id, payload))
                    return
                if parsed.path.startswith("/api/import/chunks/") and parsed.path.endswith("/embed"):
                    chunk_id = parsed.path.removeprefix("/api/import/chunks/").removesuffix("/embed")
                    self.send_json(app.embed_import_chunk(chunk_id))
                    return
                if parsed.path.startswith("/api/import/chunks/"):
                    chunk_id = parsed.path.removeprefix("/api/import/chunks/")
                    if "/" not in chunk_id:
                        self.send_json(app.update_import_chunk_text(chunk_id, payload))
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
            ensure_request_size(length, app.settings.admin_max_json_bytes, "json")
            raw = self.rfile.read(length).decode("utf-8")
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise AdminValidationError("request body must be valid JSON") from exc
            if not isinstance(payload, dict):
                raise AdminValidationError("request body must be a JSON object")
            return payload

        def read_multipart_file(self) -> tuple[str, bytes]:
            """读取单文件上传表单，当前只接受字段名 file。

            关键约束：在读 body 之前先按 admin_max_request_bytes 守门，避免恶意
            Content-Length 把 GB 级请求体灌进内存。
            """
            content_type = self.headers.get("Content-Type", "")
            boundary_match = re.search(r"boundary=(.+)", content_type)
            if not boundary_match:
                raise AdminValidationError("multipart boundary is required")
            boundary = boundary_match.group(1).strip('"').encode("utf-8")
            length = int(self.headers.get("Content-Length", "0"))
            ensure_request_size(length, app.settings.admin_max_request_bytes, "upload")
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
            try:
                for event in events:
                    self.wfile.write(format_sse_event(event).encode("utf-8"))
                    self.wfile.flush()
            except Exception as exc:
                _, sanitized_body = classify_error_response(exc)
                if sanitized_body["error"] == "internal error":
                    logger.warning("sse stream failed: %s", exc, exc_info=True)
                error_event = {"type": "error", "error": sanitized_body["error"]}
                self.wfile.write(format_sse_event(error_event).encode("utf-8"))
                self.wfile.flush()

        def send_error_json(self, exc: Exception) -> None:
            """统一响应错误；500 类异常写完整堆栈到日志，前端只看到固定文案。"""
            status, body = classify_error_response(exc)
            if status == HTTPStatus.INTERNAL_SERVER_ERROR:
                logger.error(
                    "admin handler internal error: %s\n%s", exc, traceback.format_exc()
                )
            self.send_json(body, status=status)

        def log_message(self, format: str, *args: Any) -> None:
            return

    return AdminHandler


def run_admin_server(settings: Settings, *, host: str, port: int) -> None:
    """启动本地后台 HTTP 服务；非 loopback host 必须显式 env 同意，避免误暴露。

    用 ThreadingHTTPServer 而不是单线程 HTTPServer：embed 这类阻塞调用（同步循环请求 OpenAI embedding API）
    可能持续几十秒到几分钟，单线程会让期间所有其他请求（含轮询解析进度、刷新列表）全部排队卡死。
    """
    ensure_loopback_or_explicit_opt_in(host, os.environ)
    app = AdminApp(settings)
    app.database().init_schema()
    server = ThreadingHTTPServer((host, port), make_handler(app))
    print(f"Customer Service Agent admin: http://{host}:{port}", flush=True)
    server.serve_forever()
