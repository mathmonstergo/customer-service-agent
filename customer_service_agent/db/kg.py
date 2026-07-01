from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from customer_service_agent.kg import (
    build_kg_entity_knowledge_chunk_row,
    build_kg_relation_knowledge_chunk_row,
)


class KnowledgeGraphMixin:
    """知识图谱候选审核、投影和局部子图查询。"""

    def create_kg_extraction_job(self, row: dict[str, Any]) -> dict[str, Any]:
        """创建 KG 抽取任务，关键约束是先记录 queued 状态再调用模型。"""
        payload = {
            "id": row.get("id") or self._new_kg_job_id(),
            "source_type": row["source_type"],
            "source_id": row["source_id"],
            "source_chunk_id": row.get("source_chunk_id"),
            "status": row.get("status", "queued"),
            "entity_count": int(row.get("entity_count", 0) or 0),
            "relation_count": int(row.get("relation_count", 0) or 0),
            "evidence_count": int(row.get("evidence_count", 0) or 0),
            "model": row.get("model"),
            "error": row.get("error"),
        }
        with self.connect() as conn:
            return conn.execute(self._insert_kg_extraction_job_sql(), payload).fetchone()

    def update_kg_extraction_job(self, job_id: str, **fields: Any) -> dict[str, Any]:
        """更新 KG 抽取任务状态，关键约束是只允许受控状态和计数字段。"""
        allowed = {"status", "entity_count", "relation_count", "evidence_count", "error", "model"}
        updates = {key: value for key, value in fields.items() if key in allowed}
        if not updates:
            raise ValueError("kg extraction job updates are required")
        with self.connect() as conn:
            row = conn.execute(
                self._update_kg_extraction_job_sql(set(updates)),
                {"id": job_id, **updates},
            ).fetchone()
        if row is None:
            raise KeyError(f"KG extraction job not found: {job_id}")
        return row

    def save_kg_extraction_candidates(self, extraction: dict[str, Any]) -> dict[str, int]:
        """保存 KG 抽取候选，关键约束是只进审核表，不写入可检索投影。"""
        entity_count = 0
        relation_count = 0
        evidence_count = 0
        with self.connect() as conn:
            for entity in extraction.get("entities", []):
                conn.execute(self._upsert_kg_entity_sql(), self._kg_entity_params(entity))
                entity_count += 1
                for evidence in entity.get("evidence", []):
                    conn.execute(
                        self._insert_kg_evidence_sql(),
                        self._kg_evidence_params(evidence, entity_id=entity["id"]),
                    )
                    evidence_count += 1
            for relation in extraction.get("relations", []):
                conn.execute(self._upsert_kg_relation_sql(), self._kg_relation_params(relation))
                relation_count += 1
                for evidence in relation.get("evidence", []):
                    conn.execute(
                        self._insert_kg_evidence_sql(),
                        self._kg_evidence_params(evidence, relation_id=relation["id"]),
                    )
                    evidence_count += 1
        return {
            "entity_count": entity_count,
            "relation_count": relation_count,
            "evidence_count": evidence_count,
        }

    def list_kg_entities(
        self,
        *,
        status: str | None = None,
        entity_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """列出 KG 实体候选，关键约束是返回证据摘要供人工审核。"""
        clauses = []
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if status:
            clauses.append("ent.status = %(status)s")
            params["status"] = status
        if entity_type:
            clauses.append("ent.entity_type = %(entity_type)s")
            params["entity_type"] = entity_type
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        with self.connect() as conn:
            rows = conn.execute(self._list_kg_entities_sql(where=where), params).fetchall()
            total = conn.execute(self._count_kg_entities_sql(where=where), params).fetchone()["total"]
        return {"items": rows, "total": total}

    def list_kg_relations(
        self,
        *,
        status: str | None = None,
        relation_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """列出 KG 关系候选，关键约束是返回头尾实体和证据摘要供人工审核。"""
        clauses = []
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if status:
            clauses.append("rel.status = %(status)s")
            params["status"] = status
        if relation_type:
            clauses.append("rel.relation_type = %(relation_type)s")
            params["relation_type"] = relation_type
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        with self.connect() as conn:
            rows = conn.execute(self._list_kg_relations_sql(where=where), params).fetchall()
            total = conn.execute(self._count_kg_relations_sql(where=where), params).fetchone()["total"]
        return {"items": rows, "total": total}

    def confirm_kg_entity(self, entity_id: str) -> dict[str, Any]:
        """确认 KG 实体并投影为 knowledge_chunks，关键约束是同一事务内完成状态和投影。"""
        with self.connect() as conn:
            entity = conn.execute(self._confirm_kg_entity_sql(), {"id": entity_id}).fetchone()
            if entity is None:
                raise KeyError(f"KG entity not found: {entity_id}")
            evidence = conn.execute(
                self._list_kg_entity_evidence_sql(), {"entity_id": entity_id}
            ).fetchall()
            chunk = build_kg_entity_knowledge_chunk_row(entity, [dict(item) for item in evidence])
            conn.execute(self._insert_knowledge_chunk_sql(), self._knowledge_chunk_payload(chunk))
            return entity

    def confirm_kg_relation(self, relation_id: str) -> dict[str, Any]:
        """确认 KG 关系并投影为 knowledge_chunks，关键约束是保留头尾实体稳定 ID。"""
        with self.connect() as conn:
            row = conn.execute(self._confirm_kg_relation_sql(), {"id": relation_id}).fetchone()
            if row is None:
                raise KeyError(f"KG relation not found: {relation_id}")
            evidence = conn.execute(
                self._list_kg_relation_evidence_sql(), {"relation_id": relation_id}
            ).fetchall()
            relation = {
                "id": row["id"],
                "head_entity_id": row["head_entity_id"],
                "relation_type": row["relation_type"],
                "tail_entity_id": row["tail_entity_id"],
                "description": row.get("description"),
                "confidence": row.get("confidence"),
                "status": row.get("status"),
            }
            head = {
                "id": row["head_entity_id"],
                "name": row["head_entity_name"],
                "entity_type": row["head_entity_type"],
            }
            tail = {
                "id": row["tail_entity_id"],
                "name": row["tail_entity_name"],
                "entity_type": row["tail_entity_type"],
            }
            chunk = build_kg_relation_knowledge_chunk_row(
                relation, head, tail, [dict(item) for item in evidence]
            )
            conn.execute(self._insert_knowledge_chunk_sql(), self._knowledge_chunk_payload(chunk))
            return row

    def set_kg_entity_status(self, entity_id: str, status: str) -> dict[str, Any]:
        """更新 KG 实体审核状态，关键约束是同步 kg_entity 投影状态。"""
        params = {"id": entity_id, "status": status}
        proj_params = {**params, "source_type": "kg_entity"}
        with self.connect() as conn:
            row = conn.execute(self._set_kg_entity_status_sql(), params).fetchone()
            if row is None:
                raise KeyError(f"KG entity not found: {entity_id}")
            projection_exists = conn.execute(
                self._kg_projection_exists_sql(), proj_params
            ).fetchone()["exists"]
            if status == "usable" and not projection_exists:
                evidence = conn.execute(
                    self._list_kg_entity_evidence_sql(), {"entity_id": entity_id}
                ).fetchall()
                chunk = build_kg_entity_knowledge_chunk_row(
                    row, [dict(item) for item in evidence]
                )
                conn.execute(
                    self._insert_knowledge_chunk_sql(),
                    self._knowledge_chunk_payload(chunk),
                )
            else:
                conn.execute(self._set_kg_projection_status_sql(), proj_params)
        return row

    def set_kg_relation_status(self, relation_id: str, status: str) -> dict[str, Any]:
        """更新 KG 关系审核状态，关键约束是同步 kg_relation 投影状态。"""
        params = {"id": relation_id, "status": status}
        proj_params = {**params, "source_type": "kg_relation"}
        with self.connect() as conn:
            row = conn.execute(self._set_kg_relation_status_sql(), params).fetchone()
            if row is None:
                raise KeyError(f"KG relation not found: {relation_id}")
            projection_exists = conn.execute(
                self._kg_projection_exists_sql(), proj_params
            ).fetchone()["exists"]
            if status == "usable" and not projection_exists:
                evidence = conn.execute(
                    self._list_kg_relation_evidence_sql(), {"relation_id": relation_id}
                ).fetchall()
                relation = {
                    "id": row["id"],
                    "head_entity_id": row["head_entity_id"],
                    "relation_type": row["relation_type"],
                    "tail_entity_id": row["tail_entity_id"],
                    "description": row.get("description"),
                    "confidence": row.get("confidence"),
                    "status": row.get("status"),
                }
                head = {
                    "id": row["head_entity_id"],
                    "name": row["head_entity_name"],
                    "entity_type": row["head_entity_type"],
                }
                tail = {
                    "id": row["tail_entity_id"],
                    "name": row["tail_entity_name"],
                    "entity_type": row["tail_entity_type"],
                }
                chunk = build_kg_relation_knowledge_chunk_row(
                    relation, head, tail, [dict(item) for item in evidence]
                )
                conn.execute(
                    self._insert_knowledge_chunk_sql(),
                    self._knowledge_chunk_payload(chunk),
                )
            else:
                conn.execute(self._set_kg_projection_status_sql(), proj_params)
        return row

    def search_kg_knowledge_text(
        self,
        query_text: str,
        *,
        top_k: int,
        query_terms: list[str] | None = None,
        status: str = "usable",
    ) -> list[Any]:
        """显式 KG 关键词召回，关键约束是只读已审核 KG 投影，不进入默认检索。"""
        normalized = str(query_text or "").strip()
        if not normalized:
            return []
        terms = [str(item).strip() for item in (query_terms or [normalized]) if str(item).strip()]
        params = {
            "query_like": f"%{normalized}%",
            "query_terms": terms,
            "status": status,
            "top_k": top_k,
        }
        with self.connect() as conn:
            rows = conn.execute(self._search_kg_knowledge_text_sql(), params).fetchall()
        return [self._row_to_retrieved_chunk(row) for row in rows]

    def get_kg_subgraph(
        self,
        *,
        center_entity_id: str,
        hops: int = 1,
        entity_types: list[str] | None = None,
        relation_types: list[str] | None = None,
        status: str = "usable",
        limit: int = 80,
    ) -> dict[str, Any]:
        """读取局部 KG 子图，关键约束是只返回已确认事实并限制节点边数量。"""
        params = {
            "center_entity_id": center_entity_id,
            "hops": max(1, min(int(hops or 1), 2)),
            "entity_types": entity_types or [],
            "relation_types": relation_types or [],
            "status": status,
            "limit": max(1, min(int(limit or 80), 200)),
        }
        with self.connect() as conn:
            rows = conn.execute(self._kg_subgraph_sql(), params).fetchall()
        nodes: dict[str, dict[str, Any]] = {}
        edges: list[dict[str, Any]] = []
        for row in rows:
            head = self._kg_node_payload(row, "head")
            tail = self._kg_node_payload(row, "tail")
            nodes[head["id"]] = head
            nodes[tail["id"]] = tail
            edges.append(
                {
                    "id": row["relation_id"],
                    "source": row["head_entity_id"],
                    "target": row["tail_entity_id"],
                    "relation_type": row["relation_type"],
                    "description": row.get("relation_description"),
                    "confidence": row.get("relation_confidence"),
                    "status": row.get("relation_status"),
                    "evidence_count": row.get("evidence_count", 0),
                }
            )
        return {"nodes": list(nodes.values()), "edges": edges}

    @staticmethod
    def _kg_node_payload(row: dict[str, Any], prefix: str) -> dict[str, Any]:
        """从子图 SQL 行整理节点，关键约束是字段名稳定供 2D/3D 复用。"""
        return {
            "id": row[f"{prefix}_entity_id"],
            "name": row[f"{prefix}_entity_name"],
            "entity_type": row[f"{prefix}_entity_type"],
            "description": row.get(f"{prefix}_entity_description"),
            "status": row.get(f"{prefix}_entity_status"),
            "confidence": row.get(f"{prefix}_entity_confidence"),
        }

    @staticmethod
    def _new_kg_job_id() -> str:
        """生成 KG 抽取任务 ID，关键约束是短 ID 便于本地 UI 展示。"""
        return f"kg_job_{uuid.uuid4().hex[:12]}"

    @staticmethod
    def _insert_kg_extraction_job_sql() -> str:
        """KG 抽取任务创建 SQL，关键约束是状态和来源字段完整落库。"""
        return """
        INSERT INTO kg_extraction_jobs (
            id, source_type, source_id, source_chunk_id, status,
            entity_count, relation_count, evidence_count, model, error
        )
        VALUES (
            %(id)s, %(source_type)s, %(source_id)s, %(source_chunk_id)s, %(status)s,
            %(entity_count)s, %(relation_count)s, %(evidence_count)s, %(model)s, %(error)s
        )
        RETURNING *
        """

    @staticmethod
    def _list_kg_entities_sql(*, where: str = "") -> str:
        """KG 实体审核列表 SQL，关键约束是聚合证据为前端可直接渲染的数组。"""
        return f"""
        SELECT
            ent.*,
            COALESCE(
                jsonb_agg(
                    jsonb_build_object(
                        'id', ev.id,
                        'source_type', ev.source_type,
                        'source_id', ev.source_id,
                        'source_chunk_id', ev.source_chunk_id,
                        'source_title', ev.source_title,
                        'section_path', ev.section_path,
                        'page_start', ev.page_start,
                        'page_end', ev.page_end,
                        'excerpt', ev.excerpt
                    )
                    ORDER BY ev.created_at ASC, ev.id ASC
                ) FILTER (WHERE ev.id IS NOT NULL),
                '[]'::jsonb
            ) AS evidence
        FROM kg_entities ent
        LEFT JOIN kg_evidence ev ON ev.entity_id = ent.id
        {where}
        GROUP BY ent.id
        ORDER BY ent.updated_at DESC, ent.id ASC
        LIMIT %(limit)s OFFSET %(offset)s
        """

    @staticmethod
    def _count_kg_entities_sql(*, where: str = "") -> str:
        """KG 实体审核列表计数 SQL，关键约束是和列表筛选口径一致。"""
        return f"""
        SELECT count(*) AS total
        FROM kg_entities ent
        {where}
        """

    @staticmethod
    def _list_kg_relations_sql(*, where: str = "") -> str:
        """KG 关系审核列表 SQL，关键约束是带头尾实体名称和证据数组。"""
        return f"""
        SELECT
            rel.*,
            head.name AS head_entity_name,
            head.entity_type AS head_entity_type,
            tail.name AS tail_entity_name,
            tail.entity_type AS tail_entity_type,
            COALESCE(
                jsonb_agg(
                    jsonb_build_object(
                        'id', ev.id,
                        'source_type', ev.source_type,
                        'source_id', ev.source_id,
                        'source_chunk_id', ev.source_chunk_id,
                        'source_title', ev.source_title,
                        'section_path', ev.section_path,
                        'page_start', ev.page_start,
                        'page_end', ev.page_end,
                        'excerpt', ev.excerpt
                    )
                    ORDER BY ev.created_at ASC, ev.id ASC
                ) FILTER (WHERE ev.id IS NOT NULL),
                '[]'::jsonb
            ) AS evidence
        FROM kg_relations rel
        JOIN kg_entities head ON head.id = rel.head_entity_id
        JOIN kg_entities tail ON tail.id = rel.tail_entity_id
        LEFT JOIN kg_evidence ev ON ev.relation_id = rel.id
        {where}
        GROUP BY rel.id, head.id, tail.id
        ORDER BY rel.updated_at DESC, rel.id ASC
        LIMIT %(limit)s OFFSET %(offset)s
        """

    @staticmethod
    def _count_kg_relations_sql(*, where: str = "") -> str:
        """KG 关系审核列表计数 SQL，关键约束是和列表筛选口径一致。"""
        return f"""
        SELECT count(*) AS total
        FROM kg_relations rel
        {where}
        """

    @staticmethod
    def _update_kg_extraction_job_sql(fields: set[str]) -> str:
        """KG 抽取任务更新 SQL，关键约束是调用方传入字段集合生成最小 UPDATE。"""
        allowed_order = ["status", "entity_count", "relation_count", "evidence_count", "model", "error"]
        assignments = ", ".join(f"{field} = %({field})s" for field in allowed_order if field in fields)
        return f"""
        UPDATE kg_extraction_jobs
        SET {assignments}, updated_at = now()
        WHERE id = %(id)s
        RETURNING *
        """

    @staticmethod
    def _kg_entity_params(entity: dict[str, Any]) -> dict[str, Any]:
        """整理实体写入参数，关键约束是候选状态默认 needs_review。"""
        return {
            "id": entity["id"],
            "name": entity["name"],
            "entity_type": entity["entity_type"],
            "aliases": json.dumps(entity.get("aliases", []), ensure_ascii=False),
            "description": entity.get("description"),
            "status": entity.get("status", "needs_review"),
            "confidence": entity.get("confidence"),
            "source_count": entity.get("source_count", len(entity.get("evidence", []))),
        }

    @staticmethod
    def _kg_relation_params(relation: dict[str, Any]) -> dict[str, Any]:
        """整理关系写入参数，关键约束是头尾实体 ID 必须来自 KG 实体表。"""
        return {
            "id": relation["id"],
            "head_entity_id": relation["head_entity_id"],
            "relation_type": relation["relation_type"],
            "tail_entity_id": relation["tail_entity_id"],
            "description": relation.get("description"),
            "status": relation.get("status", "needs_review"),
            "confidence": relation.get("confidence"),
        }

    @classmethod
    def _kg_evidence_params(
        cls,
        evidence: dict[str, Any],
        *,
        entity_id: str | None = None,
        relation_id: str | None = None,
    ) -> dict[str, Any]:
        """整理证据写入参数，关键约束是一条证据只绑定实体或关系之一。"""
        return {
            "id": cls._kg_evidence_id(evidence, entity_id=entity_id, relation_id=relation_id),
            "entity_id": entity_id,
            "relation_id": relation_id,
            "source_type": evidence["source_type"],
            "source_id": evidence["source_id"],
            "source_chunk_id": evidence.get("source_chunk_id"),
            "source_title": evidence.get("source_title"),
            "section_path": json.dumps(evidence.get("section_path", []), ensure_ascii=False),
            "page_start": evidence.get("page_start"),
            "page_end": evidence.get("page_end"),
            "excerpt": evidence["excerpt"],
        }

    @staticmethod
    def _kg_evidence_id(
        evidence: dict[str, Any],
        *,
        entity_id: str | None,
        relation_id: str | None,
    ) -> str:
        """生成稳定证据 ID，关键约束是重复抽取同一证据可幂等去重。"""
        payload = {
            "entity_id": entity_id,
            "relation_id": relation_id,
            "source_type": evidence.get("source_type"),
            "source_id": evidence.get("source_id"),
            "source_chunk_id": evidence.get("source_chunk_id"),
            "excerpt": evidence.get("excerpt"),
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        return "kg_ev_" + hashlib.sha256(encoded).hexdigest()[:16]

    @staticmethod
    def _upsert_kg_entity_sql() -> str:
        """实体候选 upsert SQL，关键约束是重复抽取只刷新描述、别名和证据计数。"""
        return """
        INSERT INTO kg_entities (
            id, name, entity_type, aliases, description, status, confidence, source_count
        )
        VALUES (
            %(id)s, %(name)s, %(entity_type)s, %(aliases)s::jsonb, %(description)s,
            %(status)s, %(confidence)s, %(source_count)s
        )
        ON CONFLICT (id) DO UPDATE SET
            name = EXCLUDED.name,
            entity_type = EXCLUDED.entity_type,
            aliases = EXCLUDED.aliases,
            description = EXCLUDED.description,
            confidence = EXCLUDED.confidence,
            source_count = GREATEST(kg_entities.source_count, EXCLUDED.source_count),
            updated_at = now()
        """

    @staticmethod
    def _upsert_kg_relation_sql() -> str:
        """关系候选 upsert SQL，关键约束是同一头尾关系重复抽取保持稳定 ID。"""
        return """
        INSERT INTO kg_relations (
            id, head_entity_id, relation_type, tail_entity_id, description, status, confidence
        )
        VALUES (
            %(id)s, %(head_entity_id)s, %(relation_type)s, %(tail_entity_id)s,
            %(description)s, %(status)s, %(confidence)s
        )
        ON CONFLICT (id) DO UPDATE SET
            description = EXCLUDED.description,
            confidence = EXCLUDED.confidence,
            updated_at = now()
        """

    @staticmethod
    def _insert_kg_evidence_sql() -> str:
        """证据写入 SQL，关键约束是同一证据 ID 重复写入时保持幂等。"""
        return """
        INSERT INTO kg_evidence (
            id, entity_id, relation_id, source_type, source_id, source_chunk_id,
            source_title, section_path, page_start, page_end, excerpt
        )
        VALUES (
            %(id)s, %(entity_id)s, %(relation_id)s, %(source_type)s, %(source_id)s,
            %(source_chunk_id)s, %(source_title)s, %(section_path)s::jsonb,
            %(page_start)s, %(page_end)s, %(excerpt)s
        )
        ON CONFLICT (id) DO NOTHING
        """

    @staticmethod
    def _confirm_kg_entity_sql() -> str:
        """确认实体 SQL，关键约束是只把待审核/禁用实体显式切到 usable。"""
        return """
        UPDATE kg_entities
        SET status = 'usable', updated_at = now()
        WHERE id = %(id)s
        RETURNING *
        """

    @staticmethod
    def _confirm_kg_relation_sql() -> str:
        """确认关系 SQL，关键约束是同时取回头尾实体名称和类型用于投影。"""
        return """
        WITH updated AS (
            UPDATE kg_relations
            SET status = 'usable', updated_at = now()
            WHERE id = %(id)s
            RETURNING *
        )
        SELECT
            updated.*,
            head.name AS head_entity_name,
            head.entity_type AS head_entity_type,
            tail.name AS tail_entity_name,
            tail.entity_type AS tail_entity_type
        FROM updated
        JOIN kg_entities head ON head.id = updated.head_entity_id
        JOIN kg_entities tail ON tail.id = updated.tail_entity_id
        """

    @staticmethod
    def _set_kg_entity_status_sql() -> str:
        """KG 实体状态更新 SQL，关键约束是只改审核状态不改证据。"""
        return """
        UPDATE kg_entities
        SET status = %(status)s, updated_at = now()
        WHERE id = %(id)s
        RETURNING *
        """

    @staticmethod
    def _set_kg_relation_status_sql() -> str:
        """KG 关系状态更新 SQL，关键约束是返回头尾实体信息供按需投影。"""
        return """
        WITH updated AS (
            UPDATE kg_relations
            SET status = %(status)s, updated_at = now()
            WHERE id = %(id)s
            RETURNING *
        )
        SELECT
            updated.*,
            head.name AS head_entity_name,
            head.entity_type AS head_entity_type,
            tail.name AS tail_entity_name,
            tail.entity_type AS tail_entity_type
        FROM updated
        JOIN kg_entities head ON head.id = updated.head_entity_id
        JOIN kg_entities tail ON tail.id = updated.tail_entity_id
        """

    @staticmethod
    def _kg_projection_exists_sql() -> str:
        """检查 KG 投影是否已存在，关键约束是按 source_type + source_id 精确查找。"""
        return """
        SELECT EXISTS (
            SELECT 1 FROM knowledge_chunks
            WHERE source_type = %(source_type)s
              AND source_id = %(id)s
        ) AS "exists"
        """

    @staticmethod
    def _set_kg_projection_status_sql() -> str:
        """KG 投影状态同步 SQL，关键约束是禁用后检索立即不可见。"""
        return """
        UPDATE knowledge_chunks
        SET status = %(status)s, updated_at = now()
        WHERE source_type = %(source_type)s
          AND source_id = %(id)s
        """

    @staticmethod
    def _list_kg_entity_evidence_sql() -> str:
        """读取实体证据 SQL，关键约束是投影 chunk 必须携带可追溯来源。"""
        return """
        SELECT
            source_type, source_id, source_chunk_id, source_title, section_path,
            page_start, page_end, excerpt
        FROM kg_evidence
        WHERE entity_id = %(entity_id)s
        ORDER BY created_at ASC, id ASC
        """

    @staticmethod
    def _list_kg_relation_evidence_sql() -> str:
        """读取关系证据 SQL，关键约束是投影 chunk 必须携带可追溯来源。"""
        return """
        SELECT
            source_type, source_id, source_chunk_id, source_title, section_path,
            page_start, page_end, excerpt
        FROM kg_evidence
        WHERE relation_id = %(relation_id)s
        ORDER BY created_at ASC, id ASC
        """

    @staticmethod
    def _search_kg_knowledge_text_sql() -> str:
        """KG 投影关键词召回 SQL，关键约束是显式只读 kg_entity/kg_relation。"""
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
        WHERE kc.status = %(status)s
          AND kc.source_type IN ('kg_entity', 'kg_relation')
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
    def _kg_subgraph_sql() -> str:
        """局部子图 SQL，关键约束是按 hops 可控返回并保留节点/边稳定 ID。"""
        return """
        WITH RECURSIVE reachable AS (
            SELECT %(center_entity_id)s AS entity_id, 0 AS depth
            UNION
            SELECT
                CASE WHEN rel.head_entity_id = reachable.entity_id
                     THEN rel.tail_entity_id
                     ELSE rel.head_entity_id
                END AS entity_id,
                reachable.depth + 1 AS depth
            FROM reachable
            JOIN kg_relations rel ON (
                rel.head_entity_id = reachable.entity_id
                OR rel.tail_entity_id = reachable.entity_id
            )
            JOIN kg_entities neighbor ON neighbor.id = (
                CASE WHEN rel.head_entity_id = reachable.entity_id
                     THEN rel.tail_entity_id
                     ELSE rel.head_entity_id
                END
            )
            WHERE reachable.depth < %(hops)s
              AND rel.status = %(status)s
              AND neighbor.status = %(status)s
        )
        SELECT
            rel.id AS relation_id,
            rel.relation_type,
            rel.description AS relation_description,
            rel.confidence AS relation_confidence,
            rel.status AS relation_status,
            head.id AS head_entity_id,
            head.name AS head_entity_name,
            head.entity_type AS head_entity_type,
            head.description AS head_entity_description,
            head.status AS head_entity_status,
            head.confidence AS head_entity_confidence,
            tail.id AS tail_entity_id,
            tail.name AS tail_entity_name,
            tail.entity_type AS tail_entity_type,
            tail.description AS tail_entity_description,
            tail.status AS tail_entity_status,
            tail.confidence AS tail_entity_confidence,
            COUNT(ev.id) AS evidence_count
        FROM kg_relations rel
        JOIN kg_entities head ON head.id = rel.head_entity_id
        JOIN kg_entities tail ON tail.id = rel.tail_entity_id
        LEFT JOIN kg_evidence ev ON ev.relation_id = rel.id
        WHERE rel.status = %(status)s
          AND head.status = %(status)s
          AND tail.status = %(status)s
          AND (
              rel.head_entity_id IN (SELECT entity_id FROM reachable WHERE depth < %(hops)s)
              OR rel.tail_entity_id IN (SELECT entity_id FROM reachable WHERE depth < %(hops)s)
          )
          AND (
              cardinality(%(entity_types)s::text[]) = 0
              OR head.entity_type = ANY(%(entity_types)s::text[])
              OR tail.entity_type = ANY(%(entity_types)s::text[])
          )
          AND (
              cardinality(%(relation_types)s::text[]) = 0
              OR rel.relation_type = ANY(%(relation_types)s::text[])
          )
        GROUP BY rel.id, head.id, tail.id
        ORDER BY rel.updated_at DESC, rel.id ASC
        LIMIT %(limit)s
        """
