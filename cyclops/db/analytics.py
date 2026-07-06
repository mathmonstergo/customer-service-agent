from __future__ import annotations

import json
from datetime import datetime
from typing import Any


class AnalyticsMixin:
    """查询打点 / 高频 / 零命中 / 低置信 / 时序 / chunk 频次 / 聚类摘要。"""

    def record_query_event(self, event: dict[str, Any]) -> None:
        """打点：把一次查询的命中情况写入 query_analytics_events。"""
        metadata = event.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}
        chunk_ids = [str(item) for item in (event.get("retrieved_chunk_ids") or []) if str(item)]
        params = {
            "query": str(event.get("query") or ""),
            "intent": event.get("intent"),
            "retrieved_chunk_ids": chunk_ids,
            "top_score": event.get("top_score"),
            "hit_count": int(event.get("hit_count") or 0),
            "rerank_used": bool(event.get("rerank_used") or False),
            "latency_ms": event.get("latency_ms"),
            "requester_type": str(event.get("requester_type") or "unknown"),
            "requester_id": event.get("requester_id"),
            "metadata": json.dumps(metadata, ensure_ascii=False),
        }
        with self.connect() as conn:
            conn.execute(self._record_query_event_sql(), params)

    def list_top_queries(self, *, limit: int, since: datetime) -> list[dict[str, Any]]:
        """读取最高频查询，前端用于看板高频查询表。"""
        with self.connect() as conn:
            rows = conn.execute(
                self._list_top_queries_sql(),
                {"limit": int(limit), "since": since},
            ).fetchall()
        return [self._row_dict(row) for row in rows]

    def list_zero_hit_queries(self, *, limit: int, since: datetime) -> list[dict[str, Any]]:
        """读取最近零命中查询，用于看板零命中 tab 和 LLM 聚类来源。"""
        with self.connect() as conn:
            rows = conn.execute(
                self._list_zero_hit_queries_sql(),
                {"limit": int(limit), "since": since},
            ).fetchall()
        return [self._row_dict(row) for row in rows]

    def list_low_score_queries(
        self,
        *,
        limit: int,
        since: datetime,
        threshold: float,
    ) -> list[dict[str, Any]]:
        """读取最近低置信查询，threshold 由调用方按 rag_min_score 决定。"""
        with self.connect() as conn:
            rows = conn.execute(
                self._list_low_score_queries_sql(),
                {"limit": int(limit), "since": since, "threshold": float(threshold)},
            ).fetchall()
        return [self._row_dict(row) for row in rows]

    def query_hit_rate_timeseries(self, *, since: datetime) -> list[dict[str, Any]]:
        """读取命中率时序，桶粒度按日。"""
        with self.connect() as conn:
            rows = conn.execute(
                self._query_hit_rate_timeseries_sql(),
                {"since": since},
            ).fetchall()
        return [self._row_dict(row) for row in rows]

    def top_referenced_chunks(self, *, limit: int, since: datetime) -> list[dict[str, Any]]:
        """读取被引用次数最多的 chunk_id。"""
        with self.connect() as conn:
            rows = conn.execute(
                self._top_referenced_chunks_sql(),
                {"limit": int(limit), "since": since},
            ).fetchall()
        return [self._row_dict(row) for row in rows]

    def query_analytics_overview(
        self,
        *,
        today: datetime,
        last_7d: datetime,
        last_30d: datetime,
    ) -> dict[str, Any]:
        """看板概览：分别返回今日 / 7 日 / 30 日的总查询、命中率、零命中数。"""
        sql = """
        SELECT
            COUNT(*) FILTER (WHERE created_at >= %(since)s) AS total,
            SUM(CASE WHEN hit_count > 0 AND created_at >= %(since)s THEN 1 ELSE 0 END) AS hits,
            SUM(CASE WHEN hit_count = 0 AND created_at >= %(since)s THEN 1 ELSE 0 END) AS zero_hit
        FROM query_analytics_events
        """
        result: dict[str, Any] = {}
        with self.connect() as conn:
            for key, since in (("today", today), ("last_7d", last_7d), ("last_30d", last_30d)):
                row = conn.execute(sql, {"since": since}).fetchone()
                total = int((row or {}).get("total") or 0)
                hits = int((row or {}).get("hits") or 0)
                zero_hit = int((row or {}).get("zero_hit") or 0)
                hit_rate = (hits / total) if total else 0.0
                result[key] = {"total": total, "hit_rate": hit_rate, "zero_hit": zero_hit}
        return result

    def save_cluster_summary(self, row: dict[str, Any]) -> dict[str, Any]:
        """写入零命中聚类摘要。"""
        params = {
            "period_start": row["period_start"],
            "period_end": row["period_end"],
            "cluster_label": str(row["cluster_label"]),
            "suggested_content": row.get("suggested_content"),
            "event_count": int(row.get("event_count") or 0),
            "sample_queries": [str(item) for item in (row.get("sample_queries") or [])],
        }
        sql = """
        INSERT INTO query_analytics_cluster_summaries (
            period_start, period_end, cluster_label, suggested_content, event_count, sample_queries
        )
        VALUES (
            %(period_start)s, %(period_end)s, %(cluster_label)s, %(suggested_content)s,
            %(event_count)s, %(sample_queries)s
        )
        RETURNING id, created_at, period_start, period_end, cluster_label,
                  suggested_content, event_count, sample_queries
        """
        with self.connect() as conn:
            inserted = conn.execute(sql, params).fetchone()
        return self._row_dict(inserted or {})

    def list_cluster_summaries(self, *, limit: int = 20) -> list[dict[str, Any]]:
        """读取最近的零命中聚类摘要。"""
        sql = """
        SELECT id, created_at, period_start, period_end, cluster_label,
               suggested_content, event_count, sample_queries
        FROM query_analytics_cluster_summaries
        ORDER BY created_at DESC
        LIMIT %(limit)s
        """
        with self.connect() as conn:
            rows = conn.execute(sql, {"limit": int(limit)}).fetchall()
        return [self._row_dict(row) for row in rows]

    @staticmethod
    def _record_query_event_sql() -> str:
        """打点 SQL：写入一条 query analytics 事件。"""
        return """
        INSERT INTO query_analytics_events (
            query, intent, retrieved_chunk_ids, top_score, hit_count,
            rerank_used, latency_ms, requester_type, requester_id, metadata
        )
        VALUES (
            %(query)s, %(intent)s, %(retrieved_chunk_ids)s, %(top_score)s, %(hit_count)s,
            %(rerank_used)s, %(latency_ms)s, %(requester_type)s, %(requester_id)s, %(metadata)s::jsonb
        )
        """

    @staticmethod
    def _list_top_queries_sql() -> str:
        """高频查询聚合：按归一化 query 计数。"""
        return """
        SELECT
            lower(btrim(query)) AS query,
            COUNT(*) AS count,
            MAX(created_at) AS last_seen,
            AVG(CASE WHEN hit_count > 0 THEN 1.0 ELSE 0.0 END) AS hit_rate
        FROM query_analytics_events
        WHERE created_at >= %(since)s
        GROUP BY lower(btrim(query))
        ORDER BY count DESC, last_seen DESC
        LIMIT %(limit)s
        """

    @staticmethod
    def _list_zero_hit_queries_sql() -> str:
        """零命中查询：hit_count = 0 的最近事件。"""
        return """
        SELECT id, created_at, query, intent, requester_type, requester_id
        FROM query_analytics_events
        WHERE hit_count = 0
          AND created_at >= %(since)s
        ORDER BY created_at DESC
        LIMIT %(limit)s
        """

    @staticmethod
    def _list_low_score_queries_sql() -> str:
        """低置信查询：召回了但 top_score 不达阈值。"""
        return """
        SELECT id, created_at, query, intent, top_score, hit_count, requester_type
        FROM query_analytics_events
        WHERE hit_count > 0
          AND top_score IS NOT NULL
          AND top_score < %(threshold)s
          AND created_at >= %(since)s
        ORDER BY created_at DESC
        LIMIT %(limit)s
        """

    @staticmethod
    def _query_hit_rate_timeseries_sql() -> str:
        """每日命中率时序：按 date_trunc('day') 桶聚合。"""
        return """
        SELECT
            date_trunc('day', created_at) AS bucket,
            COUNT(*) AS total,
            SUM(CASE WHEN hit_count > 0 THEN 1 ELSE 0 END) AS hits
        FROM query_analytics_events
        WHERE created_at >= %(since)s
        GROUP BY bucket
        ORDER BY bucket ASC
        """

    @staticmethod
    def _top_referenced_chunks_sql() -> str:
        """chunk 引用频次：展开 retrieved_chunk_ids 后聚合。"""
        return """
        SELECT chunk_id, COUNT(*) AS count
        FROM (
            SELECT unnest(retrieved_chunk_ids) AS chunk_id
            FROM query_analytics_events
            WHERE created_at >= %(since)s
        ) AS s
        WHERE chunk_id IS NOT NULL AND chunk_id <> ''
        GROUP BY chunk_id
        ORDER BY count DESC, chunk_id ASC
        LIMIT %(limit)s
        """
