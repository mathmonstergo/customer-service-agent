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
