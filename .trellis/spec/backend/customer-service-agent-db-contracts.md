# Customer Service Agent DB Contracts

> Project-specific contracts for the Python + PostgreSQL + pgvector knowledge-base backend.

## Scenario: Replacing Imported Chunks

### 1. Scope / Trigger

- Trigger: code modifies `ImportMixin.replace_import_chunks()` or any reparse path that replaces rows in `import_chunks`.
- Reason: platform assistant retrieval reads indexed document rows from `knowledge_chunks`; old document vectors can remain searchable if only `import_chunks` are replaced.

### 2. Signatures

- Python method: `ImportMixin.replace_import_chunks(file_id: str, chunks: list[dict[str, Any]]) -> list[dict[str, Any]]`
- Database tables:
  - `import_chunks.file_id`
  - `knowledge_chunks.source_type`
  - `knowledge_chunks.source_id`

### 3. Contracts

- Before inserting replacement chunks for an import file, delete existing `knowledge_chunks` rows where:
  - `source_type = 'document'`
  - `source_id = file_id`
- Delete old `import_chunks` for the same `file_id` in the same connection context.
- Insert replacement chunks after both cleanup steps.
- The platform assistant must never be able to retrieve document chunks from a previous parse of the same file.

### 4. Validation & Error Matrix

- Missing `file_id` is not accepted by callers; callers must pass a concrete import file id.
- Database errors must propagate so the connection context rolls back partial replacement work.
- Empty `chunks` is valid and means the file has no replacement chunks; old document knowledge must still be removed.

### 5. Good/Base/Bad Cases

- Good: reparse `imp_1`, delete `knowledge_chunks` for `source_type='document' AND source_id='imp_1'`, delete old `import_chunks`, insert new chunks.
- Base: reparse produces no chunks; delete old knowledge and old chunks, return an empty list.
- Bad: delete only `import_chunks`; the assistant may still retrieve old `knowledge_chunks` because disabled filtering uses left joins.

### 6. Tests Required

- Unit test against `Database.replace_import_chunks()` with a fake connection:
  - Asserts a `DELETE FROM knowledge_chunks` call exists.
  - Asserts the delete filters `source_type = 'document'` and `source_id = %(file_id)s`.
  - Asserts knowledge cleanup happens before deleting `import_chunks`.

### 7. Wrong vs Correct

#### Wrong

```python
with self.connect() as conn:
    conn.execute("DELETE FROM import_chunks WHERE file_id = %(file_id)s", {"file_id": file_id})
```

#### Correct

```python
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
```

## Scenario: Document Parent Chunks As Context Only

### 1. Scope / Trigger

- Trigger: code modifies `KnowledgeMixin._search_knowledge_sql()`, `KnowledgeMixin._search_knowledge_text_sql()`, `KnowledgeMixin._get_parent_context_chunks_sql()`, or any retrieval fusion that reads `knowledge_chunks`.
- Reason: document parent chunks are broad context containers. If parent and child chunks compete as equal direct candidates, retrieval can duplicate hits and inflate assistant context.

### 2. Signatures

- Python methods:
  - `KnowledgeMixin.search_knowledge(query_embedding, *, top_k, min_score, status="usable")`
  - `KnowledgeMixin.search_knowledge_text(query_text, *, top_k, query_terms=None, status="usable")`
  - `KnowledgeMixin.get_parent_context_chunks(child_ids, *, status="usable")`
- Database fields:
  - `knowledge_chunks.source_type`
  - `knowledge_chunks.chunk_level`
  - `knowledge_chunks.parent_chunk_id`
  - `knowledge_chunks.embedding_status`

### 3. Contracts

- Document child chunks drive direct vector and keyword recall.
- Direct vector retrieval must exclude document parent rows with:
  - `(kc.source_type <> 'document' OR kc.chunk_level <> 'parent')`
- Direct keyword retrieval must use the same exclusion.
- Parent rows may still have embeddings and `embedding_status = 'ready'`; embedding generation and UI summaries must not depend on direct recall eligibility.
- `_get_parent_context_chunks_sql()` must not include the direct-recall parent exclusion; it exists specifically to read parent chunks for child hits.
- File-level and chunk-level disable filters must still apply to both direct retrieval and parent context retrieval.

### 4. Validation & Error Matrix

- Document parent chunk in `knowledge_chunks` -> not returned by direct vector/keyword search.
- FAQ rows with `chunk_level = 'parent'` -> not excluded by the document-only condition unless future FAQ semantics define otherwise.
- Child hit with valid `parent_chunk_id` -> parent can be returned by `get_parent_context_chunks()`.
- Disabled import file or disabled import chunk -> both child direct hits and parent context rows are filtered out.

### 5. Good/Base/Bad Cases

- Good: query hits a document child; assistant receives child plus parent context through explicit backfill.
- Base: query hits a FAQ row; FAQ retrieval behavior is unchanged.
- Bad: direct SQL returns both document parent and child for the same section, causing duplicate evidence and larger prompts.
- Bad: direct-recall exclusion is copied into parent context SQL, preventing parent backfill.

### 6. Tests Required

- Unit tests in `tests/test_db.py` must assert:
  - `_search_knowledge_sql()` contains `(kc.source_type <> 'document' OR kc.chunk_level <> 'parent')`;
  - `_search_knowledge_text_sql()` contains the same condition;
  - `_get_parent_context_chunks_sql()` still reads `parent.chunk_level = 'parent'` and retains disable filters.
- Assistant retrieval tests should cover child hits expanding with parent context when relevant.

### 7. Wrong vs Correct

#### Wrong

```sql
WHERE COALESCE(fq.status, kc.status) = %(status)s
  AND kc.embedding_status = 'ready'
```

This lets document parent and child chunks compete in the same direct candidate list.

#### Correct

```sql
WHERE COALESCE(fq.status, kc.status) = %(status)s
  AND kc.embedding_status = 'ready'
  AND (kc.source_type <> 'document' OR kc.chunk_level <> 'parent')
```

Direct recall stays child-first for documents, while parent context remains available through explicit backfill.
