from pathlib import Path

import json

from customer_service_agent.db import (
    Database,
    build_document_knowledge_chunk_row,
    build_embedding_text,
    build_faq_knowledge_chunk_row,
    build_import_candidate_faq_row,
    format_vector,
    score_to_distance,
)


def test_format_vector_outputs_pgvector_literal():
    assert format_vector([0.1, -0.2, 3]) == "[0.1,-0.2,3.0]"


def test_score_to_distance_converts_similarity_threshold():
    assert score_to_distance(0.35) == 0.65


def test_build_import_candidate_faq_row_defaults_to_needs_review():
    candidate = {
        "id": "cand_1",
        "question": "报告没生成怎么办？",
        "answer": "建议隔 10 分钟刷新查看进度。",
        "similar_questions": ["团体报告下载不了怎么办？"],
        "category": "报告服务",
        "tags": ["报告", "生成中"],
        "confidence": "medium",
        "source_excerpt": "客服 09:16: 隔10分钟刷新一次页面查看进度",
        "file_name": "chat.md",
        "chunk_id": "chunk_1",
    }

    row = build_import_candidate_faq_row(candidate)

    assert row["id"].startswith("faq_cand_1")
    assert row["status"] == "needs_review"
    assert row["question_variants"] == ["团体报告下载不了怎么办？"]
    assert row["evidence"] == [
        {
            "source_file": "chat.md",
            "chunk_id": "chunk_1",
            "excerpt": "客服 09:16: 隔10分钟刷新一次页面查看进度",
        }
    ]


def test_insert_import_candidate_sql_includes_duplicate_fields():
    """候选 FAQ 入库时需要保存查重结果字段。"""
    sql = Database._insert_import_candidate_sql()

    assert "duplicate_level" in sql
    assert "duplicate_score" in sql
    assert "duplicate_target_id" in sql
    assert "duplicate_reason" in sql


def test_build_faq_knowledge_chunk_row_uses_unified_retrieval_shape():
    """FAQ 应能映射为统一知识单元，后续和文档切片共用检索表。"""
    faq = {
        "id": "faq_1",
        "question": "报告没生成怎么办？",
        "question_variants": ["团体报告下载不了怎么办？"],
        "answer": "建议隔 10 分钟刷新查看进度。",
        "category": "报告服务",
        "tags": ["报告", "生成中"],
        "confidence": "high",
        "status": "usable",
        "source_file": "chat.md",
        "source_group": "import_review",
        "evidence": [{"chunk_id": "chunk_1", "excerpt": "隔10分钟刷新"}],
    }

    chunk = build_faq_knowledge_chunk_row(faq)

    assert chunk["source_type"] == "faq"
    assert chunk["source_id"] == "faq_1"
    assert chunk["source_chunk_id"] is None
    assert chunk["chunk_index"] == 0
    assert chunk["source_title"] == "报告没生成怎么办？"
    assert "问题：报告没生成怎么办？" in chunk["content"]
    assert "答案：建议隔 10 分钟刷新查看进度。" in chunk["content"]
    assert chunk["embedding_text"] == build_embedding_text(faq)
    assert "报告服务" in chunk["search_text"]
    assert "生成中" in chunk["search_text"]
    assert chunk["metadata"]["evidence"] == faq["evidence"]
    assert chunk["status"] == "usable"
    assert chunk["confidence"] == "high"


