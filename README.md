# Customer Service Agent

Local customer-service agent backed by PostgreSQL + pgvector retrieval and an
OpenAI-compatible chat model.

This repository intentionally excludes concrete FAQ/question-answer data and the
production system prompt. Keep customer data in local ignored files such as
`data/faqs.jsonl` and keep deployment prompts in `system_prompt.txt`.

## Components

- `customer_service_agent/cli.py`: CLI for config checks, DB init, FAQ import, local search/ask, WeChat login, and service start.
- `customer_service_agent/db.py`: PostgreSQL schema init, FAQ upsert, pgvector search.
- `customer_service_agent/rag.py`: retrieval + answer generation.
- `customer_service_agent/rag_tool.py`: structured RAG tool interface for an upstream customer-service agent.
- `customer_service_agent/wechat_client.py`: personal WeChat client wrapper.
- `customer_service_agent/wechat_service.py`: long-running message loop.
- `scripts/install_user_service.sh`: renders and installs the user-level systemd unit from `systemd/customer-service-agent.service.template`.

## RAG tool mode

The recommended integration boundary is to use this project as a read-only FAQ/SOP RAG
tool called by a separate customer-service agent. This project returns knowledge hits and
an optional answer draft for the upstream agent to evaluate. It does not open accounts,
reset passwords, refresh caches, dispatch tasks, modify backend data, or send messages to
end users through this interface.

Structured FAQ search:

```bash
conda run -n customer-service-agent python -m customer_service_agent.cli tool-search "How do I handle a missing assigned item?"
```

Structured answer draft for an upstream agent:

```bash
conda run -n customer-service-agent python -m customer_service_agent.cli tool-answer "How do I handle a missing assigned item?"
```

Both commands print a single JSON object. `tool-search` returns retrieved FAQ documents.
`tool-answer` returns `answer_draft` plus the same source documents, so the caller can
decide whether to answer directly, ask a follow-up question, call another backend tool, or
handoff to a human.

Existing `search`, `ask`, and WeChat commands remain available for local testing and the
earlier standalone MVP path, but the RAG tool commands are the cleaner integration surface
for a configured frontend/customer-service agent.

## System dependencies

Ubuntu/Debian:

```bash
sudo apt-get update
sudo apt-get install -y postgresql postgresql-contrib postgresql-16-pgvector
sudo systemctl enable --now postgresql
```

Optional verification:

```bash
sudo -u postgres psql -tAc "SELECT name FROM pg_available_extensions WHERE name = 'vector';"
```

## Conda environment

```bash
conda env create -f environment.yml
conda run -n customer-service-agent python --version
```

## Configuration

Create a local `.env` from the template and fill in real values:

```bash
cp .env.example .env
cp system_prompt.example.txt system_prompt.txt
```

Required settings are:

- `DATABASE_URL`
- `CHAT_BASE_URL`
- `CHAT_API_KEY`
- `CHAT_MODEL`
- `EMBEDDING_BASE_URL`
- `EMBEDDING_API_KEY`
- `EMBEDDING_MODEL`

Notes:

- `.env` must not be committed.
- `system_prompt.txt` must not be committed.
- FAQ data files such as `*.jsonl` and `*.csv` must not be committed.
- `WECHAT_TOKEN_FILE` defaults to `/home/adam/.wxbot/token.json`.
- `EMBEDDING_DIMENSIONS`, `WECHAT_MESSAGE_CHUNK_SIZE`, `RAG_TOP_K`, and `RAG_MIN_SCORE` have sensible defaults in code and can stay unset unless you need overrides.

Quick config check:

```bash
conda run -n customer-service-agent python -m customer_service_agent.cli check-config
```

## Local FAQ admin

Start the local admin page:

```bash
conda run -n customer-service-agent python -m customer_service_agent.cli admin --host 127.0.0.1 --port 8765
```

Open `http://127.0.0.1:8765`.

The admin page is local-only and has no login. Saving a FAQ writes text and metadata only;
it does not generate an embedding. Use the drawer action `生成 embedding` for one record,
or the sidebar batch action for pending/stale/failed records.

## Database init and FAQ import

Create the database and role first if they do not already exist, then initialize schema and import data.

Example:

```bash
sudo -u postgres psql
CREATE USER customer_service_agent WITH PASSWORD '<choose-a-strong-password>';
CREATE DATABASE customer_service_agent OWNER customer_service_agent;
\q
```

Initialize schema:

```bash
conda run -n customer-service-agent python -m customer_service_agent.cli init-db
```

Import your local FAQ JSONL:

```bash
conda run -n customer-service-agent python -m customer_service_agent.cli import-faq --path data/faqs.jsonl
```

## Local retrieval and answer testing

Vector search:

```bash
conda run -n customer-service-agent python -m customer_service_agent.cli search "How do I handle a missing assigned item?"
```

RAG answer:

```bash
conda run -n customer-service-agent python -m customer_service_agent.cli ask "How do I handle a missing assigned item?"
```

## WeChat login

Login is a separate manual step and writes the token file configured by `WECHAT_TOKEN_FILE`:

```bash
conda run -n customer-service-agent python -m customer_service_agent.cli wechat-login
```

After login succeeds, the long-running service can reuse that token.

## systemd user service

Install the rendered unit:

```bash
./scripts/install_user_service.sh
```

Enable user lingering so the service can stay up after logout:

```bash
sudo loginctl enable-linger "$USER"
```

Start and inspect the service:

```bash
systemctl --user start customer-service-agent.service
systemctl --user status customer-service-agent.service
journalctl --user -u customer-service-agent.service -f
```

Useful operations:

```bash
systemctl --user restart customer-service-agent.service
systemctl --user stop customer-service-agent.service
```

The installer renders local absolute paths into `~/.config/systemd/user/customer-service-agent.service`, including the repo path, `.env` path, and the Python executable from the `customer-service-agent` conda environment.

## Verification

```bash
conda run -n customer-service-agent ruff check .
conda run -n customer-service-agent python -m customer_service_agent.cli --help
```
