# Customer Service Agent Document Parser Contracts

> Project-specific contracts for MinerU payload normalization and document evidence retention.

## Scenario: MinerU Page Chrome And HTML Cleanup

### 1. Scope / Trigger

- Trigger: code modifies `extract_blocks_from_mineru_payload()`, `_blocks_from_content_list()`, `_extract_item_text()`, table extraction helpers, or import chunk source evidence derived from `ParsedBlock`.
- Reason: MinerU output may include page headers, footers, page numbers, sidebars, and HTML markup. These must not pollute searchable text, but real content evidence must remain available for document management and source inspection.

### 2. Signatures

- Python function: `extract_blocks_from_mineru_payload(payload: dict[str, Any], *, source_file: str, use_kb_packager: bool = False) -> list[ParsedBlock]`
- Python dataclass: `ParsedBlock(text, block_type, page_number, section_title, evidence, position_tag)`
- Import chunk fields derived later:
  - `source_text`
  - `page_start`
  - `page_end`
  - `source_offsets.pdf_positions`
  - `source_blocks[].evidence`

### 3. Contracts

- Raw MinerU `content_list` must skip page chrome block types: `header`, `footer`, `page_number`, `page_header`, `page_footer`, `page_aside_text`, `discarded`.
- Raw MinerU `content_list` must skip unsupported unknown block types instead of letting them become searchable text.
- Real content blocks must preserve `page_number`, `position_tag`, `bbox`-derived `pdf_positions`, `section_title`, `layout_type`, `layoutno`, and `doc_type_kwd` when available.
- HTML entities must be unescaped in searchable text.
- HTML tags must be stripped from searchable text; `<br>` and block/table endings should become line breaks.
- Literal non-HTML angle-bracket text such as `<退款规则>` must remain text, not be stripped as a tag.
- HTML table bodies should become readable row text such as `状态 | 处理`, while the original raw HTML remains in `evidence["table_html"]`.

### 4. Validation & Error Matrix

- Empty or fully filtered payload -> raise `MineruParseError("MinerU returned no parseable text")`.
- Page chrome block with text -> skip silently; this is expected parser noise, not a user-facing error.
- Real content block with invalid bbox -> keep the block and omit `position_tag`.
- Table block with raw HTML but no parseable rows -> fall back to sanitized text, keeping raw table HTML in evidence.

### 5. Good/Base/Bad Cases

- Good: `header`, `text`, `page_number`, `footer` on page 77 returns only the text block, with page 77 and bbox evidence preserved.
- Base: plain table text `状态 | 处理` stays plain text and keeps asset evidence.
- Bad: page footer text enters `source_text` or `embedding_text`, causing duplicate chunks across pages.
- Bad: raw `<td>` tags enter `source_text`.
- Bad: filtering `page_number` removes the real content block's `page_start/page_end`.

### 6. Tests Required

- Unit tests in `tests/test_document_parser.py` must assert:
  - page chrome and unknown raw block types are excluded from returned blocks;
  - content block page number and `source_offsets.pdf_positions` survive filtering;
  - HTML text is sanitized;
  - HTML table text is converted to row text;
  - raw table HTML is still present in block evidence.

### 7. Wrong vs Correct

#### Wrong

```python
if block_type == "page_number":
    return ""
return str(item.get("text") or "").strip()
```

This only skips one noise type and lets HTML/table markup and unknown page chrome enter searchable text.

#### Correct

```python
if _is_ignored_mineru_block_type(block_type):
    return ""
text = _sanitize_mineru_inline_text(raw_text)
```

Filtering is centralized and text cleanup preserves evidence separately from searchable text.

## Scenario: MinerU RAGFlow-Faithful Document Parsing Layer

### 1. Scope / Trigger

- Trigger: code modifies MinerU API integration, payload normalization, post-processing, `build_import_chunks_from_blocks()`, or any `qa`, `table`, `manual/title`, or `naive` routing for parsed MinerU blocks.
- Reason: this project stays deployment-light and MinerU API-first, but document parsing quality must remain accurate and efficient. "Lightweight" means deployment/dependency shape, not simplified parsing or chunker rules.

### 2. Signatures

- Python function under discussion: `build_import_chunks_from_blocks(file_id, blocks, *, chunk_token_num=None, delimiter="\n。；！？", ...) -> list[dict[str, Any]]`
- MinerU/RAGFlow reference files that must be checked before implementation:
  - `rag/app/qa.py`
  - `rag/app/table.py`
  - `rag/app/manual.py`
  - `rag/app/naive.py`
  - `rag/nlp/__init__.py`
- Output should remain existing `import_chunks` rows unless a separate schema decision is explicitly confirmed.

### 3. Contracts

- Do not implement a simplified "lightweight routing" or parser shortcut as a substitute for MinerU/RAGFlow behavior.
- "Lightweight" means local deployment/dependency shape is light, e.g. MinerU can be consumed via API; it does not reduce parsing, post-processing, or chunking correctness requirements.
- Before implementation, write a design that maps RAGFlow behavior to this project:
  - MinerU API/local-provider boundary;
  - payload discovery and normalization;
  - QA pair extraction and malformed-row handling;
  - table row/field handling and metadata retention;
  - manual/title hierarchy handling;
  - naive fallback and delimiter/token budget behavior;
  - parent-child indexing implications;
  - source evidence retention.