def test_build_document_knowledge_chunk_row_adds_contextual_embedding_text():
    """文档切片映射为知识单元时，embedding_text 应补充来源上下文。"""
    import_file = {
        "id": "file_1",
        "original_name": "平台使用手册.pdf",
        "file_type": "pdf",
        "parser": "mineru",
    }
    import_chunk = {
        "id": "chunk_3",
        "file_id": "file_1",
        "chunk_index": 3,
        "source_text": "用户无法登录时，先检查账号状态，再重置密码。",
        "keywords": ["登录", "密码"],
        "status": "generated",
        "message_count": 0,
        "start_at": None,
        "end_at": None,
        "section_path": ["账号管理", "登录问题"],
        "page_start": 2,
        "page_end": 3,
        "block_type": "paragraph",
        "parent_chunk_id": "parent_1",
        "chunk_level": "child",
        "source_offsets": {"start": 10, "end": 48},
    }

    chunk = build_document_knowledge_chunk_row(import_chunk, import_file)

    assert chunk["source_type"] == "document"
    assert chunk["source_id"] == "file_1"
    assert chunk["source_chunk_id"] == "chunk_3"
    assert chunk["chunk_index"] == 3
    assert chunk["source_title"] == "平台使用手册.pdf"
    assert chunk["content"] == "用户无法登录时，先检查账号状态，再重置密码。"
    assert "文件：平台使用手册.pdf" in chunk["embedding_text"]
    assert "章节：账号管理 > 登录问题" in chunk["embedding_text"]
    assert "页码：2-3" in chunk["embedding_text"]
    assert "块类型：paragraph" in chunk["embedding_text"]
    assert "关键词：登录，密码" in chunk["embedding_text"]
    assert "正文：用户无法登录时，先检查账号状态，再重置密码。" in chunk["embedding_text"]
    assert "平台使用手册.pdf" in chunk["search_text"]
    assert "账号管理 > 登录问题" in chunk["search_text"]
    assert "登录" in chunk["search_text"]
    assert chunk["tags"] == ["登录", "密码"]
    assert chunk["metadata"]["file_type"] == "pdf"
    assert chunk["metadata"]["parser"] == "mineru"
    assert chunk["metadata"]["section_path"] == ["账号管理", "登录问题"]
    assert chunk["metadata"]["page_start"] == 2
    assert chunk["metadata"]["page_end"] == 3
    assert chunk["parent_chunk_id"] == "parent_1"
    assert chunk["chunk_level"] == "child"
    assert chunk["section_path"] == ["账号管理", "登录问题"]
    assert chunk["page_start"] == 2
    assert chunk["page_end"] == 3
    assert chunk["block_type"] == "paragraph"
    assert chunk["source_offsets"] == {"start": 10, "end": 48}
    assert chunk["status"] == "needs_review"


def test_knowledge_chunks_schema_supports_vector_and_keyword_retrieval():
    """统一知识单元表需要同时预留向量检索和全文检索能力。"""
    schema = Path("sql/001_init.sql").read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS knowledge_chunks" in schema
    assert "source_type TEXT NOT NULL" in schema
    assert "source_id TEXT NOT NULL" in schema
    assert "source_chunk_id TEXT" in schema
    assert "parent_chunk_id TEXT" in schema
    assert "chunk_level TEXT NOT NULL DEFAULT 'chunk'" in schema
    assert "section_path JSONB NOT NULL DEFAULT '[]'::jsonb" in schema
    assert "page_start INTEGER" in schema
    assert "page_end INTEGER" in schema
    assert "block_type TEXT" in schema
    assert "source_offsets JSONB NOT NULL DEFAULT '{}'::jsonb" in schema
    assert "content TEXT NOT NULL" in schema
    assert "embedding vector(1024)" in schema
    assert "metadata JSONB NOT NULL DEFAULT '{}'::jsonb" in schema
    assert "UNIQUE (source_type, source_id, chunk_index)" in schema
    assert "knowledge_chunks_parent_idx" in schema
    assert "knowledge_chunks_section_path_idx" in schema
    assert "knowledge_chunks_embedding_idx" in schema
    assert "knowledge_chunks_search_idx" in schema
    assert "to_tsvector('simple', search_text)" in schema


def test_insert_knowledge_chunk_sql_uses_single_upsert_shape():
    """统一知识单元写入 SQL 应覆盖来源、内容、检索文本和 embedding 状态。"""
    sql = Database._insert_knowledge_chunk_sql()

    assert "INSERT INTO knowledge_chunks" in sql
    assert "source_type" in sql
    assert "source_id" in sql
    assert "source_chunk_id" in sql
    assert "parent_chunk_id" in sql
    assert "chunk_level" in sql
    assert "section_path" in sql
    assert "page_start" in sql
    assert "page_end" in sql
    assert "block_type" in sql
    assert "source_offsets" in sql
    assert "embedding_text" in sql
    assert "search_text" in sql
    assert "ON CONFLICT (source_type, source_id, chunk_index)" in sql


def test_sync_ready_faq_knowledge_chunks_sql_reuses_existing_vectors():
    """已有 FAQ 投影到统一知识单元时应复用现成向量，不重新请求 embedding。"""
    sql = Database._sync_ready_faq_knowledge_chunks_sql()

    assert "INSERT INTO knowledge_chunks" in sql
    assert "FROM faq_documents" in sql
    assert "embedding_status = 'ready'" in sql
    assert "embedding IS NOT NULL" in sql
    assert "jsonb_build_object" in sql
    assert "ON CONFLICT (source_type, source_id, chunk_index)" in sql


