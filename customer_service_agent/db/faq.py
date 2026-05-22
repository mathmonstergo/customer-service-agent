from __future__ import annotations

import json
from typing import Any

from customer_service_agent.db.builders import (
    build_embedding_text,
    clean_list,
    compute_content_hash,
    next_embedding_status,
)
from customer_service_agent.db.models import format_vector


class FaqMixin:
    """FAQ 文档表读写：upsert / get / save_text / update_embedding / list / 状态批改。"""

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
            "question_variants": json.dumps(clean_list(row.get("question_variants")), ensure_ascii=False),
            "answer": row["answer"],
            "tags": json.dumps(clean_list(row.get("tags")), ensure_ascii=False),
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

    @staticmethod
    def _sync_ready_faq_knowledge_chunks_sql() -> str:
        """集中维护已有 FAQ 投影 SQL，关键约束是不重新生成向量。"""
        return """
        WITH upserted AS (
            INSERT INTO knowledge_chunks (
                id, source_type, source_id, source_chunk_id, parent_chunk_id,
                chunk_level, source_title, chunk_index, section_path, page_start,
                page_end, block_type, source_offsets,
                content, embedding_text, search_text, metadata, tags, confidence, status,
                embedding, embedding_status, embedding_model, embedding_dimensions,
                embedding_updated_at, embedding_error, content_hash
            )
            SELECT
                'kc_faq_' || id,
                'faq',
                id,
                NULL,
                NULL,
                'chunk',
                question,
                0,
                '[]'::jsonb,
                NULL,
                NULL,
                'faq',
                '{}'::jsonb,
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
                parent_chunk_id = EXCLUDED.parent_chunk_id,
                chunk_level = EXCLUDED.chunk_level,
                section_path = EXCLUDED.section_path,
                page_start = EXCLUDED.page_start,
                page_end = EXCLUDED.page_end,
                block_type = EXCLUDED.block_type,
                source_offsets = EXCLUDED.source_offsets,
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
