from __future__ import annotations

import json
from typing import Any

from customer_service_agent.db.builders import (
    clean_dict,
    clean_int,
    clean_list,
    compute_knowledge_chunk_hash,
    join_search_text,
)
from customer_service_agent.db.models import (
    RetrievedDocument,
    RetrievedKnowledgeChunk,
    format_vector,
    score_to_distance,
)


class KnowledgeMixin:
    """统一知识单元写入 + 向量/关键词检索 + 父块上下文回填。"""

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
            "parent_chunk_id": row.get("parent_chunk_id"),
            "chunk_level": row.get("chunk_level", "chunk"),
            "source_title": row.get("source_title"),
            "chunk_index": int(row.get("chunk_index", 0)),
            "section_path": json.dumps(clean_list(row.get("section_path")), ensure_ascii=False),
            "page_start": clean_int(row.get("page_start")),
            "page_end": clean_int(row.get("page_end")),
            "block_type": row.get("block_type"),
            "source_offsets": json.dumps(clean_dict(row.get("source_offsets")), ensure_ascii=False),
            "content": row["content"],
            "embedding_text": embedding_text,
            "search_text": row.get("search_text") or join_search_text(
                [row.get("source_title"), row.get("tags", []), row["content"]]
            ),
            "metadata": json.dumps(row.get("metadata", {}), ensure_ascii=False),
            "tags": json.dumps(clean_list(row.get("tags")), ensure_ascii=False),
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
        return [self._row_to_retrieved_chunk(row) for row in rows]

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
        terms = clean_list(query_terms) or [normalized]
        params = {
            "query_like": f"%{normalized}%",
            "query_terms": terms,
            "status": status,
            "top_k": top_k,
        }
        with self.connect() as conn:
            rows = conn.execute(self._search_knowledge_text_sql(), params).fetchall()
        return [self._row_to_retrieved_chunk(row) for row in rows]

    def get_parent_context_chunks(
        self,
        child_ids: list[str],
        *,
        status: str = "usable",
    ) -> list[RetrievedKnowledgeChunk]:
        """按 child 命中回填 parent 上下文，关键约束是只读取同来源可用父块。"""
        unique_ids = list(dict.fromkeys(str(item).strip() for item in child_ids if str(item).strip()))
        if not unique_ids:
            return []
        with self.connect() as conn:
            rows = conn.execute(
                self._get_parent_context_chunks_sql(),
                {"child_ids": unique_ids, "status": status},
            ).fetchall()
        return [self._row_to_retrieved_chunk(row) for row in rows]

    @staticmethod
    def _row_to_retrieved_chunk(row: dict[str, Any]) -> RetrievedKnowledgeChunk:
        return RetrievedKnowledgeChunk(
            id=row["id"],
            source_type=row["source_type"],
            source_id=row["source_id"],
            source_chunk_id=row["source_chunk_id"],
            parent_chunk_id=row["parent_chunk_id"],
            chunk_level=row["chunk_level"],
            source_title=row["source_title"],
            section_path=row["section_path"] or [],
            page_start=row["page_start"],
            page_end=row["page_end"],
            block_type=row["block_type"],
            source_offsets=row["source_offsets"] or {},
            content=row["content"],
            metadata=row["metadata"] or {},
            tags=row["tags"] or [],
            confidence=row["confidence"],
            status=row["status"],
            score=float(row["score"]),
        )

    @staticmethod
    def _insert_knowledge_chunk_sql() -> str:
        """集中维护统一知识单元 upsert SQL，避免多来源写入字段漂移。"""
        return """
        INSERT INTO knowledge_chunks (
            id, source_type, source_id, source_chunk_id, parent_chunk_id,
            chunk_level, source_title, chunk_index, section_path, page_start,
            page_end, block_type, source_offsets,
            content, embedding_text, search_text, metadata, tags, confidence, status,
            embedding, embedding_status, embedding_model, embedding_dimensions,
            embedding_updated_at, embedding_error, content_hash
        )
        VALUES (
            %(id)s, %(source_type)s, %(source_id)s, %(source_chunk_id)s,
            %(parent_chunk_id)s, %(chunk_level)s, %(source_title)s,
            %(chunk_index)s, %(section_path)s::jsonb, %(page_start)s,
            %(page_end)s, %(block_type)s, %(source_offsets)s::jsonb,
            %(content)s, %(embedding_text)s, %(search_text)s,
            %(metadata)s::jsonb, %(tags)s::jsonb, %(confidence)s, %(status)s,
            %(embedding)s::vector, %(embedding_status)s, %(embedding_model)s,
            %(embedding_dimensions)s,
            CASE WHEN %(embedding)s IS NULL THEN NULL ELSE now() END,
            %(embedding_error)s, %(content_hash)s
        )
        ON CONFLICT (source_type, source_id, chunk_index) DO UPDATE SET
            id = EXCLUDED.id,
            source_chunk_id = EXCLUDED.source_chunk_id,
            parent_chunk_id = EXCLUDED.parent_chunk_id,
            chunk_level = EXCLUDED.chunk_level,
            source_title = EXCLUDED.source_title,
            content = EXCLUDED.content,
            section_path = EXCLUDED.section_path,
            page_start = EXCLUDED.page_start,
            page_end = EXCLUDED.page_end,
            block_type = EXCLUDED.block_type,
            source_offsets = EXCLUDED.source_offsets,
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
    def _search_knowledge_sql() -> str:
        """集中维护统一知识单元向量检索 SQL，后续混合检索会复用同一候选表。

        LEFT JOIN import_files / import_chunks 是为了让"文档级 / 切片级禁用"立即在检索层生效，
        不需要重新生成 embedding；FAQ 来源再 LEFT JOIN faq_documents 读**实时** status——禁用/待复核（status≠usable）即时排除，改状态无需重嵌（kc.status 是投影快照，故以 fq.status 为准）。
        """
        return """
        SELECT
            kc.id, kc.source_type, kc.source_id, kc.source_chunk_id, kc.parent_chunk_id,
            kc.chunk_level, kc.source_title, kc.section_path, kc.page_start, kc.page_end,
            kc.block_type, kc.source_offsets, kc.content,
            kc.metadata, kc.tags, kc.confidence, kc.status,
            1 - (kc.embedding <=> %(embedding)s::vector) AS score
        FROM knowledge_chunks kc
        LEFT JOIN import_files imp
            ON kc.source_type = 'document' AND imp.id = kc.source_id
        LEFT JOIN import_chunks ic
            ON kc.source_type = 'document' AND ic.id = kc.source_chunk_id
        LEFT JOIN faq_documents fq
            ON kc.source_type = 'faq' AND fq.id = kc.source_id
        WHERE COALESCE(fq.status, kc.status) = %(status)s
          AND kc.embedding_status = 'ready'
          AND kc.embedding IS NOT NULL
          AND (kc.embedding <=> %(embedding)s::vector) <= %(max_distance)s
          AND COALESCE(imp.is_disabled, false) = false
          AND COALESCE(ic.is_disabled, false) = false
          AND (kc.source_type <> 'document' OR kc.chunk_level <> 'parent')
        ORDER BY kc.embedding <=> %(embedding)s::vector
        LIMIT %(top_k)s
        """

    @staticmethod
    def _search_knowledge_text_sql() -> str:
        """集中维护统一知识单元关键词检索 SQL，作为混合召回的第二路候选。

        与向量检索一致；FAQ 走 fq.status 实时口径（COALESCE(fq.status, kc.status)），文档/切片仍按 is_disabled 过滤。
        """
        return """
        SELECT
            kc.id, kc.source_type, kc.source_id, kc.source_chunk_id, kc.parent_chunk_id,
            kc.chunk_level, kc.source_title, kc.section_path, kc.page_start, kc.page_end,
            kc.block_type, kc.source_offsets, kc.content,
            kc.metadata, kc.tags, kc.confidence, kc.status,
            (
                CASE WHEN kc.source_title ILIKE %(query_like)s THEN 0.45 ELSE 0 END
                + CASE WHEN kc.search_text ILIKE %(query_like)s THEN 0.35 ELSE 0 END
                + CASE WHEN kc.content ILIKE %(query_like)s THEN 0.20 ELSE 0 END
                + COALESCE((
                    SELECT sum(
                        CASE WHEN kc.source_title ILIKE ('%%' || term || '%%') THEN 0.18 ELSE 0 END
                        + CASE WHEN kc.search_text ILIKE ('%%' || term || '%%') THEN 0.12 ELSE 0 END
                        + CASE WHEN kc.content ILIKE ('%%' || term || '%%') THEN 0.06 ELSE 0 END
                    )
                    FROM unnest(%(query_terms)s::text[]) AS term
                ), 0)
            ) AS score
        FROM knowledge_chunks kc
        LEFT JOIN import_files imp
            ON kc.source_type = 'document' AND imp.id = kc.source_id
        LEFT JOIN import_chunks ic
            ON kc.source_type = 'document' AND ic.id = kc.source_chunk_id
        LEFT JOIN faq_documents fq
            ON kc.source_type = 'faq' AND fq.id = kc.source_id
        WHERE COALESCE(fq.status, kc.status) = %(status)s
          AND COALESCE(imp.is_disabled, false) = false
          AND COALESCE(ic.is_disabled, false) = false
          AND (kc.source_type <> 'document' OR kc.chunk_level <> 'parent')
          AND (
              kc.source_title ILIKE %(query_like)s
              OR kc.content ILIKE %(query_like)s
              OR kc.search_text ILIKE %(query_like)s
              OR EXISTS (
                  SELECT 1
                  FROM unnest(%(query_terms)s::text[]) AS term
                  WHERE kc.source_title ILIKE ('%%' || term || '%%')
                     OR kc.content ILIKE ('%%' || term || '%%')
                     OR kc.search_text ILIKE ('%%' || term || '%%')
              )
          )
        ORDER BY score DESC, kc.updated_at DESC, kc.id ASC
        LIMIT %(top_k)s
        """

    @staticmethod
    def _get_parent_context_chunks_sql() -> str:
        """集中维护 child 命中后的 parent 上下文回填 SQL。"""
        return """
        SELECT DISTINCT
            parent.id,
            parent.source_type,
            parent.source_id,
            parent.source_chunk_id,
            parent.parent_chunk_id,
            parent.chunk_level,
            parent.source_title,
            parent.section_path,
            parent.page_start,
            parent.page_end,
            parent.block_type,
            parent.source_offsets,
            parent.content,
            parent.metadata,
            parent.tags,
            parent.confidence,
            parent.status,
            1.0::double precision AS score
        FROM knowledge_chunks child
        JOIN knowledge_chunks parent
          ON parent.id = child.parent_chunk_id
         AND parent.source_type = child.source_type
         AND parent.source_id = child.source_id
        LEFT JOIN import_files imp
            ON parent.source_type = 'document' AND imp.id = parent.source_id
        LEFT JOIN import_chunks ic
            ON parent.source_type = 'document' AND ic.id = parent.source_chunk_id
        WHERE child.id = ANY(%(child_ids)s::text[])
          AND parent.chunk_level = 'parent'
          AND parent.status = %(status)s
          AND parent.embedding_status = 'ready'
          AND COALESCE(imp.is_disabled, false) = false
          AND COALESCE(ic.is_disabled, false) = false
        ORDER BY parent.source_type, parent.source_id, parent.source_chunk_id, parent.id
        """
