CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS faq_documents (
    id TEXT PRIMARY KEY,
    doc_type TEXT NOT NULL,
    source_file TEXT,
    source_group TEXT,
    source_date TEXT,
    category TEXT,
    question TEXT NOT NULL,
    question_variants JSONB NOT NULL DEFAULT '[]'::jsonb,
    answer TEXT NOT NULL,
    tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
    confidence TEXT NOT NULL,
    status TEXT NOT NULL,
    sensitivity TEXT,
    embedding_text TEXT NOT NULL,
    embedding vector(1024),
    embedding_status TEXT NOT NULL DEFAULT 'pending',
    embedding_model TEXT,
    embedding_dimensions INTEGER,
    embedding_updated_at TIMESTAMPTZ,
    embedding_error TEXT,
    content_hash TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE faq_documents
    ALTER COLUMN embedding DROP NOT NULL;

ALTER TABLE faq_documents
    ADD COLUMN IF NOT EXISTS embedding_status TEXT NOT NULL DEFAULT 'pending';

ALTER TABLE faq_documents
    ADD COLUMN IF NOT EXISTS embedding_model TEXT;

ALTER TABLE faq_documents
    ADD COLUMN IF NOT EXISTS embedding_dimensions INTEGER;

ALTER TABLE faq_documents
    ADD COLUMN IF NOT EXISTS embedding_updated_at TIMESTAMPTZ;

ALTER TABLE faq_documents
    ADD COLUMN IF NOT EXISTS embedding_error TEXT;

ALTER TABLE faq_documents
    ADD COLUMN IF NOT EXISTS content_hash TEXT;

-- FAQ 用 status 表达禁用(usable/needs_review/disabled)，不再要正交的 is_disabled 列；历史库若已加则移除。
ALTER TABLE faq_documents
    DROP COLUMN IF EXISTS is_disabled;

-- 历史遗留的非常规状态(如 product_request / draft / archived)归一到三态：非 usable/disabled 的都视作待复核。
UPDATE faq_documents
SET status = 'needs_review'
WHERE status NOT IN ('usable', 'needs_review', 'disabled');

UPDATE faq_documents
SET embedding_status = 'ready'
WHERE embedding IS NOT NULL
  AND embedding_status = 'pending';

CREATE INDEX IF NOT EXISTS faq_documents_status_confidence_idx
    ON faq_documents (status, confidence);

CREATE INDEX IF NOT EXISTS faq_documents_embedding_status_idx
    ON faq_documents (embedding_status);

CREATE INDEX IF NOT EXISTS faq_documents_category_idx
    ON faq_documents (category);

CREATE INDEX IF NOT EXISTS faq_documents_embedding_idx
    ON faq_documents USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    source_chunk_id TEXT,
    parent_chunk_id TEXT,
    chunk_level TEXT NOT NULL DEFAULT 'chunk',
    source_title TEXT,
    chunk_index INTEGER NOT NULL DEFAULT 0,
    section_path JSONB NOT NULL DEFAULT '[]'::jsonb,
    page_start INTEGER,
    page_end INTEGER,
    block_type TEXT,
    source_offsets JSONB NOT NULL DEFAULT '{}'::jsonb,
    content TEXT NOT NULL,
    embedding_text TEXT NOT NULL,
    search_text TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    confidence TEXT,
    status TEXT NOT NULL DEFAULT 'needs_review',
    embedding vector(1024),
    embedding_status TEXT NOT NULL DEFAULT 'pending',
    embedding_model TEXT,
    embedding_dimensions INTEGER,
    embedding_updated_at TIMESTAMPTZ,
    embedding_error TEXT,
    content_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source_type, source_id, chunk_index)
);

