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
        allowed = {"status", "message_count", "chunk_count", "candidate_count", "error"}
        updates = {key: value for key, value in fields.items() if key in allowed}
        if not updates:
            return self.get_import_file(file_id)
        assignments = ", ".join(f"{key} = %({key})s" for key in updates)
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
        return {
            "items": rows,
            "total": total,
            "status_counts": {row["status"]: row["count"] for row in status_counts},
        }

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