- Every route must preserve existing evidence fields such as `page_number`, `section_title`, `position_tag`, `pdf_positions`, `table_html`, and asset paths.
- Chunking changes must never bypass import review or directly write searchable knowledge.

### 4. Validation & Error Matrix

- Unclear file/chunker selection strategy -> stop and confirm design; do not guess in code.
- RAGFlow behavior differs from current project model -> document "copy / adapt / not applicable" before implementation.
- RAGFlow requires heavy services or storage engines -> adapt the behavior, not the dependency.
- MinerU API output lacks fields RAGFlow expects -> define evidence-preserving fallback and tests.

### 5. Good/Base/Bad Cases

- Good: implementation test cases are derived from RAGFlow `qa/table/manual/naive` behavior.
- Good: MinerU remains API-first while parsing and chunking rules remain faithful to MinerU/RAGFlow where applicable.
- Base: ordinary paragraphs still use RAGFlow-style `naive`.
- Bad: implementing a new provider registry or local RAGFlow task executor for this lightweight project.
- Bad: replacing MinerU/RAGFlow parser or chunker behavior with a few ad hoc heuristics.
- Bad: dropping `table_html` or page evidence while transforming chunks.

### 6. Tests Required

- Unit tests in `tests/test_document_parser.py` must assert:
  - QA cases match the chosen RAGFlow-derived behavior, including malformed rows;
  - table cases match RAGFlow-derived row/field behavior;
  - manual/title cases match RAGFlow-derived hierarchy behavior;
  - existing naive behavior and evidence preservation still pass.
- Tests must include both "desired RAGFlow behavior" and "project evidence retention" assertions.

### 7. Wrong vs Correct

#### Wrong

```python
if table_like:
    return simple_row_chunks(blocks)
```

This invents a shortcut without proving it matches RAGFlow behavior.

#### Correct

```python
reference = "rag/app/table.py + rag/nlp/tokenize_table"
# Implement only after mapping RAGFlow behavior to import_chunks and tests.
```

The implementation remains project-owned, but the behavior is explicitly derived from RAGFlow.

## Scenario: Document Chunker Type Configuration

### 1. Scope / Trigger

- Trigger: code modifies document import settings, `Settings.from_env()`, `AdminApp._build_document_import_chunks()`, or `build_import_chunks_from_blocks(..., chunker_type=...)`.
- Reason: the project now supports multiple RAGFlow-derived chunker behaviors without introducing RAGFlow runtime services. The selected route must be explicit and testable, not an untracked heuristic.

### 2. Signatures

- Environment key: `DOCUMENT_CHUNKER_TYPE`
- Settings field: `Settings.document_chunker_type: str`
- Admin payload/snapshot field: `document_chunker_type`
- Python function:
  - `build_import_chunks_from_blocks(file_id, blocks, *, chunker_type="naive", ...) -> list[dict[str, Any]]`
- Supported values:
  - `naive`
  - `manual`
  - `qa`
  - `table`

### 3. Contracts

- Default chunker type is `naive`.
- `DOCUMENT_CHUNKER_TYPE` must be normalized to lowercase.
- Unknown chunker types must raise `SettingsError` during settings load or `MineruParseError` at parser entry.
- Admin settings must preserve `document_chunker_type` when the settings payload omits it.
- `AdminApp._build_document_import_chunks()` must pass `document_chunker_type` into `build_import_chunks_from_blocks()`.
- Non-naive chunkers must record their route in `import_chunks.source_offsets["chunker"]["type"]`.
- Chunker outputs must still be import review rows; no route may directly write official FAQ or searchable knowledge.

### 4. Validation & Error Matrix

- Missing env/admin field -> use current setting or default `naive`.
- `DOCUMENT_CHUNKER_TYPE=lightweight` -> raise `SettingsError("DOCUMENT_CHUNKER_TYPE must be one of...")`.
- `build_import_chunks_from_blocks(..., chunker_type="lightweight")` -> raise `MineruParseError("Unsupported chunker_type...")`.
- `table` chunker with no data rows -> raise `MineruParseError("table chunker found no table rows")`.
- `qa` chunker with no Q/A pairs -> raise `MineruParseError("qa chunker found no question-answer pairs")`.
- `manual` chunker with no section text -> raise `MineruParseError("manual chunker found no section chunks")`.

### 5. Good/Base/Bad Cases

- Good: `DOCUMENT_CHUNKER_TYPE=table` produces one import chunk per table row and keeps sheet/header/row evidence.
- Good: `DOCUMENT_CHUNKER_TYPE=qa` appends malformed txt/csv rows to the current answer after a valid question exists.
- Good: `DOCUMENT_CHUNKER_TYPE=manual` groups consecutive parsed blocks by section path and keeps page evidence.
- Base: omitted `DOCUMENT_CHUNKER_TYPE` keeps existing naive behavior.
- Bad: adding an `auto` or `lightweight` route that guesses behavior without RAGFlow mapping and tests.
- Bad: storing chunker type only in transient code variables, leaving import chunks unauditable.

