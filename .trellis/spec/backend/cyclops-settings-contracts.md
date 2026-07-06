# Cyclops Settings Contracts

> Project-specific contracts for global settings snapshots, secret handling, and provider probe APIs.

## Scenario: Global Settings With Secret-Preserving Provider Probes

### 1. Scope / Trigger

- Trigger: code modifies `/api/settings`, `AdminApp.settings_snapshot()`, `AdminApp.update_settings()`, `/api/assistant/probe`, `/api/assistant/models`, or the settings page under `web/src/pages/SettingsPage.tsx`.
- Reason: the settings UI must not receive saved secret plaintext, but backend provider operations still need to use saved secrets when the user leaves key fields blank.

### 2. Signatures

- `GET /api/settings -> SettingsSnapshot`
- `POST /api/settings(payload: dict[str, Any]) -> SettingsSnapshot`
- `POST /api/assistant/probe(payload: { chat_base_url?: str, chat_api_key?: str, chat_model?: str }) -> { ok: bool, ... }`
- `POST /api/assistant/models(payload: { chat_base_url?: str, chat_api_key?: str }) -> { ok: bool, items: list[dict[str, str]], error?: str }`
- Backend helpers:
  - `AdminApp.settings_snapshot() -> dict[str, Any]`
  - `AdminApp.update_settings(payload: dict[str, Any]) -> dict[str, Any]`
  - `AdminApp._resolved_chat_provider_values(payload: dict[str, Any]) -> tuple[str, str, str]`

### 3. Contracts

- Settings snapshots must return secret fields only as masked strings plus configured booleans:
  - `chat_api_key`, `chat_api_key_configured`
  - `embedding_api_key`, `embedding_api_key_configured`
  - `mineru_api_token`, `mineru_api_token_configured`
  - `rerank_api_key`, `rerank_api_key_configured`
  - `database_url`, `database_url_configured` with password masked when present.
- Settings update payloads preserve existing values when sensitive fields are omitted or blank:
  - `chat_api_key`, `embedding_api_key`, `mineru_api_token`, `rerank_api_key`, `database_url`.
- Provider probe/model-list payload values are temporary overrides:
  - Non-blank `chat_base_url`, `chat_api_key`, and `chat_model` override saved settings for that request.
  - Blank or omitted fields fall back to `self.settings`.
  - Frontend must omit blank `chat_api_key` instead of requiring users to re-enter saved keys.
- The frontend must never infer or reconstruct saved secret plaintext from masked values.

### 4. Validation & Error Matrix

- `probe` missing `base_url`, `api_key`, or `model` after fallback -> return `{ ok: false, error: "请先在设置页配置 base_url、api_key、model，或输入临时值" }`.
- `models` missing `base_url` or `api_key` after fallback -> return `{ ok: false, items: [], error: "请先在设置页配置 base_url、api_key，或输入临时值" }`.
- Provider HTTP failure -> return `{ ok: false, items: [], error: "HTTP <status> <body-prefix>" }` for model listing.
- Settings payload blank sensitive value -> preserve old runtime and tenant-file value.
- Settings payload non-blank sensitive value -> replace old value and refresh runtime clients.

### 5. Good/Base/Bad Cases

- Good: settings page opens with `chat_api_key_configured: true`, shows masked key, leaves key input blank, and "拉取模型" succeeds by using the backend-saved key.
- Good: user enters a new key in the modal; probe/model-list use that temporary key and save can later persist it.
- Base: no saved key and no temporary key; probe/model-list return a clear configuration error.
- Bad: `GET /api/settings` returns the saved API key plaintext.
- Bad: frontend refuses to pull models or test connection solely because the key input is blank while `*_configured` is true.
- Bad: saving a settings modal with a blank key overwrites the saved key with an empty string.

### 6. Tests Required

- Backend regression test that `settings_snapshot()` masks every secret field and exposes configured booleans.
- Backend regression test that `update_settings()` preserves blank sensitive fields.
- Backend regression test that `probe_chat_provider()` uses the saved `chat_api_key` when payload omits or blanks it.
- Backend regression test that `list_chat_provider_models()` sends `Authorization: Bearer <saved-key>` when payload omits or blanks the key.
- Frontend lint/build after changing settings page probe/model-list payload construction.

### 7. Wrong vs Correct

#### Wrong

```typescript
if (!draft.chat_base_url.trim() || !draft.chat_api_key.trim()) {
  toast.error('请输入新的 Base URL 和 API Key 后再拉取模型')
  return
}
```

This confuses "frontend cannot read the saved key" with "backend cannot use the saved key".

#### Correct

```typescript
const apiKey = draft.chat_api_key.trim()
await listModels.mutateAsync({
  chat_base_url: draft.chat_base_url.trim(),
  ...(apiKey ? { chat_api_key: apiKey } : {}),
})
```

The backend receives no plaintext saved key from the browser and falls back to `self.settings.chat_api_key`.
