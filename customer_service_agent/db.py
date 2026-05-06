from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import psycopg
from psycopg.rows import dict_row


def format_vector(values: Iterable[float]) -> str:
    return "[" + ",".join(str(float(value)) for value in values) + "]"


def score_to_distance(score: float) -> float:
    return 1.0 - score


def _clean_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return [str(item).strip() for item in value if str(item).strip()]


def build_embedding_text(row: dict[str, Any]) -> str:
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


def compute_content_hash(row: dict[str, Any]) -> str:
    payload = {
        "question": str(row.get("question", "")).strip(),
        "answer": str(row.get("answer", "")).strip(),
        "question_variants": _clean_list(row.get("question_variants")),
        "category": str(row.get("category", "") or "").strip(),
        "tags": _clean_list(row.get("tags")),
        "status": str(row.get("status", "") or "").strip(),
        "confidence": str(row.get("confidence", "") or "").strip(),
        "sensitivity": str(row.get("sensitivity", "") or "").strip(),
    }
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
        embedding_status = next_embedding_status(
            existing["embedding_status"] if existing else None,
            existing["content_hash"] if existing else None,
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
