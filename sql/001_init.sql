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
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

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
    status TEXT NOT NULL DEFAULT 'pending',
    saved_faq_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS import_files_status_idx
    ON import_files (status, updated_at DESC);

CREATE INDEX IF NOT EXISTS import_chunks_file_idx
    ON import_chunks (file_id, chunk_index);

CREATE INDEX IF NOT EXISTS import_candidates_chunk_idx
    ON import_candidates (chunk_id, status);
