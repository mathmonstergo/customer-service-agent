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

## Scenario: Retrieval Evaluation Candidate Labeling Payload

### 1. Scope / Trigger

- Trigger: code modifies `AdminApp.run_retrieval_eval_case()`, `retrieval_eval_item_payload()`, frontend evaluation candidate rendering, or expected hit labeling behavior.
- Reason: evaluation users must be able to label expected hits from readable candidates. Raw `source_id` / `chunk_id` alone is not enough because document drawer display numbers such as `#1` are UI-relative and do not equal knowledge chunk ids.

### 2. Signatures

- Python function: `retrieval_eval_item_payload(candidate: Any) -> dict[str, Any]`
- Admin API:
  - `GET /api/retrieval/eval-cases`
  - `POST /api/retrieval/eval-cases`
  - `POST /api/retrieval/eval-cases/{case_id}/run`
- Frontend types:
  - `RetrievalEvalItem`
  - `RetrievalEvalCase.expected_source_ids`
  - `RetrievalEvalCase.expected_chunk_ids`

### 3. Contracts

- Every retrieved candidate stored in `retrieval_eval_runs.retrieved_items` must keep machine ids:
  - `id` = knowledge chunk id used for chunk-level expected hit matching.
  - `source_id` = FAQ id or import file id used for source-level expected hit matching.
  - `source_type` = `faq`, `document`, or other known source class.
- Candidate payloads should also expose readable/provenance fields when available:
  - `source_title`
  - `source_chunk_id`
  - `parent_chunk_id`
  - `chunk_level`
  - `section_path`
  - `page_start`
  - `page_end`
  - `block_type`
  - `content`
  - `metadata`
- Frontend labeling should prefer "run first, label from candidate" over manual id entry.
- One-click labeling should use one evaluation granularity at a time:
  - Source labeling writes `expected_source_ids` and clears `expected_chunk_ids`.
  - Chunk labeling writes `expected_chunk_ids` and clears `expected_source_ids`.
- Manual id entry may remain as an advanced path, but it must not be the primary workflow.

### 4. Validation & Error Matrix

- Candidate missing readable fields -> UI falls back to ids, but backend must still include ids.
- Candidate missing `source_id` -> source-level label action must not add an empty id.
- Candidate missing `id` -> chunk-level label action must not add an empty id.
- Existing source-level expectation + user labels chunk -> source expectations are cleared to avoid hidden priority confusion.
- Existing chunk-level expectation + user labels source -> chunk expectations are cleared for the same reason.

### 5. Good/Base/Bad Cases

- Good: user runs an eval case, sees document title, page range, section path, excerpt, and clicks "expected chunk"; the case stores the knowledge chunk id.
- Good: user wants broad document/FAQ acceptance, clicks "expected source"; the case stores the FAQ/import file id.
- Base: older run rows without readable fields still render ids and scores.
- Bad: UI asks the user to type `kc_doc_child_...` without showing how to find it.
- Bad: UI displays document drawer `#3` as if it were the chunk id used by evaluation metrics.
- Bad: source and chunk expectations are both set by one-click UI while metrics silently use only chunk ids.

### 6. Tests Required

- Unit test for `retrieval_eval_item_payload()` asserting readable fields are emitted.
- Admin run test should continue to assert metrics are recorded and candidate ids are present.
- Frontend lint/build must cover changed `RetrievalEvalItem` type and candidate labeling UI.
- Manual UI verification should cover:
  - run eval case;
  - mark a candidate as expected source;
  - mark a candidate as expected chunk;
  - confirm labels update without hand-copying ids.

### 7. Wrong vs Correct

#### Wrong

```json
{
  "id": "kc_doc_child_1",
  "source_id": "imp_1",
  "source_type": "document"
}
```

This is technically enough for metrics but not enough for a human to know which document block is being labeled.

#### Correct

```json
{
  "id": "kc_doc_child_1",
  "source_id": "imp_1",
  "source_type": "document",
  "source_title": "售后手册.pdf",
  "source_chunk_id": "chunk_1",
  "chunk_level": "child",
  "section_path": ["售后", "报告导出"],
  "page_start": 3,
  "page_end": 4,
  "content": "报告导出失败时，先检查账号权限和网络状态。"
}
```

The UI can now let users label the expected source/chunk from a readable candidate row instead of asking them to discover internal ids.

## Scenario: Knowledge Graph Review Projection and Explicit Retrieval

### 1. Scope / Trigger