def test_search_knowledge_sql_reads_unified_chunks_without_confidence_filter():
    """智能问答检索应读取统一知识单元，允许文档切片这类无 confidence 来源参与。"""
    sql = Database._search_knowledge_sql()

    assert "FROM knowledge_chunks" in sql
    assert "source_type" in sql
    assert "parent_chunk_id" in sql
    assert "chunk_level" in sql
    assert "section_path" in sql
    assert "content" in sql
    assert "metadata" in sql
    assert "embedding_status = 'ready'" in sql
    assert "COALESCE(fq.status, kc.status) = %(status)s" in sql
    assert "confidence = %(confidence)s" not in sql


def test_search_knowledge_sql_filters_disabled_files_and_chunks():
    """向量检索 SQL 必须 LEFT JOIN import_files / import_chunks 并过滤禁用项。"""
    sql = Database._search_knowledge_sql()

    assert "LEFT JOIN import_files imp" in sql
    assert "LEFT JOIN import_chunks ic" in sql
    assert "COALESCE(imp.is_disabled, false) = false" in sql
    assert "COALESCE(ic.is_disabled, false) = false" in sql


def test_search_knowledge_sql_excludes_document_parent_from_direct_retrieval():
    """文档 parent 只用于 child 命中后的上下文回填，不应参与普通向量候选竞争。"""
    sql = Database._search_knowledge_sql()

    assert "(kc.source_type <> 'document' OR kc.chunk_level <> 'parent')" in sql


def test_search_knowledge_text_sql_filters_disabled_files_and_chunks():
    """关键词检索 SQL 同样要应用文件 / 切片级禁用过滤。"""
    sql = Database._search_knowledge_text_sql()

    assert "LEFT JOIN import_files imp" in sql
    assert "LEFT JOIN import_chunks ic" in sql
    assert "COALESCE(imp.is_disabled, false) = false" in sql
    assert "COALESCE(ic.is_disabled, false) = false" in sql


def test_search_knowledge_text_sql_excludes_document_parent_from_direct_retrieval():
    """关键词召回同样不能让文档 parent 与 child 同权竞争。"""
    sql = Database._search_knowledge_text_sql()

    assert "(kc.source_type <> 'document' OR kc.chunk_level <> 'parent')" in sql


def test_get_parent_context_chunks_sql_filters_disabled_files_and_chunks():
    """parent 上下文回填也需要排除禁用文件或切片，否则禁用后仍可能被 parent 召回。"""
    sql = Database._get_parent_context_chunks_sql()

    assert "LEFT JOIN import_files imp" in sql
    assert "LEFT JOIN import_chunks ic" in sql
    assert "COALESCE(imp.is_disabled, false) = false" in sql
    assert "COALESCE(ic.is_disabled, false) = false" in sql


def test_import_files_schema_supports_disabled_toggle():
    """import_files / import_chunks 必须各带 is_disabled 列，提供文件级 / 切片级开关。"""
    schema = Path("sql/001_init.sql").read_text(encoding="utf-8")

    assert "ALTER TABLE import_files" in schema
    assert "ADD COLUMN IF NOT EXISTS is_disabled BOOLEAN NOT NULL DEFAULT false" in schema
    # 一次出现已覆盖 import_files；保证 import_chunks 也含同列
    assert schema.count("is_disabled BOOLEAN NOT NULL DEFAULT false") >= 2


def test_import_files_schema_persists_document_chunker_type():
    """import_files 必须持久化 chunker_type，让文件级后解析路线可追溯。"""
    schema = Path("sql/001_init.sql").read_text(encoding="utf-8")

    assert "ADD COLUMN IF NOT EXISTS chunker_type TEXT NOT NULL DEFAULT 'naive'" in schema


def test_search_knowledge_text_sql_reads_keyword_fields():
    """关键词召回应读取统一知识单元的 search_text、标题和正文。"""
    sql = Database._search_knowledge_text_sql()

    assert "FROM knowledge_chunks" in sql
    assert "parent_chunk_id" in sql
    assert "chunk_level" in sql
    assert "section_path" in sql
    assert "unnest(%(query_terms)s::text[])" in sql
    assert "source_title ILIKE %(query_like)s" in sql
    assert "content ILIKE %(query_like)s" in sql
    assert "search_text ILIKE %(query_like)s" in sql
    assert "source_title ILIKE ('%%' || term || '%%')" in sql
    assert "ORDER BY score DESC" in sql


