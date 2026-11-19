# AI Agent Tutorial Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A template repo where a non-technical user fills `.env`, drops files in `documents/`, runs `docker compose up`, and gets an A2A-compatible agent that answers questions about those files.

**Architecture:** One Python container. `config` validates env; `Index` (Chroma) syncs `documents/` at startup and serves similarity search; `answer_question` retrieves 5 chunks and calls litellm; `a2a_endpoint` adapts it to A2A via the official `a2a-sdk` on a Starlette app. No hub, registry or A2A client.

**Tech Stack:** Python 3.12, `a2a-sdk[http-server]==1.3.1`, `litellm`, `chromadb` (default local ONNX embeddings), `pypdf`, `python-docx`, `uvicorn`, `pytest`, `httpx`. Pin exact versions in `requirements.txt` at install time.

**Spec:** `docs/superpowers/specs/2026-11-19-ai-agent-tutorial-design.md`

## Global Constraints

- Everything in the repo is English: README, comments, logs, error messages, `.env.example`, agent card.
- User documents folder is `documents/` (spec says `docs/`; renamed because `docs/superpowers/` holds specs/plans and would be indexed). Spec amended in the same commit as this plan.
- Supported extensions: `.pdf`, `.docx`, `.md`, `.txt`. Chunks ~800 chars with overlap. Top 5 chunks per question.
- Exposed surface only: `GET /.well-known/agent-card.json` and `POST /` (JSON-RPC). `message/send` only; no streaming, push, history, attachments.
- Verified against a2a-sdk 1.3.1: `create_jsonrpc_routes(handler, rpc_url="/", enable_v0_3_compat=True)` serves both `message/send` (v0.3) and `SendMessage` (v1.0) at `POST /`. The card must list `AgentInterface` entries for JSONRPC versions `1.0` and `0.3` at `PUBLIC_URL`.
- Env vars: `AGENT_NAME`, `AGENT_DESCRIPTION`, `LLM_MODEL`, provider key (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`), optional `PUBLIC_URL` (default `http://localhost:8000`), optional `AGENT_API_KEY`.
- Error strings (exact): `Missing <VAR> in your .env file`; `No documents found in documents/. Add files and restart.`; `The LLM provider returned an error: <reason>`; HTTP 401 `Unauthorized`.
- Each request independent; no state. Single uvicorn worker (Chroma is not multi-process safe).

## Review Focus

- Subfolders inside `documents/`: indexed recursively, source name is the relative path.
- Junk files (`.DS_Store`, `~$lock.docx`, `.png`): ignored silently, no warning noise.
- File edited between restarts: old chunks replaced, no duplicates; renamed file: old name disappears.
- Whitespace-only or empty question: answered with a short "send a question" reply, no LLM call.
- `PUBLIC_URL` with trailing slash or `AGENT_API_KEY` set to empty string in `.env`: slash normalized; empty string means auth disabled.
- Bearer header with wrong scheme/case (`bearer x`, `Basic x`): scheme is case-insensitive, wrong scheme or wrong token is 401; the agent card stays public so the central platform can discover the agent.

---

### Task 1: Project skeleton and config

**Files:**
- Create: `app/__init__.py`, `app/config.py`, `tests/test_config.py`, `requirements.txt`, `.env.example`, `.gitignore` (ignore `.env`, `data/`, `__pycache__`, `.venv`), `documents/.gitkeep`

**Interfaces:**
- Produces:
  - `class ConfigError(Exception)`
  - `@dataclass(frozen=True) class Settings: agent_name: str; agent_description: str; llm_model: str; public_url: str; agent_api_key: str | None; documents_dir: Path; data_dir: Path`
  - `def load_settings(env: Mapping[str, str] | None = None) -> Settings` (defaults to `os.environ`; `documents_dir=Path("documents")`, `data_dir=Path("data")`, overridable by `DOCUMENTS_DIR`/`DATA_DIR`)

- [ ] **Step 1: Write failing tests in `tests/test_config.py`:** valid env returns Settings with `public_url` default `http://localhost:8000`; each missing required var raises `ConfigError` with exactly `Missing AGENT_NAME in your .env file` (parametrize over `AGENT_NAME`, `AGENT_DESCRIPTION`, `LLM_MODEL`); `LLM_MODEL=anthropic/x` without `ANTHROPIC_API_KEY` raises `Missing ANTHROPIC_API_KEY in your .env file` (same for `openai/`→`OPENAI_API_KEY`, `gemini/`→`GEMINI_API_KEY`); unknown provider prefix is accepted without key check; `LLM_MODEL` without `/` raises `LLM_MODEL must look like provider/model, e.g. anthropic/claude-sonnet-5-5`; `PUBLIC_URL="http://x:9/"` → `http://x:9`; `AGENT_API_KEY=""` → `None`.
- [ ] **Step 2: Run** `python -m pytest tests/test_config.py -v` → FAIL (module missing).
- [ ] **Step 3: Implement `load_settings`/`Settings`/`ConfigError` in `app/config.py`** per the Interfaces and tests. Create `requirements.txt`, `.env.example` (every variable commented in English, provider keys blank, `AGENT_API_KEY` commented with an "endpoint is open if unset" warning), `.gitignore`, `documents/.gitkeep`.
- [ ] **Step 4: Run** `python -m pytest tests/test_config.py -v` → PASS.
- [ ] **Step 5: Commit** `feat: project skeleton and config validation`.

### Task 2: Document index

**Files:**
- Create: `app/indexer.py`, `tests/test_indexer.py`, `tests/fixtures/` (tiny `.md`, `.txt`, `.pdf`, `.docx` generated in-test via `tmp_path` where possible)

**Interfaces:**
- Produces:
  - `SUPPORTED_EXTENSIONS: frozenset[str]`
  - `def extract_text(path: Path) -> str` (pdf via pypdf, docx via python-docx, md/txt read as UTF-8 with `errors="replace"`)
  - `def chunk_text(text: str, size: int = 800, overlap: int = 100) -> list[str]`
  - `@dataclass(frozen=True) class Chunk: text: str; source: str`
  - `@dataclass class SyncReport: added: list[str]; updated: list[str]; removed: list[str]; skipped: list[str]`
  - `class Index: __init__(self, data_dir: Path, embedding_function: EmbeddingFunction | None = None)`; `sync(self, documents_dir: Path) -> SyncReport`; `search(self, query: str, k: int = 5) -> list[Chunk]`; `count(self) -> int`

- [ ] **Step 1: Write failing tests** with a deterministic fake `embedding_function` (hash-based vectors, no network): `chunk_text` splits a 2000-char text into overlapping chunks, each ≤ 800, covers all text, returns `[]` for blank; `extract_text` reads `.md`/`.txt`; `sync` on two files reports both `added`; a second `sync` unchanged reports nothing; editing a file puts it in `updated` and `count()` does not grow (no duplicates); deleting/renaming a file puts it in `removed` and its chunks disappear from `search`; a subfolder file gets source `sub/a.md`; `.DS_Store`, `~$x.docx`, `.png` are ignored and not in `skipped`; an unreadable/empty-text `.pdf` goes in `skipped` and does not raise; `search` returns `Chunk`s whose `source` matches the file; `sync` on an empty folder returns an empty report.
- [ ] **Step 2: Run** `python -m pytest tests/test_indexer.py -v` → FAIL.
- [ ] **Step 3: Implement `app/indexer.py`.** Persistent Chroma client at `data_dir/chroma`; one collection; per-file SHA-256 stored as chunk metadata (`source`, `sha256`); a file is unchanged if its stored hash equals the current one; replace = delete by `source` then add. Log one English line per added/updated/removed/skipped file (`logging`, no prints).
- [ ] **Step 4: Run** `python -m pytest tests/test_indexer.py -v` → PASS.
- [ ] **Step 5: Commit** `feat: document indexer with incremental sync`.

### Task 3: Agent (retrieval + LLM)

**Files:**
- Create: `app/agent.py`, `tests/test_agent.py`

**Interfaces:**
- Consumes: `Index.search(query, k) -> list[Chunk]`, `Index.count() -> int`
- Produces:
  - `class LLMError(Exception)` (message is the provider reason)
  - `@dataclass(frozen=True) class Answer: text: str; sources: list[str]`
  - `def answer_question(question: str, index: Index, model: str) -> Answer` (calls `litellm.completion` via the module attribute so tests can monkeypatch `app.agent.litellm.completion`)

- [ ] **Step 1: Write failing tests** (fake index object with `search`/`count`; monkeypatched `litellm.completion`): empty index → `Answer` saying `No documentation is loaded. Add files to documents/ and restart the agent.`, `sources == []`, LLM not called; blank/whitespace question → `Please send a question.`, LLM not called; normal case → `Answer.text` is the mocked completion content, `sources` is the de-duplicated, order-preserving source list of the retrieved chunks, and the messages passed to litellm include a system prompt containing `Answer only from the provided excerpts. If the answer is not in them, say so.`, every chunk text, and the question; any exception from `litellm.completion` → `LLMError(str(exc))`.
- [ ] **Step 2: Run** `python -m pytest tests/test_agent.py -v` → FAIL.
- [ ] **Step 3: Implement `app/agent.py`.** Use `litellm.completion(model=model, messages=[system, user])`, read `choices[0].message.content`.
- [ ] **Step 4: Run** `python -m pytest tests/test_agent.py -v` → PASS.
- [ ] **Step 5: Commit** `feat: retrieval agent over litellm`.

### Task 4: A2A endpoint, auth and entrypoint

**Files:**
- Create: `app/a2a_endpoint.py`, `app/main.py`, `tests/test_a2a_endpoint.py`

**Interfaces:**
- Consumes: `Settings` (Task 1), `Index` (Task 2), `answer_question`, `Answer`, `LLMError` (Task 3)
- Produces:
  - `class DocsAgentExecutor(AgentExecutor)` with `__init__(self, index: Index, model: str)`; `execute` reads `context.get_user_input()`, runs `answer_question` in a thread (`asyncio.to_thread`), publishes one artifact `answer` whose text is `<answer>` plus, when sources exist, `\n\nSources: a.pdf, b.md`, then `TaskUpdater.complete()`; on `LLMError` calls `TaskUpdater.failed(updater.new_agent_message([Part(text="The LLM provider returned an error: <reason>")]))`; `cancel` is a no-op
  - `def build_app(settings: Settings, index: Index) -> Starlette`: agent card (name/description from settings, one skill `answer_questions` described by `agent_description`, `streaming=False`, `push_notifications=False`, `AgentInterface` JSONRPC `1.0` and `0.3` at `settings.public_url + "/"`), `create_agent_card_routes` + `create_jsonrpc_routes(handler, rpc_url="/", enable_v0_3_compat=True)`, `InMemoryTaskStore`; bearer middleware on `POST` only when `settings.agent_api_key` is set (scheme case-insensitive, `hmac.compare_digest`, failure → `401` body `Unauthorized`); card route never requires auth
  - `app/main.py: main() -> None`: `load_settings()` (on `ConfigError` print `Configuration error: <msg>` to stderr, exit 1) → `Index(...).sync(...)` → log `No documents found in documents/. Add files and restart.` when `count()==0` → `uvicorn.run(build_app(...), host="0.0.0.0", port=8000)`; guarded by `if __name__ == "__main__"`

- [ ] **Step 1: Write failing tests** with Starlette `TestClient`, a fake index and monkeypatched `answer_question`: `GET /.well-known/agent-card.json` returns the configured name/description and lists JSONRPC interfaces for `1.0` and `0.3`; `POST /` with the v0.3 body `{"jsonrpc":"2.0","id":1,"method":"message/send","params":{"message":{"kind":"message","messageId":"m1","role":"user","parts":[{"kind":"text","text":"hi"}]}}}` returns `result.status.state == "completed"` and an artifact text containing the answer and `Sources: a.md`; the v1.0 `SendMessage` body (`"role":"ROLE_USER"`, header `A2A-Version: 1.0`) returns `TASK_STATE_COMPLETED`; `LLMError("quota")` yields state `failed` and a status message containing `The LLM provider returned an error: quota`; with `agent_api_key="k"`: POST without header → 401 `Unauthorized`, `Basic k` → 401, `Bearer wrong` → 401, `bearer k` → 200, and the card GET stays 200 without header; with no key set, POST needs no header.
- [ ] **Step 2: Run** `python -m pytest tests/test_a2a_endpoint.py -v` → FAIL.
- [ ] **Step 3: Implement `app/a2a_endpoint.py` and `app/main.py`** per the Interfaces. Imports verified in a2a-sdk 1.3.1: `a2a.server.agent_execution (AgentExecutor, RequestContext)`, `a2a.server.events.EventQueue`, `a2a.server.request_handlers.DefaultRequestHandler(agent_executor, task_store, agent_card)`, `a2a.server.routes (create_agent_card_routes, create_jsonrpc_routes)`, `a2a.server.tasks (InMemoryTaskStore, TaskUpdater)`, `a2a.types (AgentCard, AgentCapabilities, AgentInterface, AgentSkill, Part)`. `TaskUpdater(event_queue, task_id, context_id)`.
- [ ] **Step 4: Run** `python -m pytest -v` (whole suite) → PASS.
- [ ] **Step 5: Commit** `feat: A2A endpoint with optional bearer auth`.

### Task 5: Docker, compose and tutorial README

**Files:**
- Create: `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `README.md`

**Interfaces:**
- Consumes: `app.main` (Task 4), `.env.example` (Task 1)
- Produces: image running `python -m app.main` on port 8000

- [ ] **Step 1: Write `Dockerfile`:** `python:3.12-slim`, install `requirements.txt`, copy `app/`, pre-warm the Chroma default embedding model at build time (instantiate `chromadb.utils.embedding_functions.DefaultEmbeddingFunction()` and embed one string) so first start needs no download, `CMD ["python", "-m", "app.main"]`.
- [ ] **Step 2: Write `docker-compose.yml`:** one service `agent`, `build: .`, `env_file: .env`, `ports: "8000:8000"`, volumes `./documents:/app/documents` and a named volume `agent-data:/app/data`, `restart: unless-stopped`.
- [ ] **Step 3: Write `README.md` (English, non-technical):** what it is; prerequisites (Docker Desktop only); the 5 steps from the spec; `.env` variable table; supported file types; how to update documents (`docker compose restart`); how to verify (open the agent-card URL, plus one `curl` `message/send` example); how to register the URL in the central A2A platform; security note on the open endpoint and `AGENT_API_KEY`; troubleshooting table mapping each exact error string to its fix.
- [ ] **Step 4: Verify end to end.** With a real `.env` (test key) and a sample file in `documents/`: `docker compose up --build`, then `curl localhost:8000/.well-known/agent-card.json` returns the card and the `message/send` example returns a completed task citing the file. With the key removed, the container exits with `Missing <VAR> in your .env file`. Record the outcome; if no API key is available, verify the card, the empty-`documents/` reply and the config error, and say the LLM path was only covered by mocks.
- [ ] **Step 5: Commit** `feat: docker packaging and tutorial README`.
