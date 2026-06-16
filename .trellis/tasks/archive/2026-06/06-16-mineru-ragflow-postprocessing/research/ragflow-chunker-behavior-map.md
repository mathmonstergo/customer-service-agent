# RAGFlow Chunker Behavior Map

## Source

* Repository: `/home/adam/projects/ragflow`
* Local tag set includes `v0.26.0`; current checkout is detached and has an unrelated dirty `docker/.env`.
* Files inspected:
  * `rag/svr/task_executor.py`
  * `rag/app/qa.py`
  * `rag/app/table.py`
  * `rag/app/manual.py`
  * `rag/app/naive.py`
  * `rag/nlp/__init__.py`
  * `rag/nlp/search.py`

## Router Model

RAGFlow routes by `parser_id`, not by a lightweight guess:

* `naive` handles general PDF/DOCX/XLSX/CSV/TXT/Markdown/HTML/EPUB/JSON through parser-specific section extraction, then generic merge/tokenization.
* `manual` handles manual-style PDF/DOCX with title/outline hierarchy and media/table context.
* `qa` handles explicit Q&A sources and Q&A-structured PDF/DOCX/Markdown.
* `table` handles row-oriented structured data.

Project implication: this project should support explicit chunker intent plus file-type defaults. Assisted auto-detection can recommend a chunker, but it should not replace the chosen route or hide the route in metadata.

## QA Chunker

### Inputs

* `.xlsx/.xls`: every row is scanned left-to-right; first non-empty cell is question, second non-empty cell is answer. No header is required.
* `.txt`: delimiter is chosen by comparing two-column comma vs tab lines. Malformed lines before any question are recorded as failures; malformed lines after a question append to the current answer.
* `.csv`: uses `csv.reader`; delimiter is tab if any tab exists, otherwise comma. Malformed rows follow the same append/fail behavior as txt.
* `.md/.markdown/.mdx`: Markdown headings form a question stack; non-heading content becomes answer body. Code fences disable heading recognition.
* `.pdf`: layout boxes are scanned for question bullet patterns; following text and interleaved tables/images are appended into the answer until next question.
* `.docx`: heading levels form a question stack; paragraphs and pictures under a heading become the answer.

### Output Behavior

* Each Q/A pair is one chunk.
* `content_with_weight` is prefixed as `问题：...	回答：...` for Chinese or `Question: ...	Answer: ...` for English.
* Token fields are generated from the question, so recall is biased toward the question text.
* Row number or PDF positions are preserved when available.
* Images can mark the chunk as image-like while keeping Q/A content.

### Project Adaptation

* Copy behavior conceptually for Q/A sources: one Q/A pair maps to one import chunk.
* Store `source_text` as the prefixed Q/A text, and keep structured evidence:
  * `question`, `answer`, `row_index`, `sheet_name`, `page_number`, `position_tag`, `pdf_positions`.
* For Markdown/DOCX title stacks, map the stack to `section_path` and the final heading to the question path.
* For malformed txt/csv rows, follow RAGFlow: append to the current answer only after a valid question exists; otherwise record skipped row evidence.
* Do not bypass review: Q/A chunks still enter import review and candidate FAQ flow instead of becoming official FAQ directly.

## Table Chunker

### Inputs

* `.xlsx/.xls`: first significant rows become headers; v0.26 has multi-level header support, merged-cell inheritance, type inference, duplicate header rejection, and optional xlsx image description handling.
* `.txt`: first line is headers; default delimiter is tab unless configured.
* `.csv`: first row is headers; uses `csv.reader` with configurable delimiter.

### Output Behavior

* Every data row is one chunk.
* Empty rows are skipped; malformed rows are recorded as failures.
* Headers are meaningful semantic field names, and row text is formatted as field-value pairs.
* RAGFlow stores typed fields / field maps for search engines; that storage model is not portable to this project.
* Tables or flow images can still become table/image chunks through `tokenize_table`.

### Project Adaptation

* Treat each data row as one import chunk for table chunker.
* Use readable row text:
  * `- 字段: 值` per line, matching RAGFlow's LLM-friendly row formatting.