ALTER TABLE knowledge_chunks
    ADD COLUMN IF NOT EXISTS parent_chunk_id TEXT,
    ADD COLUMN IF NOT EXISTS chunk_level TEXT NOT NULL DEFAULT 'chunk',
    ADD COLUMN IF NOT EXISTS section_path JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS page_start INTEGER,
    ADD COLUMN IF NOT EXISTS page_end INTEGER,
    ADD COLUMN IF NOT EXISTS block_type TEXT,
    ADD COLUMN IF NOT EXISTS source_offsets JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS knowledge_chunks_source_idx
    ON knowledge_chunks (source_type, source_id);

CREATE INDEX IF NOT EXISTS knowledge_chunks_parent_idx
    ON knowledge_chunks (parent_chunk_id);

CREATE INDEX IF NOT EXISTS knowledge_chunks_status_source_idx
    ON knowledge_chunks (status, source_type);

CREATE INDEX IF NOT EXISTS knowledge_chunks_embedding_status_idx
    ON knowledge_chunks (embedding_status);

CREATE INDEX IF NOT EXISTS knowledge_chunks_embedding_idx
    ON knowledge_chunks USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS knowledge_chunks_metadata_idx
    ON knowledge_chunks USING gin (metadata);

CREATE INDEX IF NOT EXISTS knowledge_chunks_section_path_idx
    ON knowledge_chunks USING gin (section_path);

CREATE INDEX IF NOT EXISTS knowledge_chunks_search_idx
    ON knowledge_chunks USING gin (to_tsvector('simple', search_text));