- Trigger: code modifies KG extraction parsing, `kg_entities`, `kg_relations`, `kg_evidence`, KG projection into `knowledge_chunks`, `KnowledgeGraphMixin`, or retrieval/evaluation paths that can read KG chunks.
- Reason: KG facts are model-generated and may be wrong. They must not become retrievable until reviewed, and they must not affect the default assistant path before evaluation proves value.

### 2. Signatures

- Python parser: `parse_kg_extraction_response(payload, *, source) -> dict[str, list[dict[str, Any]]]`
- Python DB methods:
  - `Database.create_kg_extraction_job(row) -> dict[str, Any]`
  - `Database.update_kg_extraction_job(job_id, **fields) -> dict[str, Any]`
  - `Database.save_kg_extraction_candidates(extraction) -> dict[str, int]`
  - `Database.confirm_kg_entity(entity_id) -> dict[str, Any]`
  - `Database.confirm_kg_relation(relation_id) -> dict[str, Any]`
  - `Database.list_kg_entities(status=None, entity_type=None, limit=50, offset=0) -> dict[str, Any]`
  - `Database.list_kg_relations(status=None, relation_type=None, limit=50, offset=0) -> dict[str, Any]`
  - `Database.set_kg_entity_status(entity_id, status) -> dict[str, Any]`
  - `Database.set_kg_relation_status(relation_id, status) -> dict[str, Any]`
  - `Database.search_kg_knowledge_text(query_text, *, top_k, query_terms=None, status="usable")`
  - `Database.get_kg_subgraph(center_entity_id, hops=1, entity_types=None, relation_types=None, status="usable", limit=80)`
- Admin API:
  - `POST /api/kg/extraction-jobs` with JSON fields `source_type` (`faq` or `document_chunk`) and `source_id`.
  - `GET /api/kg/entities?status=<status>&entity_type=<type>&limit=50&offset=0`
  - `GET /api/kg/relations?status=<status>&relation_type=<type>&limit=50&offset=0`
  - `POST /api/kg/entities/{entity_id}/confirm`
  - `POST /api/kg/entities/{entity_id}/status` with JSON field `status`.
  - `POST /api/kg/relations/{relation_id}/confirm`
  - `POST /api/kg/relations/{relation_id}/status` with JSON field `status`.
  - `POST /api/retrieval/eval-cases/{case_id}/run` with optional JSON field `use_kg`.
  - `GET /api/kg/subgraph?center_entity_id=<id>&hops=1&entity_type=<csv>&relation_type=<csv>&status=usable&limit=80`
- Database tables:
  - `kg_extraction_jobs`
  - `kg_entities`
  - `kg_relations`
  - `kg_evidence`
  - projected `knowledge_chunks.source_type IN ('kg_entity', 'kg_relation')`

### 3. Contracts

- KG entity types must be one of:
  - `product_platform_module`
  - `feature_ui_action`
  - `error_symptom`
  - `process_task_object`
  - `role_permission_channel`
  - `condition_policy`
- KG relation types must be one of:
  - `belongs_to`
  - `requires`
  - `causes`
  - `resolves_by`
  - `blocked_by`
  - `available_for`
  - `escalate_when`
- Parsed model output defaults to `status = 'needs_review'`.
- `POST /api/kg/extraction-jobs` first records a job as `queued`, then updates `processing`, then `completed` or `failed`.
- First extraction scope only supports one source per job:
  - `source_type = 'faq'`, `source_id = faq_documents.id`, and the FAQ must be `usable`;
  - `source_type = 'document_chunk'`, `source_id = import_chunks.id`, and the chunk must not be disabled.
- A failed model call or parser validation error must update the job to `failed` with a bounded `error` string.
- `kg_evidence` must point to exactly one of `entity_id` or `relation_id`.
- Every KG candidate must include evidence with `source_type`, `source_id`, optional `source_chunk_id`, and non-empty `excerpt`.
- Confirmed KG entities/relations may be projected to `knowledge_chunks` using `source_type = 'kg_entity'` or `source_type = 'kg_relation'`.
- Review list APIs must include evidence arrays so UI can show source excerpt/title/page without extra per-row calls.
- Confirm APIs must set KG status to `usable` and create/update the corresponding `knowledge_chunks` projection.
- Status APIs must only accept `needs_review`, `usable`, or `disabled`; changing status must also update the matching KG projection row status if it exists.
- Default `Database.search_knowledge()` and `Database.search_knowledge_text()` must exclude `kg_entity` and `kg_relation`.
- KG retrieval is allowed only through explicit debug/evaluation paths such as `use_kg=true`.

### 4. Validation & Error Matrix