def test_search_knowledge_text_sql_escapes_percent_literals_for_psycopg():
    """关键词 SQL 里的 LIKE 百分号必须转义，避免 psycopg 误判为占位符。"""
    sql = Database._search_knowledge_text_sql()

    assert "('%%' || term || '%%')" in sql
    assert "('%' || term || '%')" not in sql


def test_retrieval_alias_schema_records_canonical_terms_and_aliases():
    """检索别名词典需要记录标准词、别名和启用状态。"""
    schema = Path("sql/001_init.sql").read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS retrieval_aliases" in schema
    assert "canonical TEXT NOT NULL" in schema
    assert "aliases JSONB NOT NULL DEFAULT '[]'::jsonb" in schema
    assert "retrieval_aliases_status_idx" in schema


def test_retrieval_eval_schema_records_expected_hits_and_runs():
    """检索评测表需要保存测试问题、期望命中和每次运行结果。"""
    schema = Path("sql/001_init.sql").read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS retrieval_eval_cases" in schema
    assert "expected_source_ids JSONB NOT NULL DEFAULT '[]'::jsonb" in schema
    assert "expected_chunk_ids JSONB NOT NULL DEFAULT '[]'::jsonb" in schema
    assert "CREATE TABLE IF NOT EXISTS retrieval_eval_runs" in schema
    assert "metrics JSONB NOT NULL DEFAULT '{}'::jsonb" in schema


def test_list_retrieval_eval_cases_includes_latest_run():
    """评测用例列表应带最近一次运行，页面刷新后仍可回放指标和候选。"""

    class _FakeConn:
        def __init__(self):
            self.calls = []

        def execute(self, sql, params=None):
            self.calls.append((sql, params or {}))
            return self

        def fetchall(self):
            return [
                {
                    "id": "eval_1",
                    "question": "报告导出失败怎么办？",
                    "latest_run": {
                        "id": "eval_run_1",
                        "strategy": "retrieval_hybrid_v1",
                    },
                }
            ]

        def fetchone(self):
            return {"total": 1}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    conn = _FakeConn()
    db = Database("postgresql://unused")
    db.connect = lambda: conn

    result = db.list_retrieval_eval_cases(status="active", limit=20, offset=0)

    assert result["items"][0]["latest_run"]["id"] == "eval_run_1"
    rows_sql = conn.calls[0][0]
    assert "LEFT JOIN LATERAL" in rows_sql
    assert "FROM retrieval_eval_runs" in rows_sql
    assert "run.case_id = c.id" in rows_sql
    assert "ORDER BY run.created_at DESC" in rows_sql
    assert "jsonb_build_object" in rows_sql
    assert conn.calls[0][1] == {"status": "active", "limit": 20, "offset": 0}


def test_import_file_embedding_summaries_sql_counts_document_chunks():
    """文档列表需要按文件汇总切片向量状态，区分完成、部分、过期和失败。"""
    sql = Database._import_file_embedding_summaries_sql()

    assert "FROM import_chunks" in sql
    assert "FROM knowledge_chunks" in sql
    assert "source_type = 'document'" in sql
    assert "expected_knowledge_count" in sql
    assert "jsonb_array_elements" in sql
    assert "ready_count" in sql
    assert "stale_count" in sql
    assert "failed_count" in sql
    assert "missing_count" in sql


def test_import_chunks_schema_preserves_parser_structure_for_retrieval():
    """导入切片表需要保存解析器给出的章节、页码和块类型，供后续生成父子知识单元。"""
    schema = Path("sql/001_init.sql").read_text(encoding="utf-8")
    insert_sql = Database._insert_import_chunk_sql()

    assert "section_path JSONB NOT NULL DEFAULT '[]'::jsonb" in schema
    assert "page_start INTEGER" in schema
    assert "page_end INTEGER" in schema
    assert "block_type TEXT" in schema
    assert "source_offsets JSONB NOT NULL DEFAULT '{}'::jsonb" in schema
    assert "source_blocks JSONB NOT NULL DEFAULT '[]'::jsonb" in schema
    assert "children_delimiter TEXT NOT NULL DEFAULT ''" in schema
    assert "DROP COLUMN IF EXISTS parent_chunk_id" in schema
    assert "DROP COLUMN IF EXISTS chunk_level" in schema
    assert "section_path" in insert_sql
    assert "page_start" in insert_sql
    assert "page_end" in insert_sql
    assert "block_type" in insert_sql
    assert "source_blocks" in insert_sql
    assert "children_delimiter" in insert_sql


