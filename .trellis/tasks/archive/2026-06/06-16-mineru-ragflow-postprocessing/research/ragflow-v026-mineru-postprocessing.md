# RAGFlow v0.26.0 MinerU 后处理研究

## Source

* Repository: `/home/adam/projects/ragflow`
* Local starting point: `v0.25.1` (`ce4c782`, 2026-04-30)
* Latest fetched tag at research time: `v0.26.0`
* Compared range: `v0.25.1..v0.26.0`

## Relevant Changes

### MinerU parser

RAGFlow v0.26.0 changed `deepdoc/parser/mineru_parser.py` in areas relevant to this project:

* More robust MinerU output discovery:
  * handles original and sanitized file names;
  * handles `vlm/` subdirectory;
  * searches multiple `content_list.json` and `*_content_list.json` fallback patterns.
* Text sanitization:
  * unescapes HTML entities;
  * converts HTML/table/list block endings to newlines;
  * strips HTML tags before chunking-facing text is used.
* Page chrome filtering:
  * commit `d398d617c fix(mineru): skip page chrome blocks to prevent duplicate chunks (#15387)` adds logic and fixtures to prevent repeated page chrome from becoming duplicate chunks.
* Image semantic enrichment:
  * commit `f58e0b3ec Feat: VLM image descriptions in MinerU parser (#14869) (#14946)` optionally generates descriptions for image blocks when a visual model is available.

### Naive chunker

RAGFlow v0.26.0 changed `rag/app/naive.py` in areas relevant to this project:

* MinerU provider lookup changed with tenant provider refactors; not directly portable.
* MinerU can pass a vision model into the parser for image description enrichment.
* Markdown short headers are force-merged with following content to avoid isolated title-only chunks.
* OpenDataLoader and provider selection changes are not directly relevant unless this project later supports more providers.

### Parent-child indexing and retrieval

RAGFlow behavior remains important:

* child chunks carry `mom_with_weight` before indexing;
* task executor creates parent chunks with `mom_id` and `available_int = 0`;
* retrieval first returns child hits, then `retrieval_by_children()` folds child hits into parent chunks and sorts by child similarity.

This differs from the current project, where parent and child both enter `knowledge_chunks` with ready embeddings and can compete in the same SQL search.

## Portability Assessment

### Move Into This Project

* MinerU output file fallback rules.
* HTML/table/list text sanitization rules.
* Page chrome detection as text filtering, while retaining page/bbox evidence.
* Optional image description support as a later feature flag.
* Markdown short-title merge behavior if MinerU Markdown fallback is used.
* Parent-child retrieval concept: child recall + parent context, avoiding parent/child equal competition.

### Adapt, Do Not Copy Directly

* RAGFlow model/provider lookup, because this project uses OpenAI-compatible clients and local settings.
* RAGFlow task executor, because it is tied to RAGFlow job orchestration, doc stores, RAPTOR, GraphRAG, recording context, and cancellation.
* RAGFlow ES/Infinity field names, because this project uses PostgreSQL `import_chunks` and `knowledge_chunks`.
* RAGFlow image storage, because this project stores MinerU assets under local upload directories.

### Not Needed In MVP

* OpenDataLoader-specific parser options.
* RAGFlow tenant provider registry.
* RAPTOR migration and cleanup behavior.
* GraphRAG ingestion changes.

## Project-Specific Balance

The project should preserve UI and auditability semantics even when adopting RAGFlow behavior:

* page chrome text should not enter `source_text` or `embedding_text`;
* `page_start`, `page_end`, `source_offsets`, and asset evidence should remain available;
* filtered blocks should be explainable in metadata or debug output;
* import review remains the boundary before formal FAQ or searchable knowledge;
* vector generation remains a separate explicit step.

## Recommended Direction

Implement a project-owned `MineruPostProcessor` pipeline:

1. read MinerU zip/json robustly;
2. normalize blocks and assets;
3. sanitize text and table HTML;
4. mark/filter page chrome from text while retaining evidence;
5. produce stable `ParsedBlock` records;
6. feed existing or new chunkers;
7. adjust indexing/retrieval so child chunks drive recall and parent chunks provide context.