- Missing entity name/type -> `KnowledgeGraphExtractionError`.
- Entity or relation type outside fixed enum -> `KnowledgeGraphExtractionError`.
- Missing evidence or missing evidence excerpt -> `KnowledgeGraphExtractionError`.
- `POST /api/kg/extraction-jobs` with unsupported `source_type` -> `AdminValidationError`.
- `POST /api/kg/extraction-jobs` with missing `source_id` -> `AdminValidationError`.
- KG extraction from non-usable FAQ -> `failed` job or `AdminValidationError` before candidates are saved.
- KG extraction from disabled/empty document chunk -> `failed` job or `AdminValidationError` before candidates are saved.
- Missing `center_entity_id` for subgraph API -> `AdminValidationError`.
- `POST /api/kg/*/{id}/status` with unsupported status -> `AdminValidationError`.
- `use_kg` omitted or false -> evaluation run must not call `search_kg_knowledge_text`.
- KG row with `status != 'usable'` -> not returned by KG retrieval or subgraph query.

### 5. Good/Base/Bad Cases

- Good: model extracts an entity and relation from a document chunk; rows enter KG tables as `needs_review`; user confirms the entity; a `kg_entity` chunk is created with `embedding_status = 'pending'`.
- Good: review UI calls `GET /api/kg/entities?status=needs_review`; response rows include evidence excerpts and source ids.
- Good: user disables a bad relation; `kg_relations.status` and existing `kg_relation` projection both become `disabled`.
- Good: `POST /api/kg/extraction-jobs {"source_type":"faq","source_id":"faq_1"}` reads the usable FAQ, calls the Chat model, saves candidates, and returns a `completed` job with counts.
- Good: invalid model JSON or enum drift returns a `failed` job with `error`, leaving no confirmed KG projection.
- Good: evaluation run with `use_kg=true` includes KG candidates and records strategy `retrieval_hybrid_v1_kg_debug`.
- Base: evaluation run without `use_kg` behaves like normal hybrid retrieval and records strategy `retrieval_hybrid_v1`.
- Bad: KG projection appears in default assistant search results before evaluation explicitly enables KG.
- Bad: model invents `entity_type = "random_type"` and the parser silently stores it.

### 6. Tests Required

- Parser tests must assert:
  - valid output defaults to `needs_review`;
  - evidence provenance is preserved;
  - unknown entity/relation types are rejected;
  - missing evidence is rejected.
- DB tests must assert:
  - `kg_extraction_jobs` schema includes source, status, model, error, and count fields;
  - `create_kg_extraction_job()` writes a queued source record;
  - `update_kg_extraction_job()` writes status/count/error fields;
  - schema contains `kg_entities`, `kg_relations`, `kg_evidence`, status fields, and indexes;
  - `save_kg_extraction_candidates()` writes entities, relations, and evidence;
  - default `search_knowledge*` SQL excludes `kg_entity`/`kg_relation`;
  - `search_kg_knowledge_text()` only reads `kg_entity`/`kg_relation`;
  - confirming a KG entity projects a pending `knowledge_chunks` row;
  - confirming a KG relation projects a pending `knowledge_chunks` row with head/tail entity IDs.
  - list entity/relation SQL aggregates evidence and supports status/type filters;
  - status update methods synchronize KG table status and KG projection chunk status.
- Admin tests must assert:
  - entity/relation list methods pass status/type/pagination filters to DB;
  - confirm methods delegate to DB and return item wrappers;
  - status methods validate allowed statuses and delegate to DB;
  - FAQ KG extraction creates a job, calls the model, saves candidates, and completes with counts;
  - document chunk KG extraction preserves file/chunk provenance;
  - invalid model output marks the job `failed`;
  - `use_kg=true` calls KG retrieval and uses KG debug strategy;
  - default eval runs do not require KG DB methods;
  - subgraph API passes filters and limits to DB.

### 7. Wrong vs Correct

#### Wrong

```python
fused = fuse_retrieval_candidates(
    vector_docs=vector_docs,
    keyword_docs=keyword_docs + database.search_kg_knowledge_text(query, top_k=top_k),
    top_k=top_k,
)
```

This makes KG affect normal retrieval without an explicit switch.

#### Correct

```python
kg_docs = []
if payload.get("use_kg") is True:
    kg_docs = database.search_kg_knowledge_text(query, top_k=candidate_limit, query_terms=query_terms)

fused = fuse_retrieval_candidates(
    vector_docs=vector_docs,
    keyword_docs=keyword_docs,
    kg_docs=kg_docs if payload.get("use_kg") is True else None,
    top_k=top_k,
)
```

The default assistant and evaluation path stays unchanged; KG participates only in explicit debug/evaluation runs.
