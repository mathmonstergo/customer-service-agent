from __future__ import annotations

import json
import uuid
from typing import Any

from customer_service_agent.db.builders import (
    clean_block_list,
    clean_dict,
    clean_int,
    clean_list,
    compute_knowledge_chunk_hash,
    count_job_item_statuses,
    empty_import_file_embedding_summary,
)


class ImportMixin:
    """import_files / import_chunks / import_candidates / import_generation_jobs CRUD。"""

    def create_import_file(self, row: dict[str, Any]) -> dict[str, Any]:
        """创建导入文件记录，保存原件路径和格式识别结果。"""
        sql = """
        INSERT INTO import_files (
            id, original_name, stored_path, file_type, parser, chunker_type, status,
            message_count, chunk_count, candidate_count, error
        )
        VALUES (
            %(id)s, %(original_name)s, %(stored_path)s, %(file_type)s, %(parser)s,
            %(chunker_type)s,
            %(status)s, %(message_count)s, %(chunk_count)s, %(candidate_count)s, %(error)s
        )
        RETURNING *
        """
        payload = {
            "chunker_type": "naive",
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
            "chunker_type",
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
        """删除导入文件记录，依赖外键级联清理切块和候选 FAQ。

        knowledge_chunks 不在外键级联范围内（统一知识表），需手工清除文档来源的向量行，
        避免文件删除后残留 stale embedding 继续被检索命中。

        返回值带 `_deleted_chunk_count` / `_deleted_vector_count`，反映实际触发的 DB 事件量；
        前端据此条件性提示（没切片就不提示切片清理，没向量就不提示向量清理），避免假动作提示。
        """
        count_chunks_sql = (
            "SELECT count(*) AS c FROM import_chunks WHERE file_id = %(id)s"
        )
        delete_knowledge_sql = (
            "DELETE FROM knowledge_chunks "
            "WHERE source_type = 'document' AND source_id = %(id)s "
            "RETURNING id"
        )
        delete_file_sql = "DELETE FROM import_files WHERE id = %(id)s RETURNING *"
        with self.connect() as conn:
            chunk_count = int(
                conn.execute(count_chunks_sql, {"id": file_id}).fetchone()["c"]
            )
            deleted_vectors = conn.execute(
                delete_knowledge_sql, {"id": file_id}
            ).fetchall()
            record = conn.execute(delete_file_sql, {"id": file_id}).fetchone()
        if record is None:
            return None
        record["_deleted_chunk_count"] = chunk_count
        record["_deleted_vector_count"] = len(deleted_vectors)
        return record

    def set_import_file_disabled(
        self, file_id: str, is_disabled: bool
    ) -> dict[str, Any] | None:
        """切换文件级禁用标记；禁用后该文件下所有切片不再被 RAG 检索召回。"""
        sql = """
        UPDATE import_files
        SET is_disabled = %(is_disabled)s,
            updated_at = now()
        WHERE id = %(id)s
        RETURNING *
        """
        with self.connect() as conn:
            return conn.execute(
                sql, {"id": file_id, "is_disabled": bool(is_disabled)}
            ).fetchone()

    def set_import_chunk_disabled(
        self, chunk_id: str, is_disabled: bool
    ) -> dict[str, Any] | None:
        """切换切片级禁用标记；禁用后该切片不再被 RAG 检索召回（即使所属文件启用）。"""
        sql = """
        UPDATE import_chunks
        SET is_disabled = %(is_disabled)s,
            updated_at = now()
        WHERE id = %(id)s
        RETURNING *
        """
        with self.connect() as conn:
            return conn.execute(
                sql, {"id": chunk_id, "is_disabled": bool(is_disabled)}
            ).fetchone()

    def set_import_chunk_questions(
        self,
        chunk_id: str,
        questions: list[str],
        *,
        model: str | None,
        status: str = "ready",
        error: str | None = None,
    ) -> dict[str, Any] | None:
        """落库假设性问题与生成状态；status 取 pending|ready|failed|skipped。"""
        sql = """
        UPDATE import_chunks
        SET questions = %(questions)s::jsonb,
            questions_status = %(status)s,
            questions_model = %(model)s,
            questions_updated_at = now(),
            questions_error = %(error)s,
            updated_at = now()
        WHERE id = %(id)s
        RETURNING *
        """
        with self.connect() as conn:
            return conn.execute(
                sql,
                {
                    "id": chunk_id,
                    "questions": json.dumps(list(questions or []), ensure_ascii=False),
                    "status": status,
                    "model": model,
                    "error": error,
                },
            ).fetchone()

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
        """替换某个文件的切块，关键约束是同步清理旧知识单元，避免旧向量继续被问答页召回。"""
        with self.connect() as conn:
            conn.execute(
                """
                DELETE FROM knowledge_chunks
                WHERE source_type = 'document'
                  AND source_id = %(file_id)s
                """,
                {"file_id": file_id},
            )
            conn.execute("DELETE FROM import_chunks WHERE file_id = %(file_id)s", {"file_id": file_id})
            rows = []
            for chunk in chunks:
                rows.append(conn.execute(self._insert_import_chunk_sql(), self._import_chunk_payload(chunk)).fetchone())
        return rows

    def list_import_chunks(self, file_id: str) -> list[dict[str, Any]]:
        """按文件列出切片，并联表 knowledge_chunks 派生每片真实 embedding_status。

        import_chunks 本身不存 embedding 状态（向量只落在统一知识表 knowledge_chunks），
        因此切片级状态要按"该片的 parent + child 知识单元"聚合得到，规则与文件级摘要保持一致：
        无向量=未索引(pending)、任一 stale=过期、全失败=失败、全就绪=已索引、其余=部分(partial)。
        """
        with self.connect() as conn:
            return conn.execute(self._list_import_chunks_sql(), {"file_id": file_id}).fetchall()

    @staticmethod
    def _list_import_chunks_sql() -> str:
        """集中维护切片列表 SQL；LEFT JOIN 知识表派生切片级 embedding_status。

        关联口径沿用 stale/删除 SQL：parent 的 source_chunk_id=切片 id，
        child 的 parent_chunk_id='kc_document_'||切片 id，用 OR 一次覆盖该片全部知识单元。
        """
        return """
        WITH chunk_knowledge AS (
            SELECT
                ic.id AS chunk_id,
                count(kc.id) AS knowledge_count,
                count(kc.id) FILTER (WHERE kc.embedding_status = 'ready') AS ready_count,
                count(kc.id) FILTER (WHERE kc.embedding_status = 'stale') AS stale_count,
                count(kc.id) FILTER (WHERE kc.embedding_status = 'failed') AS failed_count
            FROM import_chunks ic
            LEFT JOIN knowledge_chunks kc
              ON kc.source_type = 'document'
             AND (
                    kc.source_chunk_id = ic.id
                    OR kc.parent_chunk_id = ('kc_document_' || ic.id)
                 )
            WHERE ic.file_id = %(file_id)s
            GROUP BY ic.id
        )
        SELECT
            ic.*,
            CASE
                WHEN COALESCE(ck.knowledge_count, 0) = 0 THEN 'pending'
                WHEN ck.stale_count > 0 THEN 'stale'
                WHEN ck.failed_count > 0 AND ck.ready_count = 0 THEN 'failed'
                WHEN ck.ready_count >= ck.knowledge_count THEN 'ready'
                WHEN ck.ready_count = 0 THEN 'pending'
                ELSE 'partial'
            END AS embedding_status
        FROM import_chunks ic
        LEFT JOIN chunk_knowledge ck ON ck.chunk_id = ic.id
        WHERE ic.file_id = %(file_id)s
        ORDER BY ic.chunk_index ASC
        """

    def get_import_chunk(self, chunk_id: str) -> dict[str, Any] | None:
        """按 id 获取导入切块。"""
        sql = "SELECT * FROM import_chunks WHERE id = %(id)s"
        with self.connect() as conn:
            return conn.execute(sql, {"id": chunk_id}).fetchone()

    @staticmethod
    def _import_chunk_payload(chunk: dict[str, Any]) -> dict[str, Any]:
        """补齐导入切片结构化字段默认值，兼容 Markdown 和 MinerU 两类来源。"""
        return {
            **chunk,
            "section_path": json.dumps(clean_list(chunk.get("section_path")), ensure_ascii=False),
            "page_start": clean_int(chunk.get("page_start")),
            "page_end": clean_int(chunk.get("page_end")),
            "block_type": chunk.get("block_type"),
            "source_offsets": json.dumps(clean_dict(chunk.get("source_offsets")), ensure_ascii=False),
            "source_blocks": json.dumps(clean_block_list(chunk.get("source_blocks")), ensure_ascii=False),
            "children_delimiter": str(chunk.get("children_delimiter") or ""),
        }

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
            conn.execute(self._delete_document_chunk_child_knowledge_sql(), payload)
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
            counts = count_job_item_statuses(items)
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
            "similar_questions": json.dumps(clean_list(row.get("similar_questions")), ensure_ascii=False),
            "category": row.get("category"),
            "tags": json.dumps(clean_list(row.get("tags")), ensure_ascii=False),
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
            id, file_id, chunk_index,
            section_path, page_start, page_end, block_type, source_offsets, source_blocks,
            children_delimiter,
            start_at, end_at, message_count,
            keywords, source_text, status, candidate_count
        )
        VALUES (
            %(id)s, %(file_id)s, %(chunk_index)s,
            %(section_path)s::jsonb, %(page_start)s,
            %(page_end)s, %(block_type)s, %(source_offsets)s::jsonb, %(source_blocks)s::jsonb,
            %(children_delimiter)s,
            %(start_at)s, %(end_at)s,
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
            SELECT
                file_id,
                COALESCE(
                    sum(
                        CASE
                            WHEN jsonb_array_length(source_blocks) > 1 THEN
                                1 + (
                                    SELECT count(*)
                                    FROM jsonb_array_elements(source_blocks) AS source_block(block_value)
                                    WHERE btrim(COALESCE(source_block.block_value->>'text', '')) <> ''
                                )
                            ELSE 1
                        END
                    ),
                    0
                )::int AS expected_knowledge_count
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
        ),
        combined_counts AS (
            SELECT
                requested.file_id,
                GREATEST(
                    COALESCE(chunk_counts.expected_knowledge_count, 0),
                    COALESCE(knowledge_counts.knowledge_count, 0)
                )::int AS total_chunks,
                COALESCE(knowledge_counts.knowledge_count, 0)::int AS knowledge_count,
                COALESCE(knowledge_counts.ready_count, 0)::int AS ready_count,
                COALESCE(knowledge_counts.stale_count, 0)::int AS stale_count,
                COALESCE(knowledge_counts.failed_count, 0)::int AS failed_count,
                COALESCE(knowledge_counts.pending_count, 0)::int AS pending_count
            FROM requested
            LEFT JOIN chunk_counts ON chunk_counts.file_id = requested.file_id
            LEFT JOIN knowledge_counts ON knowledge_counts.file_id = requested.file_id
        )
        SELECT
            combined_counts.file_id,
            combined_counts.total_chunks,
            combined_counts.knowledge_count,
            combined_counts.ready_count,
            combined_counts.stale_count,
            combined_counts.failed_count,
            (
                combined_counts.pending_count
                + GREATEST(
                    combined_counts.total_chunks - combined_counts.knowledge_count,
                    0
                )
            )::int AS pending_count,
            GREATEST(
                combined_counts.total_chunks - combined_counts.knowledge_count,
                0
            )::int AS missing_count,
            CASE
                WHEN combined_counts.total_chunks = 0 THEN 'none'
                WHEN combined_counts.stale_count > 0 THEN 'stale'
                WHEN combined_counts.failed_count > 0
                    AND combined_counts.ready_count = 0 THEN 'failed'
                WHEN combined_counts.ready_count >= combined_counts.total_chunks THEN 'ready'
                WHEN combined_counts.ready_count = 0 THEN 'pending'
                ELSE 'partial'
            END AS status
        FROM combined_counts
        """

    @staticmethod
    def _update_import_chunk_text_sql() -> str:
        """集中维护切片正文更新 SQL，手工编辑后清空旧解析块避免 child 过期。"""
        return """
        UPDATE import_chunks
        SET source_text = %(source_text)s,
            source_blocks = '[]'::jsonb,
            updated_at = now()
        WHERE id = %(id)s
        RETURNING *
        """

    @staticmethod
    def _mark_document_chunk_knowledge_stale_sql() -> str:
        """集中维护文档 parent 知识单元过期标记 SQL，避免旧向量继续命中。"""
        return """
        UPDATE knowledge_chunks
        SET content = %(source_text)s,
            embedding_text = %(source_text)s,
            search_text = concat_ws(E'\n', source_title, tags::text, %(source_text)s::text),
            embedding_status = 'stale',
            embedding_error = NULL,
            content_hash = %(content_hash)s,
            updated_at = now()
        WHERE source_type = 'document'
          AND source_chunk_id = %(chunk_id)s
        """

    @staticmethod
    def _delete_document_chunk_child_knowledge_sql() -> str:
        """集中维护手工编辑后旧 child 知识单元清理 SQL，避免 stale child 残留。"""
        return """
        DELETE FROM knowledge_chunks
        WHERE source_type = 'document'
          AND parent_chunk_id = ('kc_document_' || %(chunk_id)s)
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