### 6. Tests Required

- `tests/test_config.py`:
  - default settings expose `document_chunker_type == "naive"`;
  - configured settings parse `DOCUMENT_CHUNKER_TYPE`;
  - unknown types raise `SettingsError`.
- `tests/test_admin_server.py`:
  - settings snapshot and tenant persistence include `document_chunker_type`;
  - omitted settings payload preserves existing chunker type;
  - `_build_document_import_chunks()` passes `chunker_type` into the parser.
- `tests/test_document_parser.py`:
  - `table` creates one chunk per row with row/header evidence;
  - `qa` appends malformed rows to the current answer;
  - `manual` groups by section path and records chunker metadata.

### 7. Wrong vs Correct

#### Wrong

```python
chunker_type = guess_from_text(blocks)
chunks = build_import_chunks_from_blocks(file_id, blocks)
```

This hides the route, cannot be audited in import chunks, and can drift away from RAGFlow behavior.

#### Correct

```python
chunks = build_import_chunks_from_blocks(
    file_id,
    blocks,
    chunker_type=settings.document_chunker_type,
)
```

The route is explicit, validated, and persisted in chunk metadata for non-naive chunkers.

## Scenario: Document File-Level Chunker Selection

### 1. Scope / Trigger

- Trigger: code modifies `import_files.chunker_type`, document parse job payloads, document management UI chunker selection, or `AdminApp._finish_mineru_parse_job()`.
- Reason: global `DOCUMENT_CHUNKER_TYPE` is only a default. Mixed imports need each file to preserve the selected RAGFlow-derived post-parser route so parsing is auditable and repeatable.

### 2. Signatures

- Database field: `import_files.chunker_type TEXT NOT NULL DEFAULT 'naive'`
- Python method:
  - `AdminApp.create_import_file(filename, content, *, auto_parse=True, chunker_type=None)`
  - `AdminApp.start_import_parse_job(file_id, payload)`
  - `AdminApp.reparse_import_file(file_id, payload)`
  - `AdminApp._build_document_import_chunks(file_id, blocks, *, chunker_type=None)`
- HTTP payload:
  - `POST /api/import/files/<id>/parse-jobs`
  - optional JSON field: `chunker_type`
- Frontend type:
  - `ImportFile.chunker_type: string`

### 3. Contracts

- New import file rows must persist a `chunker_type`; omitted values use `settings.document_chunker_type`, then `naive`.
- Parse job payload may override the file's `chunker_type`; the backend must validate and persist it before MinerU job progress is saved.
- MinerU finish/reparse paths must pass the file record's `chunker_type` into `build_import_chunks_from_blocks()`.
- The global `DOCUMENT_CHUNKER_TYPE` remains only the default/fallback, not the final source of truth for existing file records.
- Document management UI must display the current file chunker and submit the selected value when starting parse.
- Markdown chat imports do not use document chunkers; their message chunking remains `parse_mode` / `chunk_days` based.

### 4. Validation & Error Matrix

- Missing `chunker_type` in payload -> keep the file's stored value; if absent on legacy rows, fallback to settings/default.
- `chunker_type` in `{naive, manual, qa, table}` -> persist on `import_files` and use for MinerU chunk building.
- Unknown values such as `auto`, `lightweight`, or `ragflow` -> raise `AdminValidationError("chunker_type must be one of...")`.
- Existing DB without the column -> `sql/001_init.sql` must add `chunker_type TEXT NOT NULL DEFAULT 'naive'`.
- File status polling completion -> must not silently switch back to global settings.

### 5. Good/Base/Bad Cases

- Good: PDF manual row has `chunker_type='manual'`; MinerU completion builds manual chunks even when global setting is `naive`.
- Good: FAQ-like source row has `chunker_type='qa'`; parse job payload persists `qa` before background polling.
- Base: old row lacks explicit application-provided value; migration/default makes it `naive`.
- Bad: UI only sends parser name and backend always reads `settings.document_chunker_type`.
- Bad: chunker choice is stored only in `import_chunks.source_offsets` after parsing, leaving the file list/audit trail unable to show which route will be used on reparse.

### 6. Tests Required

- `tests/test_db.py` must assert `sql/001_init.sql` adds `import_files.chunker_type`.
- `tests/test_admin_server.py` must assert:
  - file creation writes the default chunker;
  - parse job payload persists `chunker_type`;
  - unknown chunker payloads are rejected;
  - MinerU finish uses the file-level chunker instead of global settings.
- Frontend changes must pass TypeScript build and at least lint the modified files.

### 7. Wrong vs Correct

#### Wrong

```python
chunk_rows = self._build_document_import_chunks(record["id"], blocks)
```

This lets the builder fall back to global settings, so a file-level user choice is ignored when the long MinerU task finishes.

#### Correct

```python
chunk_rows = self._build_document_import_chunks(
    record["id"],
    blocks,
    chunker_type=self._document_chunker_type_from_record(record),
)
```

The route is persisted on the import file and then explicitly passed into the RAGFlow-derived post-processing layer.
