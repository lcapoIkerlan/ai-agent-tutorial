# AI Agent Tutorial: Design Spec

Date: 2026-11-19

## Goal

A template repository that a non-technical user can download and, by filling in a few values and dropping documents in a folder, deploy their own question-answering agent with `docker compose up`. The deployed container exposes an A2A-compatible endpoint that a separate, central A2A platform (a different repo) can call.

## Scope

In scope:
- One container running a single agent that answers questions about the user's documents (RAG).
- An A2A-compliant surface: agent card and JSON-RPC `message/send`.
- A step-by-step README aimed at non-technical users.

Out of scope (explicitly):
- Any A2A hub, registry, orchestrator or A2A client. The agent never calls other agents.
- Streaming (`message/stream`), push notifications, multi-turn memory, attachments/images in requests.
- Document sources other than a local folder (no URLs, SharePoint, Confluence, GitLab).
- Web chat UI.

## Language

Everything in the repo is in English: README, code comments, logs, error messages, `.env.example`, agent card.

## User experience

1. Install Docker Desktop and download the repo (ZIP or `git clone`).
2. Copy `.env.example` to `.env` and fill in a few values.
3. Copy documents (PDF, DOCX, MD, TXT) into `documents/`.
4. Run `docker compose up`.
5. Open `http://localhost:8000/.well-known/agent-card.json` to verify. That base URL is what the user registers in the central A2A platform.

Changing `documents/` later: `docker compose restart`.

## Configuration (`.env`)

| Variable | Required | Purpose |
|---|---|---|
| `AGENT_NAME` | yes | Name shown in the agent card |
| `AGENT_DESCRIPTION` | yes | Description shown in the agent card and used as the single skill's description |
| `LLM_MODEL` | yes | litellm model string, e.g. `anthropic/claude-sonnet-5-5`, `openai/gpt-...` |
| Provider API key | yes | The key matching the provider, e.g. `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` |
| `PUBLIC_URL` | no | URL published in the agent card. Default `http://localhost:8000` |
| `AGENT_API_KEY` | no | If set, requests must send `Authorization: Bearer <key>`. If unset the endpoint is open and the README warns about it |

## Architecture

Single container, single service in `docker-compose.yml`. Chroma data persists in a Docker volume.

```
ai-agent-tutorial/
├── README.md
├── .env.example
├── docker-compose.yml
├── Dockerfile
├── documents/            # user documents
├── app/
│   ├── main.py           # startup: validate config, index docs, serve
│   ├── config.py         # read and validate .env
│   ├── indexer.py        # docs -> chunks -> Chroma
│   ├── agent.py          # question -> retrieval -> litellm -> answer with sources
│   └── a2a_endpoint.py   # agent card + JSON-RPC via a2a-sdk
└── tests/
```

Technology: Python, official `a2a-sdk`, `litellm` (provider abstraction), Chroma with its built-in local ONNX embeddings (no second API key).

Units and boundaries:
- `config.py`: env in, validated settings out. No other module reads env vars.
- `indexer.py`: folder + Chroma collection in, updated index out. Knows nothing about A2A or the LLM.
- `agent.py`: question in, answer + source file names out. Knows nothing about A2A transport.
- `a2a_endpoint.py`: adapts `agent.py` to the A2A protocol and handles auth.

## Exposed surface

- `GET /.well-known/agent-card.json`
- `POST /` (JSON-RPC, `message/send`)

Nothing else. The agent card declares one skill: answer questions about the loaded documentation, using `AGENT_DESCRIPTION`.

## Data flow

Startup:
1. `config.py` validates `.env`; on failure the container exits with a clear message.
2. `indexer.py` walks `documents/`, hashes each file, processes only new or modified files, and removes index entries for deleted files. Text is extracted from PDF, DOCX, MD and TXT, split into chunks of about 800 characters with overlap, and stored in Chroma with the file name as metadata.
3. The server starts.

Per request (`message/send`):
1. Receive the text message.
2. Retrieve the 5 most similar chunks from Chroma.
3. Call litellm with a fixed system prompt ("Answer only from the provided excerpts. If the answer is not in them, say so."), the excerpts and the question.
4. Return an A2A message containing the answer and the names of the source files used.

Each request is independent; no conversation history is kept.

## Errors

| Situation | Behavior |
|---|---|
| Missing/invalid config | Exit at startup: `Missing ANTHROPIC_API_KEY in your .env file` (variable name matches the provider) |
| `documents/` empty | Start anyway, log `No documents found in documents/. Add files and restart.`, agent answers that no documentation is loaded |
| Unreadable file (e.g. scanned PDF with no text) | Log a warning with the file name, skip it, continue |
| LLM provider failure | Failed A2A task with `The LLM provider returned an error: <reason>`; no retry |
| Wrong/missing bearer token (when `AGENT_API_KEY` set) | HTTP 401 `Unauthorized` |

## Testing

- Unit tests: indexer (chunking, hashing, deletions), config validation.
- Endpoint test with a mocked LLM: agent card is valid; `message/send` returns the answer with sources; 401 behavior with `AGENT_API_KEY` set.
- No tests against real LLM APIs.

## Notes for the implementation plan

- Verify the current `a2a-sdk` API against its up-to-date documentation before writing code.
- Default is `message/send` only; streaming is deferred until the central platform needs it.
- The user folder is `documents/` (not `docs/`) because `docs/` holds this repo's own specs and plans, which must not be indexed.
- With `AGENT_API_KEY` set, only `POST /` requires the bearer token; the agent card stays public so the central platform can discover the agent.