def test_update_import_chunk_text_sql_marks_existing_knowledge_chunk_stale():
    """切片原文保存后，应删除旧 child 并只把 parent 知识单元标记为 stale。"""
    update_sql = Database._update_import_chunk_text_sql()
    delete_sql = Database._delete_document_chunk_child_knowledge_sql()
    stale_sql = Database._mark_document_chunk_knowledge_stale_sql()

    assert "UPDATE import_chunks" in update_sql
    assert "source_text = %(source_text)s" in update_sql
    assert "source_blocks = '[]'::jsonb" in update_sql
    assert "DELETE FROM knowledge_chunks" in delete_sql
    assert "parent_chunk_id = ('kc_document_' || %(chunk_id)s)" in delete_sql
    assert "UPDATE knowledge_chunks" in stale_sql
    assert "source_type = 'document'" in stale_sql
    assert "source_chunk_id = %(chunk_id)s" in stale_sql
    assert "parent_chunk_id = ('kc_document_' || %(chunk_id)s)" not in stale_sql
    assert "embedding_status = 'stale'" in stale_sql


def test_replace_import_chunks_removes_old_document_knowledge_chunks():
    """重新解析替换切片前，应先清理同文件旧知识单元，避免问答页召回旧向量。"""

    class _FakeConn:
        def __init__(self):
            self.calls = []

        def execute(self, sql, params=None):
            self.calls.append((sql, params or {}))
            return self

        def fetchone(self):
            return {}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    conn = _FakeConn()
    db = Database("postgresql://unused")
    db.connect = lambda: conn

    db.replace_import_chunks("imp_1", [])

    assert conn.calls
    delete_knowledge_calls = [
        (sql, params)
        for sql, params in conn.calls
        if "DELETE FROM knowledge_chunks" in sql
    ]
    assert delete_knowledge_calls, "replace_import_chunks must clear old document knowledge"
    sql, params = delete_knowledge_calls[0]
    assert "source_type = 'document'" in sql
    assert "source_id = %(file_id)s" in sql
    assert params == {"file_id": "imp_1"}
    import_delete_index = next(
        index for index, (sql, _params) in enumerate(conn.calls) if "DELETE FROM import_chunks" in sql
    )
    knowledge_delete_index = conn.calls.index(delete_knowledge_calls[0])
    assert knowledge_delete_index < import_delete_index


def test_parent_context_sql_reads_same_source_parent_chunks():
    """父级上下文回填只能读取同来源、可用且 ready 的 parent chunk。"""
    sql = Database._get_parent_context_chunks_sql()

    assert "FROM knowledge_chunks child" in sql
    assert "JOIN knowledge_chunks parent" in sql
    assert "parent.id = child.parent_chunk_id" in sql
    assert "parent.source_type = child.source_type" in sql
    assert "parent.source_id = child.source_id" in sql
    assert "parent.chunk_level = 'parent'" in sql
    assert "parent.status = %(status)s" in sql
    assert "parent.embedding_status = 'ready'" in sql


def test_query_analytics_events_schema_records_query_intent_and_hits():
    """查询打点表需要保存原始 query、意图、命中数、score、rerank 标记、来源标识。"""
    schema = Path("sql/001_init.sql").read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS query_analytics_events" in schema
    assert "query TEXT NOT NULL" in schema
    assert "intent TEXT" in schema
    assert "retrieved_chunk_ids TEXT[] NOT NULL DEFAULT '{}'" in schema
    assert "top_score DOUBLE PRECISION" in schema
    assert "hit_count INT NOT NULL DEFAULT 0" in schema
    assert "rerank_used BOOLEAN NOT NULL DEFAULT false" in schema
    assert "latency_ms INT" in schema
    assert "requester_type TEXT NOT NULL DEFAULT 'unknown'" in schema
    assert "requester_id TEXT" in schema
    assert "metadata JSONB NOT NULL DEFAULT '{}'::jsonb" in schema
    assert "idx_query_analytics_created_at" in schema
    assert "idx_query_analytics_hit_zero" in schema


def test_query_analytics_cluster_summaries_schema_supports_llm_clustering():
    """零命中 LLM 聚类结果需要存到独立表，保留 period_start / period_end / sample_queries。"""
    schema = Path("sql/001_init.sql").read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS query_analytics_cluster_summaries" in schema
    assert "period_start TIMESTAMPTZ NOT NULL" in schema
    assert "period_end TIMESTAMPTZ NOT NULL" in schema
    assert "cluster_label TEXT NOT NULL" in schema
    assert "suggested_content TEXT" in schema
    assert "event_count INT NOT NULL" in schema
    assert "sample_queries TEXT[] NOT NULL DEFAULT '{}'" in schema


