# Cyclops Assistant Contracts

> Project-specific contracts for the internal platform assistant page.

## Scenario: Assistant Chat Stream

### 1. Scope / Trigger

- Trigger: code modifies `AdminApp.iter_assistant_chat_events()`, `assistant_document_payload()`, or frontend consumers under `web/src/pages/assistant/`.
- Reason: the internal platform question page relies on the backend SSE stream to show retrieval steps, source evidence, and the final answer. A field drift can make the page look correct while hiding missing evidence or unsafe behavior.

### 2. Signatures

- Backend stream method: `AdminApp.iter_assistant_chat_events(payload: dict[str, Any]) -> Iterator[dict[str, Any]]`
- SSE formatter: `format_sse_event(event: dict[str, Any]) -> str`
- Source payload builder: `assistant_document_payload(doc: Any) -> dict[str, Any]`
- Prompt builder: `build_user_prompt(question: str, docs: Sequence[RetrievedDocument], conversation_context: ConversationContext | None = None) -> str`
- Frontend stream client: `streamAssistantChat({ payload, signal, onEvent })`
- Frontend source type: `AssistantSource`

### 3. Contracts

- Stream events must use `type` values consumed by the frontend:
  - `meta`
  - `step`
  - `delta`
  - `done`
  - `error`
- `format_sse_event()` must emit `event: <type>` and JSON `data` with the same `type`.
- `step` events for retrieval must keep debug fields serializable, especially `analysis` and `documents`.
- `done` events must include:
  - `flow_id`
  - `question`
  - `answer_draft`
  - `documents`
- Sensitive questions with `analysis.safety_action == "refuse"` must stop after intent detection and must not call embedding, vector search, keyword search, rerank, or answer-generation LLM.
- Realtime status questions may retrieve SOP/help content, but the prompt sent to the model must explicitly state that the assistant cannot confirm backend realtime status and must not fabricate realtime status.
- `conversation_context` is optional request context for the current assistant turn only:
  - Shape: `{ summary?: string, recent_messages: [{ role: "user" | "assistant", content: string }] }`
  - It must not be persisted to the database and must not be shared across conversations.
  - Backend normalization must discard invalid roles, empty content, and non-object items.
  - Backend formatting must use the GenericAgent-inspired short-term context structure:
    - `### [WORKING MEMORY]`
    - optional `<earlier_context>...</earlier_context>` for compact old history
    - optional `<history>` with `[USER] ...` and `[Agent] ...` lines for recent turns
  - The prompt must state that working memory only helps resolve references and follow-up context; factual answers still come from the knowledge-base context.
- `assistant_document_payload()` must expose provenance fields at the top level for frontend rendering:
  - `source_type`
  - `source_id`
  - `source_chunk_id`
  - `parent_chunk_id`
  - `chunk_level`
  - `source_title`
  - `section_path`
  - `page_start`
  - `page_end`
  - `block_type`
  - `source_offsets`
  - `content`
  - `metadata`
  - `score`
- Metadata may keep duplicate provenance for backward compatibility, but frontend code should prefer top-level fields and use metadata only as fallback.

### 4. Validation & Error Matrix

- Missing `question` -> raise `AdminValidationError`.
- Unsupported `flow_id` -> raise `AdminValidationError`.
- Invalid `conversation_context` -> ignore invalid parts and continue the request; do not fail the chat stream for malformed optional history.
- Sensitive question -> return a refusal `delta` and `done` with `documents: []`.
- No retrieval hits -> continue answer generation with no documents and no fabricated knowledge-base evidence.
- Answer-generation model/provider failure -> emit `answer_generation` step with `status: "failed"` and then `type: "error"` with a user-readable model-service message; do not let the exception bubble to the generic SSE `internal error` handler.
- Stream HTTP/SSE transport errors -> frontend must surface an error on the assistant message and stop streaming state.

### 5. Good/Base/Bad Cases

- Good: sensitive query emits `meta`, `input_question`, `intent_detection`, refusal `delta`, `answer_generation completed`, `done` with empty documents.
- Good: answer-generation model failure emits `answer_generation running`, `answer_generation failed`, then `error` and no `done`.
- Good: follow-up questions include `### [WORKING MEMORY]` before the current question while retrieval still uses the current question.
- Good: document source includes top-level `page_start`, `section_path`, `retrieval_channels`, and parent context entry when a child hit expands to parent.
- Base: realtime status query with no hits still sends prompt guidance saying realtime backend state cannot be confirmed.
- Bad: sensitive query goes through embedding or search; the UI can imply the platform retrieved secret knowledge.
- Bad: provider errors such as unsupported model names surface as generic `internal error` in the answer bubble.
- Bad: provenance exists only inside `metadata`; frontend field drift can hide page/section evidence.
- Bad: old conversation history is appended as a full transcript without truncation or working-memory boundaries.

### 6. Tests Required

- Unit test for SSE formatting covering `meta`, `step`, `delta`, `done`, and `error`.
- Regression test for sensitive short-circuit asserting embedding/search/LLM are not called.
- Regression test for realtime status prompt constraints.
- Regression test for answer-generation model failure asserting failed step + `error` event.
- Unit test for `normalize_conversation_context()` and `build_user_prompt(..., conversation_context=...)`.
- Unit test for `assistant_document_payload()` top-level provenance fields.
- Frontend lint/build or focused type check for changed assistant source fields.

### 7. Wrong vs Correct

#### Wrong

```python
analysis = analyze_query(question, chat)
query_embedding = self.embedding_client().embed(analysis.query_rewrite or question)
vector_docs = self.database().search_knowledge(query_embedding, top_k=top_k, min_score=min_score)
```

This lets sensitive questions enter the normal RAG path.

#### Correct

```python
analysis = analyze_query(question, chat)
if analysis.safety_action == "refuse":
    yield {"type": "delta", "text": SENSITIVE_REFUSAL_MESSAGE}
    yield {"type": "done", "answer_draft": SENSITIVE_REFUSAL_MESSAGE, "documents": []}
    return
```

The unsafe query is handled before any retrieval or model-answer generation work.
