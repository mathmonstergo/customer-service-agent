from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import psycopg
from psycopg.rows import dict_row


def format_vector(values: Iterable[float]) -> str:
    return "[" + ",".join(str(float(value)) for value in values) + "]"


def score_to_distance(score: float) -> float:
    return 1.0 - score


def _count_job_item_statuses(items: list[dict[str, Any]]) -> dict[str, int]:
    """统计生成任务子项状态，写入任务摘要字段。"""
    return {
        "queued_count": sum(1 for item in items if item["status"] == "queued"),
        "processing_count": sum(1 for item in items if item["status"] == "processing"),
        "generated_count": sum(1 for item in items if item["status"] == "generated"),
        "skipped_count": sum(1 for item in items if item["status"] == "skipped"),
        "failed_count": sum(1 for item in items if item["status"] == "failed"),
    }


def _clean_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return [str(item).strip() for item in value if str(item).strip()]


def build_embedding_text(row: dict[str, Any]) -> str:
    """把 FAQ 问题、答案和标签拼成单条向量文本，保持一条 FAQ 一个向量。"""
    question = str(row.get("question", "")).strip()
    answer = str(row.get("answer", "")).strip()
    variants = _clean_list(row.get("question_variants"))
    tags = _clean_list(row.get("tags"))
    category = str(row.get("category", "") or "").strip()

    parts = [f"标准问题：{question}"]
    if variants:
        parts.append(f"相似问法：{'；'.join(variants)}")
    parts.append(f"答案：{answer}")
    if category:
        parts.append(f"分类：{category}")
    if tags:
        parts.append(f"标签：{'，'.join(tags)}")
    return "\n".join(parts)


def _join_search_text(parts: Iterable[Any]) -> str:
    """拼接全文检索文本，关键约束是跳过空值并保留中文原文。"""
    values: list[str] = []
    for part in parts:
        if part is None:
            continue
        if isinstance(part, list):
            values.extend(str(item).strip() for item in part if str(item).strip())
            continue
        text = str(part).strip()
        if text:
            values.append(text)
    return "\n".join(values)


def compute_knowledge_chunk_hash(row: dict[str, Any]) -> str:
    """按统一知识单元的向量文本计算指纹，用于后续判断 embedding 是否过期。"""
    payload = {"embedding_text": row["embedding_text"]}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def empty_import_file_embedding_summary() -> dict[str, Any]:
    """构造文档向量空摘要，关键约束是字段稳定供前端直接渲染。"""
    return {
        "status": "none",
        "total_chunks": 0,
        "knowledge_count": 0,
        "ready_count": 0,
        "stale_count": 0,
        "failed_count": 0,
        "pending_count": 0,
        "missing_count": 0,
    }


def build_faq_knowledge_chunk_row(row: dict[str, Any]) -> dict[str, Any]:
    """把正式 FAQ 映射为统一知识单元，保持一条 FAQ 对应一个 chunk。"""
    question = str(row.get("question", "")).strip()
    answer = str(row.get("answer", "")).strip()
    variants = _clean_list(row.get("question_variants"))
    tags = _clean_list(row.get("tags"))
    category = str(row.get("category", "") or "").strip()
    content_parts = [f"问题：{question}"]
    if variants:
        content_parts.append(f"相似问法：{'；'.join(variants)}")
    content_parts.append(f"答案：{answer}")
    embedding_text = row.get("embedding_text") or build_embedding_text(row)
    metadata = {
        "category": category or None,
        "question_variants": variants,
        "evidence": row.get("evidence", []),
        "source_file": row.get("source_file"),
        "source_group": row.get("source_group"),
        "source_date": row.get("source_date"),
    }
    chunk = {
        "id": f"kc_faq_{row['id']}",
        "source_type": "faq",
        "source_id": row["id"],
        "source_chunk_id": None,
        "source_title": question,
        "chunk_index": 0,
        "content": "\n".join(content_parts),
        "embedding_text": embedding_text,
        "search_text": _join_search_text([question, variants, answer, category, tags]),
        "metadata": metadata,
        "tags": tags,
        "confidence": row.get("confidence"),
        "status": row.get("status", "usable"),
    }
    chunk["content_hash"] = compute_knowledge_chunk_hash(chunk)
    return chunk