* Preserve row metadata in `source_offsets`:
  * `sheet_name`, `row_index`, `header_rows`, `headers`, `field_map`, and malformed row notes where relevant.
* For multi-level headers, build `父级-子级` header names like RAGFlow.
* For duplicate headers, fail parsing with a clear import-file error rather than silently overwriting columns.
* Defer xlsx image-description parity unless a visual model path is confirmed.

## Manual Chunker

### Inputs

* `.pdf`: uses selected layout recognizer. When MinerU/Docling/PaddleOCR/TCADP is selected, parser output is normalized to `(text, layoutno, positions)`.
* `.docx`: heading levels form title paths; tables are turned into HTML, with nearest title hierarchy embedded in table caption.

### Output Behavior

* PDF sections are grouped by outline if enough outlines exist; otherwise by bullet/title frequency.
* Small or same-section pieces are merged until token thresholds are reached.
* Tables and images are tokenized separately but can receive surrounding text context.
* PDF outline can be attached as transient metadata for document-level persistence.

### Project Adaptation

* This is the closest route for customer manuals, SOPs, policies, and product instructions.
* Build parent chunks from title/section groups, not only flat token windows.
* Use existing `section_path`, `page_start/page_end`, `source_offsets.pdf_positions`, and `source_blocks` to retain inspectable evidence.
* For table/image chunks, keep `table_html`/asset paths and optional `media_context`.
* PDF outline metadata should be stored at import-file metadata level only after a schema/UI decision; do not hide it inside source text.

## Naive Chunker

### Inputs

* General fallback for PDF/DOCX/XLSX/CSV/TXT/Markdown/HTML/EPUB/JSON.
* Parser stage extracts `sections` and `tables`, then merge stage works on structured sections.
* PDF can use MinerU through `by_mineru`; deployment/provider lookup is RAGFlow-specific and should not be copied.

### Output Behavior

* `naive_merge` appends sections until token threshold is exceeded.
* Custom delimiters wrapped in backticks force segment splits.
* `children_delimiter` creates child chunks with `mom_with_weight` as the parent text.
* `tokenize_chunks` removes PDF position tags from user-facing text but preserves positions separately.
* `naive_merge_docx` treats text/table/image as typed chunks and can attach context around media.

### Project Adaptation

* Existing `ragflow_naive_merge_blocks`, `children_delimiter`, structured `source_blocks`, and parent/child rows already align with this behavior.
* Keep improving evidence fidelity rather than replacing this path.
* Naive remains the fallback route, but manual should be preferred for long structured manuals if the user/import intent says the source is a manual/SOP.

## Parent-Child Retrieval

RAGFlow parent-child behavior is:

* Child chunks are indexed with `mom_id`.
* Parent chunks are inserted with `available_int = 0`, so they are not normal retrieval candidates.
* `retrieval_by_children()` groups child hits by `mom_id`, fetches the parent, and ranks parent contexts by average child similarity.

Project adaptation already started:

* Direct retrieval excludes document `chunk_level = 'parent'`.
* Parent remains available through child-hit context backfill.
* Parent embeddings can remain for UI/vector-state compatibility, but they should not compete with children by default.

## What Not To Copy

* RAGFlow task executor, tenant model lookup, ES/Infinity/OceanBase field model, RAPTOR, GraphRAG, MinIO image storage, and provider registry.
* RAGFlow's local heavy parser stack as a deployment requirement.
* Any shortcut that guesses chunker behavior without making the route explicit and testable.

## Recommended Next Implementation Order

1. Add explicit project-owned chunker type names: `naive`, `manual`, `qa`, `table`.
2. Store selected/recommended chunker source in import-file or import-chunk metadata.
3. TDD `table` row chunking first because it is deterministic and high-value for xlsx/csv imports.
4. TDD `qa` pair chunking next, including malformed txt/csv continuation behavior and Markdown heading stack.
5. TDD `manual` title hierarchy grouping for parsed MinerU/ParsedBlock inputs.
6. Keep `naive` as fallback and regression-protect existing evidence preservation.