def test_record_query_event_sql_inserts_all_fields():
    """打点写入应覆盖所有分析维度，确保看板查询有数据。"""
    sql = Database._record_query_event_sql()

    assert "INSERT INTO query_analytics_events" in sql
    assert "query" in sql
    assert "intent" in sql
    assert "retrieved_chunk_ids" in sql
    assert "top_score" in sql
    assert "hit_count" in sql
    assert "rerank_used" in sql
    assert "latency_ms" in sql
    assert "requester_type" in sql
    assert "requester_id" in sql
    assert "metadata" in sql


def test_list_top_queries_sql_groups_by_normalized_query():
    """高频查询聚合应按归一化后的 query 计数并按时间过滤。"""
    sql = Database._list_top_queries_sql()

    assert "FROM query_analytics_events" in sql
    assert "GROUP BY" in sql
    assert "COUNT(*)" in sql
    assert "created_at >= %(since)s" in sql
    assert "ORDER BY" in sql
    assert "LIMIT %(limit)s" in sql


def test_list_zero_hit_queries_sql_filters_hit_count_zero():
    """零命中查询读取应只看 hit_count = 0 的记录。"""
    sql = Database._list_zero_hit_queries_sql()

    assert "FROM query_analytics_events" in sql
    assert "hit_count = 0" in sql
    assert "created_at >= %(since)s" in sql
    assert "ORDER BY created_at DESC" in sql


def test_list_low_score_queries_sql_filters_top_score_below_threshold():
    """低置信查询读取应只看 top_score 低于阈值且至少命中一条的记录。"""
    sql = Database._list_low_score_queries_sql()

    assert "FROM query_analytics_events" in sql
    assert "hit_count > 0" in sql
    assert "top_score < %(threshold)s" in sql
    assert "created_at >= %(since)s" in sql


def test_query_hit_rate_timeseries_sql_buckets_by_date():
    """命中率时序应按时间桶聚合 hit_count > 0 的比例。"""
    sql = Database._query_hit_rate_timeseries_sql()

    assert "FROM query_analytics_events" in sql
    assert "date_trunc" in sql
    assert "hit_count > 0" in sql
    assert "created_at >= %(since)s" in sql


def test_top_referenced_chunks_sql_unnests_retrieved_chunk_ids():
    """chunk 引用频次需要展开 retrieved_chunk_ids 数组并按 chunk_id 聚合。"""
    sql = Database._top_referenced_chunks_sql()

    assert "FROM query_analytics_events" in sql
    assert "unnest(retrieved_chunk_ids)" in sql
    assert "GROUP BY" in sql
    assert "COUNT(*)" in sql
    assert "LIMIT %(limit)s" in sql


def test_database_record_query_event_writes_via_connection():
    """Database.record_query_event 应通过 connect 把事件写入 query_analytics_events。"""

    class _FakeCursor:
        def __init__(self, store):
            self.store = store

        def execute(self, sql, params=None):
            self.store.append((sql, params))

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _FakeConn:
        def __init__(self, store):
            self.store = store

        def execute(self, sql, params=None):
            self.store.append((sql, params))
            return _FakeCursor(self.store)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    store: list = []
    db = Database("postgresql://unused")
    db.connect = lambda: _FakeConn(store)

    db.record_query_event(
        {
            "query": "如何重置密码",
            "intent": "procedure",
            "retrieved_chunk_ids": ["kc_1", "kc_2"],
            "top_score": 0.78,
            "hit_count": 2,
            "rerank_used": True,
            "latency_ms": 154,
            "requester_type": "agent",
            "requester_id": "listing-writer",
            "metadata": {"flow": "basic_rag"},
        }
    )

    assert store, "record_query_event must execute SQL via connect()"
    sql, params = store[0]
    assert "INSERT INTO query_analytics_events" in sql
    assert params["query"] == "如何重置密码"
    assert params["intent"] == "procedure"
    assert params["retrieved_chunk_ids"] == ["kc_1", "kc_2"]
    assert params["top_score"] == 0.78
    assert params["hit_count"] == 2
    assert params["rerank_used"] is True
    assert params["latency_ms"] == 154
    assert params["requester_type"] == "agent"
    assert params["requester_id"] == "listing-writer"
    assert params["metadata"] == json.dumps({"flow": "basic_rag"}, ensure_ascii=False)