CREATE TABLE IF NOT EXISTS import_files (
    id TEXT PRIMARY KEY,
    original_name TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    file_type TEXT NOT NULL,
    parser TEXT NOT NULL,
    status TEXT NOT NULL,
    message_count INTEGER NOT NULL DEFAULT 0,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    candidate_count INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    parse_batch_id TEXT,
    parse_file_name TEXT,
    parse_progress JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE import_files
    ADD COLUMN IF NOT EXISTS parse_batch_id TEXT,
    ADD COLUMN IF NOT EXISTS parse_file_name TEXT,
    ADD COLUMN IF NOT EXISTS parse_progress JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS is_disabled BOOLEAN NOT NULL DEFAULT false;

CREATE TABLE IF NOT EXISTS import_chunks (
    id TEXT PRIMARY KEY,
    file_id TEXT NOT NULL REFERENCES import_files(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    section_path JSONB NOT NULL DEFAULT '[]'::jsonb,
    page_start INTEGER,
    page_end INTEGER,
    block_type TEXT,
    source_offsets JSONB NOT NULL DEFAULT '{}'::jsonb,
    source_blocks JSONB NOT NULL DEFAULT '[]'::jsonb,
    children_delimiter TEXT NOT NULL DEFAULT '',
    start_at TIMESTAMPTZ,
    end_at TIMESTAMPTZ,
    message_count INTEGER NOT NULL DEFAULT 0,
    keywords JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    candidate_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE import_chunks
    DROP COLUMN IF EXISTS parent_chunk_id,
    DROP COLUMN IF EXISTS chunk_level,
    ADD COLUMN IF NOT EXISTS section_path JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS page_start INTEGER,
    ADD COLUMN IF NOT EXISTS page_end INTEGER,
    ADD COLUMN IF NOT EXISTS block_type TEXT,
    ADD COLUMN IF NOT EXISTS source_offsets JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS source_blocks JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS children_delimiter TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS is_disabled BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS questions JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS questions_status TEXT NOT NULL DEFAULT 'pending',
    ADD COLUMN IF NOT EXISTS questions_model TEXT,
    ADD COLUMN IF NOT EXISTS questions_updated_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS questions_error TEXT;

CREATE TABLE IF NOT EXISTS import_candidates (
    id TEXT PRIMARY KEY,
    file_id TEXT NOT NULL REFERENCES import_files(id) ON DELETE CASCADE,
    chunk_id TEXT NOT NULL REFERENCES import_chunks(id) ON DELETE CASCADE,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    similar_questions JSONB NOT NULL DEFAULT '[]'::jsonb,
    category TEXT,
    tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    confidence TEXT NOT NULL DEFAULT 'medium',
    internal_note TEXT,
    source_excerpt TEXT NOT NULL,
    duplicate_level TEXT NOT NULL DEFAULT 'none',
    duplicate_score DOUBLE PRECISION NOT NULL DEFAULT 0,
    duplicate_target_id TEXT,
    duplicate_reason TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    saved_faq_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE import_candidates
    ADD COLUMN IF NOT EXISTS duplicate_level TEXT NOT NULL DEFAULT 'none',
    ADD COLUMN IF NOT EXISTS duplicate_score DOUBLE PRECISION NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS duplicate_target_id TEXT,
    ADD COLUMN IF NOT EXISTS duplicate_reason TEXT;

CREATE TABLE IF NOT EXISTS import_generation_jobs (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'queued',
    total_count INTEGER NOT NULL DEFAULT 0,
    queued_count INTEGER NOT NULL DEFAULT 0,
    processing_count INTEGER NOT NULL DEFAULT 0,
    generated_count INTEGER NOT NULL DEFAULT 0,
    skipped_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS import_generation_job_items (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES import_generation_jobs(id) ON DELETE CASCADE,
    chunk_id TEXT NOT NULL REFERENCES import_chunks(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'queued',
    reason TEXT,
    candidate_count INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (job_id, chunk_id)
);

CREATE INDEX IF NOT EXISTS import_files_status_idx
    ON import_files (status, updated_at DESC);

CREATE INDEX IF NOT EXISTS import_chunks_file_idx
    ON import_chunks (file_id, chunk_index);

CREATE INDEX IF NOT EXISTS import_candidates_chunk_idx
    ON import_candidates (chunk_id, status);

CREATE INDEX IF NOT EXISTS import_generation_job_items_chunk_status_idx
    ON import_generation_job_items (chunk_id, status);

CREATE TABLE IF NOT EXISTS retrieval_eval_cases (
    id TEXT PRIMARY KEY,
    question TEXT NOT NULL,
    intent TEXT,
    expected_source_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    expected_chunk_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    note TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS retrieval_eval_runs (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES retrieval_eval_cases(id) ON DELETE CASCADE,
    strategy TEXT NOT NULL,
    retrieved_items JSONB NOT NULL DEFAULT '[]'::jsonb,
    metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
    analysis JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS retrieval_eval_cases_status_idx
    ON retrieval_eval_cases (status, updated_at DESC);

CREATE INDEX IF NOT EXISTS retrieval_eval_runs_case_idx
    ON retrieval_eval_runs (case_id, created_at DESC);

CREATE TABLE IF NOT EXISTS retrieval_aliases (
    id TEXT PRIMARY KEY,
    canonical TEXT NOT NULL,
    aliases JSONB NOT NULL DEFAULT '[]'::jsonb,
    tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS retrieval_aliases_status_idx
    ON retrieval_aliases (status, updated_at DESC);

CREATE TABLE IF NOT EXISTS query_analytics_events (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    query TEXT NOT NULL,
    intent TEXT,
    retrieved_chunk_ids TEXT[] NOT NULL DEFAULT '{}',
    top_score DOUBLE PRECISION,
    hit_count INT NOT NULL DEFAULT 0,
    rerank_used BOOLEAN NOT NULL DEFAULT false,
    latency_ms INT,
    requester_type TEXT NOT NULL DEFAULT 'unknown',
    requester_id TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_query_analytics_created_at
    ON query_analytics_events (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_query_analytics_hit_zero
    ON query_analytics_events (created_at DESC)
    WHERE hit_count = 0;

CREATE TABLE IF NOT EXISTS query_analytics_cluster_summaries (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    period_start TIMESTAMPTZ NOT NULL,
    period_end TIMESTAMPTZ NOT NULL,
    cluster_label TEXT NOT NULL,
    suggested_content TEXT,
    event_count INT NOT NULL,
    sample_queries TEXT[] NOT NULL DEFAULT '{}'
);
