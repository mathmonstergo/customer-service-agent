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
    ADD COLUMN IF NOT EXISTS parse_progress JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE TABLE IF NOT EXISTS import_chunks (
    id TEXT PRIMARY KEY,
    file_id TEXT NOT NULL REFERENCES import_files(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
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