def build_document_knowledge_chunk_row(
    chunk: dict[str, Any],
    import_file: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """把导入文档切片映射为统一知识单元，默认不直接进入可检索状态。"""
    import_file = import_file or {}
    source_text = str(chunk.get("source_text", "")).strip()
    keywords = _clean_list(chunk.get("keywords"))
    source_title = str(import_file.get("original_name") or chunk.get("file_id") or "").strip()
    source_id = str(import_file.get("id") or chunk.get("file_id")).strip()
    metadata = {
        "file_id": chunk.get("file_id"),
        "file_name": import_file.get("original_name"),
        "file_type": import_file.get("file_type"),
        "parser": import_file.get("parser"),
        "chunk_id": chunk.get("id"),
        "start_at": str(chunk.get("start_at")) if chunk.get("start_at") else None,
        "end_at": str(chunk.get("end_at")) if chunk.get("end_at") else None,
        "message_count": chunk.get("message_count", 0),
    }
    row = {
        "id": f"kc_document_{chunk['id']}",
        "source_type": "document",
        "source_id": source_id,
        "source_chunk_id": chunk.get("id"),
        "source_title": source_title or None,
        "chunk_index": int(chunk.get("chunk_index", 0)),
        "content": source_text,
        "embedding_text": source_text,
        "search_text": _join_search_text([source_title, keywords, source_text]),
        "metadata": metadata,
        "tags": keywords,
        "confidence": None,
        "status": chunk.get("retrieval_status", "needs_review"),
    }
    row["content_hash"] = compute_knowledge_chunk_hash(row)
    return row


def compute_content_hash(row: dict[str, Any]) -> str:
    """只按会进入 embedding 的文本计算内容指纹。"""
    payload = {"embedding_text": row.get("embedding_text") or build_embedding_text(row)}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def next_embedding_status(
    previous_status: str | None,
    previous_hash: str | None,
    new_hash: str,
) -> str:
    if previous_status == "ready" and previous_hash == new_hash:
        return "ready"
    if previous_status == "ready":
        return "stale"
    if previous_status in {"stale", "failed"} and previous_hash == new_hash:
        return previous_status
    return "pending"


def build_import_candidate_faq_row(candidate: dict[str, Any]) -> dict[str, Any]:
    """把导入候选 FAQ 转成正式 FAQ 保存载荷，默认仍需人工审核。"""
    evidence = [
        {
            "source_file": candidate.get("file_name"),
            "chunk_id": candidate.get("chunk_id"),
            "excerpt": candidate.get("source_excerpt"),
        }
    ]
    row = {
        "id": f"faq_{candidate['id']}",
        "doc_type": "faq_qa",
        "source_file": candidate.get("file_name"),
        "source_group": "import_review",
        "category": candidate.get("category"),
        "question": candidate["question"],
        "question_variants": candidate.get("similar_questions") or [],
        "answer": candidate["answer"],
        "tags": candidate.get("tags") or [],
        "evidence": evidence,
        "confidence": candidate.get("confidence") or "medium",
        "status": "needs_review",
        "sensitivity": None,
    }
    row["embedding_text"] = build_embedding_text(row)
    return row


@dataclass(frozen=True)
class RetrievedDocument:
    id: str
    question: str
    answer: str
    category: str | None
    tags: list[str]
    source_date: str | None
    confidence: str
    status: str
    score: float


@dataclass(frozen=True)
class RetrievedKnowledgeChunk:
    """统一知识单元检索结果，兼容 FAQ 和文档切片两类来源。"""

    id: str
    source_type: str
    source_id: str
    source_chunk_id: str | None
    source_title: str | None
    content: str
    metadata: dict[str, Any]
    tags: list[str]
    confidence: str | None
    status: str
    score: float

    @property
    def question(self) -> str:
        """兼容旧 RAG prompt 的问题字段，文档切片使用来源标题。"""
        return self.source_title or self.source_id

    @property
    def answer(self) -> str:
        """兼容旧 RAG prompt 的答案字段，统一返回可引用正文。"""
        return self.content

    @property
    def category(self) -> str | None:
        """兼容旧 RAG prompt 的分类字段，优先使用元数据分类。"""
        return self.metadata.get("category") or self.source_type

    @property
    def source_date(self) -> str | None:
        """兼容旧 RAG prompt 的来源日期字段，来自元数据。"""
        value = self.metadata.get("source_date")
        return str(value) if value else None


class Database:
    def __init__(self, database_url: str):
        self.database_url = database_url

    def connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def init_schema(self, sql_path: str | Path = "sql/001_init.sql") -> None:
        sql = Path(sql_path).read_text(encoding="utf-8")
        with self.connect() as conn:
            conn.execute(sql)

    def upsert_faq(
        self,
        row: dict[str, Any],
        embedding: list[float],
        *,
        embedding_model: str | None = None,
        embedding_dimensions: int | None = None,
    ) -> None:
        embedding_text = row.get("embedding_text") or build_embedding_text(row)
        content_hash = compute_content_hash({**row, "embedding_text": embedding_text})
        payload = {
            "id": row["id"],
            "doc_type": row.get("doc_type", "faq_qa"),
            "source_file": row.get("source_file"),
            "source_group": row.get("source_group"),
            "source_date": row.get("source_date"),
            "category": row.get("category"),
            "question": row["question"],
            "question_variants": json.dumps(row.get("question_variants", []), ensure_ascii=False),
            "answer": row["answer"],
            "tags": json.dumps(row.get("tags", []), ensure_ascii=False),
            "evidence": json.dumps(row.get("evidence", []), ensure_ascii=False),
            "confidence": row["confidence"],
            "status": row["status"],
            "sensitivity": row.get("sensitivity"),
            "embedding_text": embedding_text,
            "embedding": format_vector(embedding),
            "embedding_status": "ready",
            "embedding_model": embedding_model,
            "embedding_dimensions": embedding_dimensions,
            "embedding_error": None,
            "content_hash": content_hash,
        }
        sql = """
        INSERT INTO faq_documents (
            id, doc_type, source_file, source_group, source_date, category,
            question, question_variants, answer, tags, evidence, confidence,
            status, sensitivity, embedding_text, embedding, embedding_status,
            embedding_model, embedding_dimensions, embedding_updated_at,
            embedding_error, content_hash
        )
        VALUES (
            %(id)s, %(doc_type)s, %(source_file)s, %(source_group)s, %(source_date)s, %(category)s,
            %(question)s, %(question_variants)s::jsonb, %(answer)s, %(tags)s::jsonb,
            %(evidence)s::jsonb, %(confidence)s, %(status)s, %(sensitivity)s,
            %(embedding_text)s, %(embedding)s::vector, %(embedding_status)s,
            %(embedding_model)s, %(embedding_dimensions)s, now(),
            %(embedding_error)s, %(content_hash)s
        )
        ON CONFLICT (id) DO UPDATE SET
            doc_type = EXCLUDED.doc_type,
            source_file = EXCLUDED.source_file,
            source_group = EXCLUDED.source_group,
            source_date = EXCLUDED.source_date,
            category = EXCLUDED.category,
            question = EXCLUDED.question,
            question_variants = EXCLUDED.question_variants,
            answer = EXCLUDED.answer,
            tags = EXCLUDED.tags,
            evidence = EXCLUDED.evidence,
            confidence = EXCLUDED.confidence,
            status = EXCLUDED.status,
            sensitivity = EXCLUDED.sensitivity,
            embedding_text = EXCLUDED.embedding_text,
            embedding = EXCLUDED.embedding,
            embedding_status = EXCLUDED.embedding_status,
            embedding_model = EXCLUDED.embedding_model,
            embedding_dimensions = EXCLUDED.embedding_dimensions,
            embedding_updated_at = EXCLUDED.embedding_updated_at,
            embedding_error = EXCLUDED.embedding_error,
            content_hash = EXCLUDED.content_hash,
            updated_at = now()
        """
        with self.connect() as conn:
            conn.execute(sql, payload)

    def get_faq(self, faq_id: str) -> dict[str, Any] | None:
        sql = "SELECT * FROM faq_documents WHERE id = %(id)s"
        with self.connect() as conn:
            return conn.execute(sql, {"id": faq_id}).fetchone()

    def save_faq_text(self, row: dict[str, Any]) -> dict[str, Any]:
        existing = self.get_faq(row["id"])
        embedding_text = row.get("embedding_text") or build_embedding_text(row)
        new_hash = compute_content_hash({**row, "embedding_text": embedding_text})
        previous_hash = existing["content_hash"] if existing else None
        if existing and existing.get("embedding_text") == embedding_text:
            previous_hash = new_hash
        embedding_status = next_embedding_status(
            existing["embedding_status"] if existing else None,
            previous_hash,
            new_hash,
        )
        payload = {
            "id": row["id"],
            "doc_type": row.get("doc_type", "faq_qa"),
            "source_file": row.get("source_file"),
            "source_group": row.get("source_group"),
            "source_date": row.get("source_date"),
            "category": row.get("category"),
            "question": row["question"],
            "question_variants": json.dumps(_clean_list(row.get("question_variants")), ensure_ascii=False),
            "answer": row["answer"],
            "tags": json.dumps(_clean_list(row.get("tags")), ensure_ascii=False),
            "evidence": json.dumps(row.get("evidence", []), ensure_ascii=False),
            "confidence": row.get("confidence", "high"),
            "status": row.get("status", "usable"),
            "sensitivity": row.get("sensitivity"),
            "embedding_text": embedding_text,
            "embedding_status": embedding_status,
            "embedding_error": None if embedding_status in {"pending", "stale"} else row.get("embedding_error"),
            "content_hash": new_hash,
        }
        sql = """
        INSERT INTO faq_documents (
            id, doc_type, source_file, source_group, source_date, category,
            question, question_variants, answer, tags, evidence, confidence,
            status, sensitivity, embedding_text, embedding_status,
            embedding_error, content_hash
        )
        VALUES (
            %(id)s, %(doc_type)s, %(source_file)s, %(source_group)s, %(source_date)s, %(category)s,
            %(question)s, %(question_variants)s::jsonb, %(answer)s, %(tags)s::jsonb,
            %(evidence)s::jsonb, %(confidence)s, %(status)s, %(sensitivity)s,
            %(embedding_text)s, %(embedding_status)s, %(embedding_error)s, %(content_hash)s
        )
        ON CONFLICT (id) DO UPDATE SET
            doc_type = EXCLUDED.doc_type,
            source_file = EXCLUDED.source_file,
            source_group = EXCLUDED.source_group,
            source_date = EXCLUDED.source_date,
            category = EXCLUDED.category,
            question = EXCLUDED.question,
            question_variants = EXCLUDED.question_variants,
            answer = EXCLUDED.answer,
            tags = EXCLUDED.tags,
            evidence = EXCLUDED.evidence,
            confidence = EXCLUDED.confidence,
            status = EXCLUDED.status,
            sensitivity = EXCLUDED.sensitivity,
            embedding_text = EXCLUDED.embedding_text,
            embedding_status = EXCLUDED.embedding_status,
            embedding_error = EXCLUDED.embedding_error,
            content_hash = EXCLUDED.content_hash,
            updated_at = now()
        RETURNING *
        """
        with self.connect() as conn:
            return conn.execute(sql, payload).fetchone()

    def update_faq_embedding(
        self,
        faq_id: str,
        embedding: list[float],
        *,
        embedding_model: str,
        embedding_dimensions: int,
    ) -> dict[str, Any]:
        sql = """
        UPDATE faq_documents
        SET embedding = %(embedding)s::vector,
            embedding_status = 'ready',
            embedding_model = %(embedding_model)s,
            embedding_dimensions = %(embedding_dimensions)s,
            embedding_updated_at = now(),
            embedding_error = NULL,
            updated_at = now()
        WHERE id = %(id)s
        RETURNING *
        """
        params = {
            "id": faq_id,
            "embedding": format_vector(embedding),
            "embedding_model": embedding_model,
            "embedding_dimensions": embedding_dimensions,
        }
        with self.connect() as conn:
            row = conn.execute(sql, params).fetchone()
        if row is None:
            raise KeyError(f"FAQ not found: {faq_id}")
        return row

    def upsert_knowledge_chunk(
        self,
        row: dict[str, Any],
        embedding: list[float] | None = None,
        *,
        embedding_model: str | None = None,
        embedding_dimensions: int | None = None,
    ) -> dict[str, Any]:
        """写入统一知识单元，关键约束是无向量时保持 pending 等待后续生成。"""
        embedding_text = str(row.get("embedding_text") or row["content"]).strip()
        payload = {
            "id": row["id"],
            "source_type": row["source_type"],
            "source_id": row["source_id"],
            "source_chunk_id": row.get("source_chunk_id"),
            "source_title": row.get("source_title"),
            "chunk_index": int(row.get("chunk_index", 0)),
            "content": row["content"],
            "embedding_text": embedding_text,
            "search_text": row.get("search_text") or _join_search_text(
                [row.get("source_title"), row.get("tags", []), row["content"]]
            ),
            "metadata": json.dumps(row.get("metadata", {}), ensure_ascii=False),
            "tags": json.dumps(_clean_list(row.get("tags")), ensure_ascii=False),
            "confidence": row.get("confidence"),
            "status": row.get("status", "needs_review"),
            "embedding": format_vector(embedding) if embedding is not None else None,
            "embedding_status": "ready" if embedding is not None else row.get("embedding_status", "pending"),
            "embedding_model": embedding_model,
            "embedding_dimensions": embedding_dimensions,
            "embedding_error": None if embedding is not None else row.get("embedding_error"),
            "content_hash": row.get("content_hash")
            or compute_knowledge_chunk_hash({**row, "embedding_text": embedding_text}),
        }
        with self.connect() as conn:
            return conn.execute(self._insert_knowledge_chunk_sql(), payload).fetchone()

    def sync_ready_faq_knowledge_chunks(self) -> int:
        """把已有 ready FAQ 复用原向量投影到统一知识单元表。"""
        with self.connect() as conn:
            row = conn.execute(self._sync_ready_faq_knowledge_chunks_sql()).fetchone()
        return int(row["count"])

    def mark_embedding_failed(self, faq_id: str, error: str) -> dict[str, Any]:
        sql = """
        UPDATE faq_documents
        SET embedding_status = 'failed',
            embedding_error = %(error)s,
            updated_at = now()
        WHERE id = %(id)s
        RETURNING *
        """
        with self.connect() as conn:
            row = conn.execute(sql, {"id": faq_id, "error": error[:1000]}).fetchone()
        if row is None:
            raise KeyError(f"FAQ not found: {faq_id}")
        return row

    def update_faq_statuses(self, ids: list[str], status: str) -> list[dict[str, Any]]:
        """批量更新 FAQ 可用状态，保持正文和 embedding 内容不变。"""
        sql = """
        UPDATE faq_documents
        SET status = %(status)s,
            updated_at = now()
        WHERE id = ANY(%(ids)s::text[])
        RETURNING id, question, answer, category, tags, confidence, status,
                  embedding_status, embedding_model, embedding_dimensions,
                  embedding_updated_at, embedding_error, updated_at
        """
        with self.connect() as conn:
            return conn.execute(sql, {"ids": ids, "status": status}).fetchall()

    def create_import_file(self, row: dict[str, Any]) -> dict[str, Any]:
        """创建导入文件记录，保存原件路径和格式识别结果。"""
        sql = """
        INSERT INTO import_files (
            id, original_name, stored_path, file_type, parser, status,
            message_count, chunk_count, candidate_count, error
        )
        VALUES (
            %(id)s, %(original_name)s, %(stored_path)s, %(file_type)s, %(parser)s,
            %(status)s, %(message_count)s, %(chunk_count)s, %(candidate_count)s, %(error)s
        )
        RETURNING *
        """
        payload = {
            "message_count": 0,
            "chunk_count": 0,
            "candidate_count": 0,
            "error": None,
            **row,
        }
        with self.connect() as conn:
            return conn.execute(sql, payload).fetchone()

    def update_import_file_summary(self, file_id: str, **fields: Any) -> dict[str, Any]:
        """更新导入文件解析摘要，只允许受控字段。"""
        allowed = {
            "status",
            "message_count",
            "chunk_count",
            "candidate_count",
            "error",
            "parse_batch_id",
            "parse_file_name",
            "parse_progress",
        }
        updates = {key: value for key, value in fields.items() if key in allowed}
        if not updates:
            return self.get_import_file(file_id)
        if "parse_progress" in updates:
            updates["parse_progress"] = json.dumps(updates["parse_progress"] or {}, ensure_ascii=False)
        assignments = ", ".join(
            f"{key} = %({key})s::jsonb" if key == "parse_progress" else f"{key} = %({key})s"
            for key in updates
        )
        sql = f"""
        UPDATE import_files
        SET {assignments}, updated_at = now()
        WHERE id = %(id)s
        RETURNING *
        """
        with self.connect() as conn:
            row = conn.execute(sql, {"id": file_id, **updates}).fetchone()
        if row is None:
            raise KeyError(f"Import file not found: {file_id}")
        return row

    def get_import_file(self, file_id: str) -> dict[str, Any] | None:
        """按 id 获取导入文件记录。"""
        sql = "SELECT * FROM import_files WHERE id = %(id)s"
        with self.connect() as conn:
            return conn.execute(sql, {"id": file_id}).fetchone()

    def delete_import_file(self, file_id: str) -> dict[str, Any] | None:
        """删除导入文件记录，依赖外键级联清理切块和候选 FAQ。"""
        sql = "DELETE FROM import_files WHERE id = %(id)s RETURNING *"
        with self.connect() as conn:
            return conn.execute(sql, {"id": file_id}).fetchone()

    def list_import_files(
        self,
        *,
        query: str = "",
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """列出导入文件，并返回状态计数供侧栏筛选。"""
        clauses = []
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if query:
            params["query"] = f"%{query}%"
            clauses.append("original_name ILIKE %(query)s")
        if status:
            params["status"] = status
            clauses.append("status = %(status)s")
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        rows_sql = f"""
        SELECT *
        FROM import_files
        {where}
        ORDER BY updated_at DESC, id DESC
        LIMIT %(limit)s OFFSET %(offset)s
        """
        count_sql = f"SELECT count(*) AS total FROM import_files {where}"
        status_sql = "SELECT status, count(*) AS count FROM import_files GROUP BY status"
        with self.connect() as conn:
            rows = conn.execute(rows_sql, params).fetchall()
            total = conn.execute(count_sql, params).fetchone()["total"]
            status_counts = conn.execute(status_sql).fetchall()
        summaries = self.list_import_file_embedding_summaries([row["id"] for row in rows])
        return {
            "items": [
                {
                    **row,
                    "embedding_summary": summaries.get(row["id"], empty_import_file_embedding_summary()),
                }
                for row in rows
            ],
            "total": total,
            "status_counts": {row["status"]: row["count"] for row in status_counts},
        }

    def list_import_file_embedding_summaries(self, file_ids: list[str]) -> dict[str, dict[str, Any]]:
        """批量统计文档切片向量状态，避免文档列表逐行查询。"""
        unique_ids = list(dict.fromkeys(file_ids))
        if not unique_ids:
            return {}
        with self.connect() as conn:
            rows = conn.execute(
                self._import_file_embedding_summaries_sql(),
                {"file_ids": unique_ids},
            ).fetchall()
        return {
            row["file_id"]: {
                "status": row["status"],
                "total_chunks": row["total_chunks"],
                "knowledge_count": row["knowledge_count"],
                "ready_count": row["ready_count"],
                "stale_count": row["stale_count"],
                "failed_count": row["failed_count"],
                "pending_count": row["pending_count"],
                "missing_count": row["missing_count"],
            }
            for row in rows
        }

    def get_import_file_embedding_summary(self, file_id: str) -> dict[str, Any]:
        """获取单个文档的切片向量摘要，供详情抽屉保存后刷新。"""
        return self.list_import_file_embedding_summaries([file_id]).get(
            file_id,
            empty_import_file_embedding_summary(),
        )

    def replace_import_chunks(
        self,
        file_id: str,
        chunks: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """替换某个文件的切块，重新解析时保持结果一致。"""
        with self.connect() as conn:
            conn.execute("DELETE FROM import_chunks WHERE file_id = %(file_id)s", {"file_id": file_id})
            rows = []
            for chunk in chunks:
                rows.append(conn.execute(self._insert_import_chunk_sql(), chunk).fetchone())
        return rows

    def list_import_chunks(self, file_id: str) -> list[dict[str, Any]]:
        """按文件列出时间切块。"""
        sql = """
        SELECT *
        FROM import_chunks
        WHERE file_id = %(file_id)s
        ORDER BY chunk_index ASC
        """
        with self.connect() as conn:
            return conn.execute(sql, {"file_id": file_id}).fetchall()

    def get_import_chunk(self, chunk_id: str) -> dict[str, Any] | None:
        """按 id 获取导入切块。"""
        sql = "SELECT * FROM import_chunks WHERE id = %(id)s"
        with self.connect() as conn:
            return conn.execute(sql, {"id": chunk_id}).fetchone()

    def update_import_chunk_text(self, chunk_id: str, source_text: str) -> dict[str, Any]:
        """保存切片原文，并把已有文档知识单元标记为需要重新生成向量。"""
        payload = {
            "id": chunk_id,
            "chunk_id": chunk_id,
            "source_text": source_text,
            "content_hash": compute_knowledge_chunk_hash({"embedding_text": source_text}),
        }
        with self.connect() as conn:
            row = conn.execute(self._update_import_chunk_text_sql(), payload).fetchone()
            if row is None:
                raise KeyError(f"Import chunk not found: {chunk_id}")
            conn.execute(self._mark_document_chunk_knowledge_stale_sql(), payload)
        return row

    def create_import_candidates(
        self,
        chunk: dict[str, Any],
        candidates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """保存某个切块的 AI 候选 FAQ，并更新切块候选数。"""
        with self.connect() as conn:
            rows = []
            for candidate in candidates:
                payload = {
                    "duplicate_level": "none",
                    "duplicate_score": 0,
                    "duplicate_target_id": None,
                    "duplicate_reason": None,
                    **candidate,
                }
                rows.append(conn.execute(self._insert_import_candidate_sql(), payload).fetchone())
            conn.execute(
                """
                UPDATE import_chunks
                SET status = 'generated',
                    candidate_count = %(candidate_count)s,
                    updated_at = now()
                WHERE id = %(id)s
                """,
                {"id": chunk["id"], "candidate_count": len(rows)},
            )
            conn.execute(
                """
                UPDATE import_files
                SET candidate_count = candidate_count + %(candidate_count)s,
                    updated_at = now()
                WHERE id = %(file_id)s
                """,
                {"file_id": chunk["file_id"], "candidate_count": len(rows)},
            )
        return rows

    def create_import_generation_job(self, chunk_ids: list[str]) -> dict[str, Any]:
        """创建候选生成任务，已处理或活跃中的切块会被标记为跳过。"""
        unique_chunk_ids = list(dict.fromkeys(chunk_ids))
        if not unique_chunk_ids:
            raise ValueError("chunk_ids is required")
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        with self.connect() as conn:
            chunks = conn.execute(
                """
                SELECT id, candidate_count, status
                FROM import_chunks
                WHERE id = ANY(%(ids)s::text[])
                """,
                {"ids": unique_chunk_ids},
            ).fetchall()
            chunks_by_id = {row["id"]: row for row in chunks}
            active_rows = conn.execute(
                """
                SELECT DISTINCT chunk_id
                FROM import_generation_job_items
                WHERE chunk_id = ANY(%(ids)s::text[])
                  AND status IN ('queued', 'processing')
                """,
                {"ids": unique_chunk_ids},
            ).fetchall()
            active_ids = {row["chunk_id"] for row in active_rows}
            items = []
            for chunk_id in unique_chunk_ids:
                chunk = chunks_by_id.get(chunk_id)
                status = "queued"
                reason = None
                if chunk is None:
                    status = "skipped"
                    reason = "missing_chunk"
                elif chunk["candidate_count"] > 0 or chunk["status"] == "generated":
                    status = "skipped"
                    reason = "already_generated"
                elif chunk_id in active_ids:
                    status = "skipped"
                    reason = "already_queued"
                items.append(
                    {
                        "id": f"job_item_{uuid.uuid4().hex[:12]}",
                        "job_id": job_id,
                        "chunk_id": chunk_id,
                        "status": status,
                        "reason": reason,
                        "candidate_count": 0,
                        "error": None,
                    }
                )
            counts = _count_job_item_statuses(items)
            job = conn.execute(
                """
                INSERT INTO import_generation_jobs (
                    id, status, total_count, queued_count, processing_count,
                    generated_count, skipped_count, failed_count
                )
                VALUES (
                    %(id)s, %(status)s, %(total_count)s, %(queued_count)s, %(processing_count)s,
                    %(generated_count)s, %(skipped_count)s, %(failed_count)s
                )
                RETURNING *
                """,
                {
                    "id": job_id,
                    "status": "queued" if counts["queued_count"] else "completed",
                    "total_count": len(items),
                    **counts,
                },
            ).fetchone()
            inserted_items = [
                conn.execute(self._insert_import_generation_job_item_sql(), item).fetchone()
                for item in items
            ]
        return {**job, "items": inserted_items}

    def get_import_generation_job(self, job_id: str) -> dict[str, Any] | None:
        """按 id 获取候选生成任务。"""
        sql = "SELECT * FROM import_generation_jobs WHERE id = %(id)s"
        with self.connect() as conn:
            return conn.execute(sql, {"id": job_id}).fetchone()

    def list_import_generation_job_items(self, job_id: str) -> list[dict[str, Any]]:
        """列出候选生成任务的切块子项。"""
        sql = """
        SELECT *
        FROM import_generation_job_items
        WHERE job_id = %(job_id)s
        ORDER BY created_at ASC, id ASC
        """
        with self.connect() as conn:
            return conn.execute(sql, {"job_id": job_id}).fetchall()

    def update_import_generation_job_item(self, item_id: str, **fields: Any) -> dict[str, Any]:
        """更新候选生成任务子项状态和结果。"""
        allowed = {"status", "reason", "candidate_count", "error"}
        updates = {key: value for key, value in fields.items() if key in allowed}
        if not updates:
            raise ValueError("generation job item updates are required")
        assignments = ", ".join(f"{key} = %({key})s" for key in updates)
        sql = f"""
        UPDATE import_generation_job_items
        SET {assignments}, updated_at = now()
        WHERE id = %(id)s
        RETURNING *
        """
        with self.connect() as conn:
            row = conn.execute(sql, {"id": item_id, **updates}).fetchone()
        if row is None:
            raise KeyError(f"Import generation job item not found: {item_id}")
        return row

    def update_import_generation_job_summary(self, job_id: str, status: str) -> dict[str, Any]:
        """重新统计候选生成任务摘要并写入最终状态。"""
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT status, count(*) AS count
                FROM import_generation_job_items
                WHERE job_id = %(job_id)s
                GROUP BY status
                """,
                {"job_id": job_id},
            ).fetchall()
            counts = {row["status"]: row["count"] for row in rows}
            job = conn.execute(
                """
                UPDATE import_generation_jobs
                SET status = %(status)s,
                    queued_count = %(queued_count)s,
                    processing_count = %(processing_count)s,
                    generated_count = %(generated_count)s,
                    skipped_count = %(skipped_count)s,
                    failed_count = %(failed_count)s,
                    updated_at = now()
                WHERE id = %(id)s
                RETURNING *
                """,
                {
                    "id": job_id,
                    "status": status,
                    "queued_count": counts.get("queued", 0),
                    "processing_count": counts.get("processing", 0),
                    "generated_count": counts.get("generated", 0),
                    "skipped_count": counts.get("skipped", 0),
                    "failed_count": counts.get("failed", 0),
                },
            ).fetchone()
        if job is None:
            raise KeyError(f"Import generation job not found: {job_id}")
        return job

    def list_import_candidates(self, chunk_id: str) -> list[dict[str, Any]]:
        """按切块列出候选 FAQ。"""
        sql = """
        SELECT *
        FROM import_candidates
        WHERE chunk_id = %(chunk_id)s
        ORDER BY created_at ASC, id ASC
        """
        with self.connect() as conn:
            return conn.execute(sql, {"chunk_id": chunk_id}).fetchall()

    def list_import_file_candidates(self, file_id: str) -> list[dict[str, Any]]:
        """按文件汇总候选 FAQ，并带上来源切块编号供审核列表定位。"""
        sql = """
        SELECT c.*, ch.chunk_index, ch.start_at, ch.end_at
        FROM import_candidates c
        JOIN import_chunks ch ON ch.id = c.chunk_id
        WHERE c.file_id = %(file_id)s
        ORDER BY c.updated_at DESC, c.created_at DESC, c.id ASC
        """
        with self.connect() as conn:
            return conn.execute(sql, {"file_id": file_id}).fetchall()

    def list_import_dedupe_references(self, chunk_id: str) -> list[dict[str, Any]]:
        """列出候选查重参考，包括正式 FAQ 和其它候选 FAQ。"""
        sql = """
        SELECT id, question, answer
        FROM faq_documents
        UNION ALL
        SELECT id, question, answer
        FROM import_candidates
        WHERE chunk_id <> %(chunk_id)s
          AND status IN ('pending', 'saved')
        """
        with self.connect() as conn:
            return conn.execute(sql, {"chunk_id": chunk_id}).fetchall()

    def get_import_candidate(self, candidate_id: str) -> dict[str, Any] | None:
        """获取候选 FAQ，并带上来源文件名用于保存 evidence。"""
        sql = """
        SELECT c.*, f.original_name AS file_name
        FROM import_candidates c
        JOIN import_files f ON f.id = c.file_id
        WHERE c.id = %(id)s
        """
        with self.connect() as conn:
            return conn.execute(sql, {"id": candidate_id}).fetchone()

    def update_import_candidate(self, candidate_id: str, row: dict[str, Any]) -> dict[str, Any]:
        """更新人工编辑后的候选 FAQ 内容。"""
        payload = {
            "id": candidate_id,
            "question": row["question"],
            "answer": row["answer"],
            "similar_questions": json.dumps(_clean_list(row.get("similar_questions")), ensure_ascii=False),
            "category": row.get("category"),
            "tags": json.dumps(_clean_list(row.get("tags")), ensure_ascii=False),
            "confidence": row.get("confidence", "medium"),
            "internal_note": row.get("internal_note"),
        }
        sql = """
        UPDATE import_candidates
        SET question = %(question)s,
            answer = %(answer)s,
            similar_questions = %(similar_questions)s::jsonb,
            category = %(category)s,
            tags = %(tags)s::jsonb,
            confidence = %(confidence)s,
            internal_note = %(internal_note)s,
            updated_at = now()
        WHERE id = %(id)s
        RETURNING *
        """
        with self.connect() as conn:
            result = conn.execute(sql, payload).fetchone()
        if result is None:
            raise KeyError(f"Import candidate not found: {candidate_id}")
        return result

    def mark_import_candidate_saved(self, candidate_id: str, faq_id: str) -> dict[str, Any]:
        """标记候选 FAQ 已保存到标准问答。"""
        sql = """
        UPDATE import_candidates
        SET status = 'saved',
            saved_faq_id = %(faq_id)s,
            updated_at = now()
        WHERE id = %(id)s
        RETURNING *
        """
        with self.connect() as conn:
            row = conn.execute(sql, {"id": candidate_id, "faq_id": faq_id}).fetchone()
        if row is None:
            raise KeyError(f"Import candidate not found: {candidate_id}")
        return row

    def mark_import_candidate_ignored(self, candidate_id: str) -> dict[str, Any]:
        """标记候选 FAQ 已忽略。"""
        sql = """
        UPDATE import_candidates
        SET status = 'ignored',
            updated_at = now()
        WHERE id = %(id)s
        RETURNING *
        """
        with self.connect() as conn:
            row = conn.execute(sql, {"id": candidate_id}).fetchone()
        if row is None:
            raise KeyError(f"Import candidate not found: {candidate_id}")
        return row

    @staticmethod
    def _insert_import_chunk_sql() -> str:
        """集中维护切块插入 SQL，避免多处字段漂移。"""
        return """
        INSERT INTO import_chunks (
            id, file_id, chunk_index, start_at, end_at, message_count,
            keywords, source_text, status, candidate_count
        )
        VALUES (
            %(id)s, %(file_id)s, %(chunk_index)s, %(start_at)s, %(end_at)s,
            %(message_count)s, %(keywords)s::jsonb, %(source_text)s,
            %(status)s, %(candidate_count)s
        )
        RETURNING *
        """

    @staticmethod
    def _import_file_embedding_summaries_sql() -> str:
        """集中维护文档级向量摘要 SQL，确保列表和详情状态口径一致。"""
        return """
        WITH requested AS (
            SELECT unnest(%(file_ids)s::text[]) AS file_id
        ),
        chunk_counts AS (
            SELECT file_id, count(*) AS total_chunks
            FROM import_chunks
            WHERE file_id = ANY(%(file_ids)s::text[])
            GROUP BY file_id
        ),
        knowledge_counts AS (
            SELECT
                source_id AS file_id,
                count(*) AS knowledge_count,
                count(*) FILTER (WHERE embedding_status = 'ready') AS ready_count,
                count(*) FILTER (WHERE embedding_status = 'stale') AS stale_count,
                count(*) FILTER (WHERE embedding_status = 'failed') AS failed_count,
                count(*) FILTER (WHERE embedding_status = 'pending') AS pending_count
            FROM knowledge_chunks
            WHERE source_type = 'document'
              AND source_id = ANY(%(file_ids)s::text[])
            GROUP BY source_id
        )
        SELECT
            requested.file_id,
            COALESCE(chunk_counts.total_chunks, 0)::int AS total_chunks,
            COALESCE(knowledge_counts.knowledge_count, 0)::int AS knowledge_count,
            COALESCE(knowledge_counts.ready_count, 0)::int AS ready_count,
            COALESCE(knowledge_counts.stale_count, 0)::int AS stale_count,
            COALESCE(knowledge_counts.failed_count, 0)::int AS failed_count,
            (
                COALESCE(knowledge_counts.pending_count, 0)
                + GREATEST(
                    COALESCE(chunk_counts.total_chunks, 0)
                    - COALESCE(knowledge_counts.knowledge_count, 0),
                    0
                )
            )::int AS pending_count,
            GREATEST(
                COALESCE(chunk_counts.total_chunks, 0)
                - COALESCE(knowledge_counts.knowledge_count, 0),
                0
            )::int AS missing_count,
            CASE
                WHEN COALESCE(chunk_counts.total_chunks, 0) = 0 THEN 'none'
                WHEN COALESCE(knowledge_counts.stale_count, 0) > 0 THEN 'stale'
                WHEN COALESCE(knowledge_counts.failed_count, 0) > 0
                    AND COALESCE(knowledge_counts.ready_count, 0) = 0 THEN 'failed'
                WHEN COALESCE(knowledge_counts.ready_count, 0)
                    >= COALESCE(chunk_counts.total_chunks, 0) THEN 'ready'
                WHEN COALESCE(knowledge_counts.ready_count, 0) = 0 THEN 'pending'
                ELSE 'partial'
            END AS status
        FROM requested
        LEFT JOIN chunk_counts ON chunk_counts.file_id = requested.file_id
        LEFT JOIN knowledge_counts ON knowledge_counts.file_id = requested.file_id
        """

    @staticmethod
    def _update_import_chunk_text_sql() -> str:
        """集中维护切片正文更新 SQL，只允许改原文和更新时间。"""
        return """
        UPDATE import_chunks
        SET source_text = %(source_text)s,
            updated_at = now()
        WHERE id = %(id)s
        RETURNING *
        """

    @staticmethod
    def _mark_document_chunk_knowledge_stale_sql() -> str:
        """集中维护文档切片知识单元过期标记 SQL，避免旧向量继续命中。"""
        return """
        UPDATE knowledge_chunks
        SET content = %(source_text)s,
            embedding_text = %(source_text)s,
            search_text = concat_ws(E'\n', source_title, tags::text, %(source_text)s),
            embedding_status = 'stale',
            embedding_error = NULL,
            content_hash = %(content_hash)s,
            updated_at = now()
        WHERE source_type = 'document'
          AND source_chunk_id = %(chunk_id)s
        """

    @staticmethod
    def _insert_knowledge_chunk_sql() -> str:
        """集中维护统一知识单元 upsert SQL，避免多来源写入字段漂移。"""
        return """
        INSERT INTO knowledge_chunks (
            id, source_type, source_id, source_chunk_id, source_title, chunk_index,
            content, embedding_text, search_text, metadata, tags, confidence, status,
            embedding, embedding_status, embedding_model, embedding_dimensions,
            embedding_updated_at, embedding_error, content_hash
        )
        VALUES (
            %(id)s, %(source_type)s, %(source_id)s, %(source_chunk_id)s, %(source_title)s,
            %(chunk_index)s, %(content)s, %(embedding_text)s, %(search_text)s,
            %(metadata)s::jsonb, %(tags)s::jsonb, %(confidence)s, %(status)s,
            %(embedding)s::vector, %(embedding_status)s, %(embedding_model)s,
            %(embedding_dimensions)s,
            CASE WHEN %(embedding)s IS NULL THEN NULL ELSE now() END,
            %(embedding_error)s, %(content_hash)s
        )
        ON CONFLICT (source_type, source_id, chunk_index) DO UPDATE SET
            id = EXCLUDED.id,
            source_chunk_id = EXCLUDED.source_chunk_id,
            source_title = EXCLUDED.source_title,
            content = EXCLUDED.content,
            embedding_text = EXCLUDED.embedding_text,
            search_text = EXCLUDED.search_text,
            metadata = EXCLUDED.metadata,
            tags = EXCLUDED.tags,
            confidence = EXCLUDED.confidence,
            status = EXCLUDED.status,
            embedding = EXCLUDED.embedding,
            embedding_status = EXCLUDED.embedding_status,
            embedding_model = EXCLUDED.embedding_model,
            embedding_dimensions = EXCLUDED.embedding_dimensions,
            embedding_updated_at = EXCLUDED.embedding_updated_at,
            embedding_error = EXCLUDED.embedding_error,
            content_hash = EXCLUDED.content_hash,
            updated_at = now()
        RETURNING *
        """

    @staticmethod
    def _sync_ready_faq_knowledge_chunks_sql() -> str:
        """集中维护已有 FAQ 投影 SQL，关键约束是不重新生成向量。"""
        return """
        WITH upserted AS (
            INSERT INTO knowledge_chunks (
                id, source_type, source_id, source_chunk_id, source_title, chunk_index,
                content, embedding_text, search_text, metadata, tags, confidence, status,
                embedding, embedding_status, embedding_model, embedding_dimensions,
                embedding_updated_at, embedding_error, content_hash
            )
            SELECT
                'kc_faq_' || id,
                'faq',
                id,
                NULL,
                question,
                0,
                '问题：' || question || E'\n答案：' || answer,
                embedding_text,
                concat_ws(E'\n', question, question_variants::text, answer, category, tags::text),
                jsonb_build_object(
                    'category', category,
                    'question_variants', question_variants,
                    'evidence', evidence,
                    'source_file', source_file,
                    'source_group', source_group,
                    'source_date', source_date
                ),
                tags,
                confidence,
                status,
                embedding,
                embedding_status,
                embedding_model,
                embedding_dimensions,
                embedding_updated_at,
                embedding_error,
                COALESCE(content_hash, md5(embedding_text))
            FROM faq_documents
            WHERE embedding_status = 'ready'
              AND embedding IS NOT NULL
            ON CONFLICT (source_type, source_id, chunk_index) DO UPDATE SET
                source_title = EXCLUDED.source_title,
                content = EXCLUDED.content,
                embedding_text = EXCLUDED.embedding_text,
                search_text = EXCLUDED.search_text,
                metadata = EXCLUDED.metadata,
                tags = EXCLUDED.tags,
                confidence = EXCLUDED.confidence,
                status = EXCLUDED.status,
                embedding = EXCLUDED.embedding,
                embedding_status = EXCLUDED.embedding_status,
                embedding_model = EXCLUDED.embedding_model,
                embedding_dimensions = EXCLUDED.embedding_dimensions,
                embedding_updated_at = EXCLUDED.embedding_updated_at,
                embedding_error = EXCLUDED.embedding_error,
                content_hash = EXCLUDED.content_hash,
                updated_at = now()
            RETURNING id
        )
        SELECT count(*) AS count FROM upserted
        """

    @staticmethod
    def _insert_import_candidate_sql() -> str:
        """集中维护候选 FAQ 插入 SQL，确保 API 和测试使用同一字段。"""
        return """
        INSERT INTO import_candidates (
            id, file_id, chunk_id, question, answer, similar_questions, category,
            tags, confidence, internal_note, source_excerpt, duplicate_level,
            duplicate_score, duplicate_target_id, duplicate_reason, status
        )
        VALUES (
            %(id)s, %(file_id)s, %(chunk_id)s, %(question)s, %(answer)s,
            %(similar_questions)s::jsonb, %(category)s, %(tags)s::jsonb,
            %(confidence)s, %(internal_note)s, %(source_excerpt)s, %(duplicate_level)s,
            %(duplicate_score)s, %(duplicate_target_id)s, %(duplicate_reason)s, %(status)s
        )
        RETURNING *
        """

    @staticmethod
    def _insert_import_generation_job_item_sql() -> str:
        """集中维护生成任务切块插入 SQL。"""
        return """
        INSERT INTO import_generation_job_items (
            id, job_id, chunk_id, status, reason, candidate_count, error
        )
        VALUES (
            %(id)s, %(job_id)s, %(chunk_id)s, %(status)s, %(reason)s,
            %(candidate_count)s, %(error)s
        )
        RETURNING *
        """

    def list_faqs(
        self,
        *,
        query: str = "",
        status: str | None = None,
        embedding_status: str | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> dict[str, Any]:
        clauses = []
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if query:
            params["query"] = f"%{query}%"
            clauses.append("(question ILIKE %(query)s OR answer ILIKE %(query)s OR category ILIKE %(query)s)")
        if status:
            params["status"] = status
            clauses.append("status = %(status)s")
        if embedding_status:
            params["embedding_status"] = embedding_status
            clauses.append("embedding_status = %(embedding_status)s")
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        rows_sql = f"""
        SELECT id, question, answer, category, tags, confidence, status,
               embedding_status, embedding_model, embedding_dimensions,
               embedding_updated_at, embedding_error, updated_at
        FROM faq_documents
        {where}
        ORDER BY updated_at DESC, id DESC
        LIMIT %(limit)s OFFSET %(offset)s
        """
        count_sql = f"SELECT count(*) AS total FROM faq_documents {where}"
        status_sql = "SELECT status, count(*) AS count FROM faq_documents GROUP BY status"
        embedding_sql = """
        SELECT embedding_status, count(*) AS count
        FROM faq_documents
        GROUP BY embedding_status
        """
        with self.connect() as conn:
            rows = conn.execute(rows_sql, params).fetchall()
            total = conn.execute(count_sql, params).fetchone()["total"]
            status_counts = conn.execute(status_sql).fetchall()
            embedding_counts = conn.execute(embedding_sql).fetchall()
        return {
            "items": rows,
            "total": total,
            "status_counts": {row["status"]: row["count"] for row in status_counts},
            "embedding_counts": {
                row["embedding_status"]: row["count"] for row in embedding_counts
            },
        }

    def create_retrieval_eval_case(self, row: dict[str, Any]) -> dict[str, Any]:
        """创建或更新检索评测用例，关键约束是期望命中字段统一保存为 JSONB。"""
        payload = {
            "id": row["id"],
            "question": row["question"],
            "intent": row.get("intent"),
            "expected_source_ids": json.dumps(
                _clean_list(row.get("expected_source_ids")),
                ensure_ascii=False,
            ),
            "expected_chunk_ids": json.dumps(
                _clean_list(row.get("expected_chunk_ids")),
                ensure_ascii=False,
            ),
            "tags": json.dumps(_clean_list(row.get("tags")), ensure_ascii=False),
            "note": row.get("note"),
            "status": row.get("status", "active"),
        }
        sql = """
        INSERT INTO retrieval_eval_cases (
            id, question, intent, expected_source_ids, expected_chunk_ids,
            tags, note, status
        )
        VALUES (
            %(id)s, %(question)s, %(intent)s, %(expected_source_ids)s::jsonb,
            %(expected_chunk_ids)s::jsonb, %(tags)s::jsonb, %(note)s, %(status)s
        )
        ON CONFLICT (id) DO UPDATE SET
            question = EXCLUDED.question,
            intent = EXCLUDED.intent,
            expected_source_ids = EXCLUDED.expected_source_ids,
            expected_chunk_ids = EXCLUDED.expected_chunk_ids,
            tags = EXCLUDED.tags,
            note = EXCLUDED.note,
            status = EXCLUDED.status,
            updated_at = now()
        RETURNING *
        """
        with self.connect() as conn:
            return conn.execute(sql, payload).fetchone()

    def list_retrieval_eval_cases(
        self,
        *,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """列出检索评测用例，供后端接口和后续评测页面复用。"""
        clauses = []
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if status:
            params["status"] = status
            clauses.append("status = %(status)s")
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        rows_sql = f"""
        SELECT *
        FROM retrieval_eval_cases
        {where}
        ORDER BY updated_at DESC, id DESC
        LIMIT %(limit)s OFFSET %(offset)s
        """
        count_sql = f"SELECT count(*) AS total FROM retrieval_eval_cases {where}"
        with self.connect() as conn:
            rows = conn.execute(rows_sql, params).fetchall()
            total = conn.execute(count_sql, params).fetchone()["total"]
        return {"items": rows, "total": total}

    def record_retrieval_eval_run(self, row: dict[str, Any]) -> dict[str, Any]:
        """保存单次检索评测运行结果，关键约束是完整保留候选和指标用于回放。"""
        payload = {
            "id": row.get("id") or f"eval_run_{uuid.uuid4().hex[:12]}",
            "case_id": row["case_id"],
            "strategy": row.get("strategy", "hybrid_v1"),
            "retrieved_items": json.dumps(row.get("retrieved_items", []), ensure_ascii=False),
            "metrics": json.dumps(row.get("metrics", {}), ensure_ascii=False),
            "analysis": json.dumps(row.get("analysis", {}), ensure_ascii=False),
        }
        sql = """
        INSERT INTO retrieval_eval_runs (
            id, case_id, strategy, retrieved_items, metrics, analysis
        )
        VALUES (
            %(id)s, %(case_id)s, %(strategy)s, %(retrieved_items)s::jsonb,
            %(metrics)s::jsonb, %(analysis)s::jsonb
        )
        RETURNING *
        """
        with self.connect() as conn:
            return conn.execute(sql, payload).fetchone()

    def get_retrieval_eval_case(self, case_id: str) -> dict[str, Any] | None:
        """按 id 读取检索评测用例，供单条评测运行使用。"""
        sql = "SELECT * FROM retrieval_eval_cases WHERE id = %(id)s"
        with self.connect() as conn:
            return conn.execute(sql, {"id": case_id}).fetchone()

    def list_retrieval_aliases(self, status: str = "active") -> list[dict[str, Any]]:
        """列出检索别名词典，第一版只读取启用词条用于关键词扩展。"""
        sql = """
        SELECT *
        FROM retrieval_aliases
        WHERE status = %(status)s
        ORDER BY updated_at DESC, id DESC
        """
        with self.connect() as conn:
            return conn.execute(sql, {"status": status}).fetchall()

    def upsert_retrieval_alias(self, row: dict[str, Any]) -> dict[str, Any]:
        """写入检索别名词典，关键约束是标准词和别名都由人工维护。"""
        payload = {
            "id": row.get("id") or f"alias_{uuid.uuid4().hex[:12]}",
            "canonical": str(row.get("canonical", "")).strip(),
            "aliases": json.dumps(_clean_list(row.get("aliases")), ensure_ascii=False),
            "tags": json.dumps(_clean_list(row.get("tags")), ensure_ascii=False),
            "status": row.get("status", "active"),
        }
        sql = """
        INSERT INTO retrieval_aliases (id, canonical, aliases, tags, status)
        VALUES (
            %(id)s, %(canonical)s, %(aliases)s::jsonb, %(tags)s::jsonb, %(status)s
        )
        ON CONFLICT (id) DO UPDATE SET
            canonical = EXCLUDED.canonical,
            aliases = EXCLUDED.aliases,
            tags = EXCLUDED.tags,
            status = EXCLUDED.status,
            updated_at = now()
        RETURNING *
        """
        with self.connect() as conn:
            return conn.execute(sql, payload).fetchone()

    def list_embedding_candidates(self, *, limit: int = 50) -> list[dict[str, Any]]:
        sql = """
        SELECT *
        FROM faq_documents
        WHERE embedding_status IN ('pending', 'stale', 'failed')
        ORDER BY updated_at ASC
        LIMIT %(limit)s
        """
        with self.connect() as conn:
            return conn.execute(sql, {"limit": limit}).fetchall()

    def search(
        self,
        query_embedding: list[float],
        *,
        top_k: int,
        min_score: float,
        status: str = "usable",
        confidence: str = "high",
    ) -> list[RetrievedDocument]:
        sql = """
        SELECT
            id, question, answer, category, tags, source_date, confidence, status,
            1 - (embedding <=> %(embedding)s::vector) AS score
        FROM faq_documents
        WHERE status = %(status)s
          AND embedding_status = 'ready'
          AND embedding IS NOT NULL
          AND confidence = %(confidence)s
          AND (embedding <=> %(embedding)s::vector) <= %(max_distance)s
        ORDER BY embedding <=> %(embedding)s::vector
        LIMIT %(top_k)s
        """
        params = {
            "embedding": format_vector(query_embedding),
            "status": status,
            "confidence": confidence,
            "max_distance": score_to_distance(min_score),
            "top_k": top_k,
        }
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [
            RetrievedDocument(
                id=row["id"],
                question=row["question"],
                answer=row["answer"],
                category=row["category"],
                tags=row["tags"] or [],
                source_date=row["source_date"],
                confidence=row["confidence"],
                status=row["status"],
                score=float(row["score"]),
            )
            for row in rows
        ]

    def search_knowledge(
        self,
        query_embedding: list[float],
        *,
        top_k: int,
        min_score: float,
        status: str = "usable",
    ) -> list[RetrievedKnowledgeChunk]:
        """从统一知识单元表检索内容，关键约束是不过滤 confidence 以允许文档切片命中。"""
        params = {
            "embedding": format_vector(query_embedding),
            "status": status,
            "max_distance": score_to_distance(min_score),
            "top_k": top_k,
        }
        with self.connect() as conn:
            rows = conn.execute(self._search_knowledge_sql(), params).fetchall()
        return [
            RetrievedKnowledgeChunk(
                id=row["id"],
                source_type=row["source_type"],
                source_id=row["source_id"],
                source_chunk_id=row["source_chunk_id"],
                source_title=row["source_title"],
                content=row["content"],
                metadata=row["metadata"] or {},
                tags=row["tags"] or [],
                confidence=row["confidence"],
                status=row["status"],
                score=float(row["score"]),
            )
            for row in rows
        ]

    def search_knowledge_text(
        self,
        query_text: str,
        *,
        top_k: int,
        query_terms: list[str] | None = None,
        status: str = "usable",
    ) -> list[RetrievedKnowledgeChunk]:
        """从统一知识单元表做关键词召回，关键约束是只返回正式可检索内容。"""
        normalized = str(query_text or "").strip()
        if not normalized:
            return []
        terms = _clean_list(query_terms) or [normalized]
        params = {
            "query_like": f"%{normalized}%",
            "query_terms": terms,
            "status": status,
            "top_k": top_k,
        }
        with self.connect() as conn:
            rows = conn.execute(self._search_knowledge_text_sql(), params).fetchall()
        return [
            RetrievedKnowledgeChunk(
                id=row["id"],
                source_type=row["source_type"],
                source_id=row["source_id"],
                source_chunk_id=row["source_chunk_id"],
                source_title=row["source_title"],
                content=row["content"],
                metadata=row["metadata"] or {},
                tags=row["tags"] or [],
                confidence=row["confidence"],
                status=row["status"],
                score=float(row["score"]),
            )
            for row in rows
        ]

    @staticmethod
    def _search_knowledge_sql() -> str:
        """集中维护统一知识单元向量检索 SQL，后续混合检索会复用同一候选表。"""
        return """
        SELECT
            id, source_type, source_id, source_chunk_id, source_title, content,
            metadata, tags, confidence, status,
            1 - (embedding <=> %(embedding)s::vector) AS score
        FROM knowledge_chunks
        WHERE status = %(status)s
          AND embedding_status = 'ready'
          AND embedding IS NOT NULL
          AND (embedding <=> %(embedding)s::vector) <= %(max_distance)s
        ORDER BY embedding <=> %(embedding)s::vector
        LIMIT %(top_k)s
        """

    @staticmethod
    def _search_knowledge_text_sql() -> str:
        """集中维护统一知识单元关键词检索 SQL，作为混合召回的第二路候选。"""
        return """
        SELECT
            id, source_type, source_id, source_chunk_id, source_title, content,
            metadata, tags, confidence, status,
            (
                CASE WHEN source_title ILIKE %(query_like)s THEN 0.45 ELSE 0 END
                + CASE WHEN search_text ILIKE %(query_like)s THEN 0.35 ELSE 0 END
                + CASE WHEN content ILIKE %(query_like)s THEN 0.20 ELSE 0 END
                + COALESCE((
                    SELECT sum(
                        CASE WHEN source_title ILIKE ('%%' || term || '%%') THEN 0.18 ELSE 0 END
                        + CASE WHEN search_text ILIKE ('%%' || term || '%%') THEN 0.12 ELSE 0 END
                        + CASE WHEN content ILIKE ('%%' || term || '%%') THEN 0.06 ELSE 0 END
                    )
                    FROM unnest(%(query_terms)s::text[]) AS term
                ), 0)
            ) AS score
        FROM knowledge_chunks
        WHERE status = %(status)s
          AND (
              source_title ILIKE %(query_like)s
              OR content ILIKE %(query_like)s
              OR search_text ILIKE %(query_like)s
              OR EXISTS (
                  SELECT 1
                  FROM unnest(%(query_terms)s::text[]) AS term
                  WHERE source_title ILIKE ('%%' || term || '%%')
                     OR content ILIKE ('%%' || term || '%%')
                     OR search_text ILIKE ('%%' || term || '%%')
              )
          )
        ORDER BY score DESC, updated_at DESC, id ASC
        LIMIT %(top_k)s
        """
