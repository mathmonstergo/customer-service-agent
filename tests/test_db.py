from pathlib import Path

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


def test_build_document_knowledge_chunk_row_keeps_raw_slice_content():
    """文档切片映射为知识单元时，content 和 embedding_text 默认使用切片原文。"""
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
    }

    chunk = build_document_knowledge_chunk_row(import_chunk, import_file)

    assert chunk["source_type"] == "document"
    assert chunk["source_id"] == "file_1"
    assert chunk["source_chunk_id"] == "chunk_3"
    assert chunk["chunk_index"] == 3
    assert chunk["source_title"] == "平台使用手册.pdf"
    assert chunk["content"] == "用户无法登录时，先检查账号状态，再重置密码。"
    assert chunk["embedding_text"] == "用户无法登录时，先检查账号状态，再重置密码。"
    assert "平台使用手册.pdf" in chunk["search_text"]
    assert "登录" in chunk["search_text"]
    assert chunk["tags"] == ["登录", "密码"]
    assert chunk["metadata"]["file_type"] == "pdf"
    assert chunk["metadata"]["parser"] == "mineru"
    assert chunk["status"] == "needs_review"


def test_knowledge_chunks_schema_supports_vector_and_keyword_retrieval():
    """统一知识单元表需要同时预留向量检索和全文检索能力。"""
    schema = Path("sql/001_init.sql").read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS knowledge_chunks" in schema
    assert "source_type TEXT NOT NULL" in schema
    assert "source_id TEXT NOT NULL" in schema
    assert "source_chunk_id TEXT" in schema
    assert "content TEXT NOT NULL" in schema
    assert "embedding vector(1024)" in schema
    assert "metadata JSONB NOT NULL DEFAULT '{}'::jsonb" in schema
    assert "UNIQUE (source_type, source_id, chunk_index)" in schema
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
    assert "content" in sql
    assert "metadata" in sql
    assert "embedding_status = 'ready'" in sql
    assert "status = %(status)s" in sql
    assert "confidence = %(confidence)s" not in sql


def test_import_file_embedding_summaries_sql_counts_document_chunks():
    """文档列表需要按文件汇总切片向量状态，区分完成、部分、过期和失败。"""
    sql = Database._import_file_embedding_summaries_sql()

    assert "FROM import_chunks" in sql
    assert "FROM knowledge_chunks" in sql
    assert "source_type = 'document'" in sql
    assert "ready_count" in sql
    assert "stale_count" in sql
    assert "failed_count" in sql
    assert "missing_count" in sql


def test_update_import_chunk_text_sql_marks_existing_knowledge_chunk_stale():
    """切片原文保存后，对应统一知识单元应更新正文并标记为 stale。"""
    update_sql = Database._update_import_chunk_text_sql()
    stale_sql = Database._mark_document_chunk_knowledge_stale_sql()

    assert "UPDATE import_chunks" in update_sql
    assert "source_text = %(source_text)s" in update_sql
    assert "UPDATE knowledge_chunks" in stale_sql
    assert "source_type = 'document'" in stale_sql
    assert "source_chunk_id = %(chunk_id)s" in stale_sql
    assert "embedding_status = 'stale'" in stale_sql
