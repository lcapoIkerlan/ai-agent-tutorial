# Documentation Agent

An AI agent that answers questions about **your own documents** (PDF, Word, Markdown and text files). It follows the open A2A protocol, so a central A2A platform or any other A2A agent can ask it questions.

You do not need to know how to program. You only need Docker Desktop.

## What you need

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running.
- An API key from an AI provider (Anthropic, OpenAI or Google Gemini).

## Setup in 5 steps

1. **Download this project.** Click "Download ZIP" and unzip it (or use `git clone`). Open a terminal in the unzipped folder.
2. **Create your settings file.** Copy `.env.example` to a new file called `.env`, then open `.env` in any text editor and fill in the values (see the table below). Tip: files starting with a dot are hidden on macOS and Windows. In the terminal you can copy it with `cp .env.example .env` (Mac/Linux) or `copy .env.example .env` (Windows).
3. **Add your documents.** Copy your files into the `documents/` folder.
4. **Start the agent.** Make sure Docker Desktop is open and running, then in the terminal run:
   ```
   docker compose up
   ```
   The first run takes a few minutes while it builds. Leave the window open: the agent runs while it is open. (Use `docker compose up -d` to run it in the background.)
5. **Check that it works.** Open <http://localhost:8000/.well-known/agent-card.json> in your browser. You should see a block of text with your agent's name. That address (`http://localhost:8000`) is the one you register in the central A2A platform.

Always start the agent with `docker compose up`, because the agent receives your settings from the `.env` file through Docker.

**Changed `.env`?** Run `docker compose up -d` again so the agent restarts with the new settings. `docker compose restart` does NOT pick up `.env` changes; use it only after changing files in `documents/`.

## The `.env` settings

| Variable | Required | What to put |
|---|---|---|
| `AGENT_NAME` | yes | The name other agents and users see. |
| `AGENT_DESCRIPTION` | yes | One sentence on what the agent answers questions about. |
| `LLM_MODEL` | yes | Provider and model, e.g. `anthropic/claude-sonnet-5-5`, `openai/gpt-4o` or `gemini/gemini-2.5-flash`. |
| `ANTHROPIC_API_KEY` | if you use `anthropic/...` | Your Anthropic key. |
| `OPENAI_API_KEY` | if you use `openai/...` | Your OpenAI key. |
| `GEMINI_API_KEY` | if you use `gemini/...` | Your Gemini key. |
| `PUBLIC_URL` | no | The address where the agent can be reached. Default `http://localhost:8000`. **If you run the agent on a server, set it to the address the central platform will actually use** (e.g. `https://agent.mycompany.com`), otherwise the agent tells callers the wrong address. |
| `AGENT_API_KEY` | no | A secret password callers must send. See "Security" below. |

Only fill in the API key for the provider you chose in `LLM_MODEL`.

## Your documents

- Supported types: **PDF, DOCX, MD, TXT** (other files are ignored).
- Put them in the `documents/` folder (subfolders are fine).
- After adding, changing or deleting files, restart the agent so it picks up the changes (this is for documents only, not for `.env`):
  ```
  docker compose restart
  ```
  Only new or changed files are re-read, so restarts are quick.
- The `docs/` folder in this project holds developer notes. It is not for you.

## Try it from the command line (optional)

This step is optional and the command below works on Mac, Linux and Git Bash (not in Windows cmd/PowerShell). With the agent running, it sends the agent a question:

```
curl -X POST http://localhost:8000/ \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"message/send","params":{"message":{"kind":"message","messageId":"1","role":"user","parts":[{"kind":"text","text":"What is this documentation about?"}]}}}'
```

If you set `AGENT_API_KEY`, add this line before `-d`:

```
  -H "Authorization: Bearer YOUR_AGENT_API_KEY" \
```

The agent supports both A2A v0.3 (`message/send`, used above) and v1.0 (`SendMessage`) at the same address.

## Register it in the central A2A platform

In the platform, add a new agent and give it the base URL, e.g. `http://localhost:8000` (or your `PUBLIC_URL`). The platform reads the agent card from `/.well-known/agent-card.json` by itself. If you set `AGENT_API_KEY`, give the platform that key as a bearer token.

## Security

If `AGENT_API_KEY` is empty, **anyone who can reach the agent can ask it questions** about your documents. That is fine on your own computer, but on a server set `AGENT_API_KEY` to a long random secret. Callers must then send `Authorization: Bearer <key>`; requests without it get `Unauthorized` (HTTP 401). The agent card stays public.

Your documents are sent in small excerpts to the AI provider you chose, to produce answers.

## Troubleshooting

| What you see | What it means / what to do |
|---|---|
| `Configuration error: Missing <VAR> in your .env file` | The named setting is empty or missing in `.env`. Fill it in and run `docker compose up` again. |
| `Configuration error: LLM_MODEL must look like provider/model, e.g. anthropic/claude-sonnet-5-5` | Fix `LLM_MODEL` so it has the form `provider/model`. |
| `Configuration error: <msg>` | Any other message after this prefix describes the `.env` problem; fix it as stated. |
| `No documents found in documents/. Add files and restart.` (in the logs) | The folder is empty or has no supported files. Add files, then `docker compose restart`. Until then the agent replies "No documentation is loaded." |
| `The LLM provider returned an error: <reason>` | The AI provider refused or failed the request. The reason usually says why: wrong or expired API key, no credit, wrong model name, or a temporary outage. |
| `The model returned an empty response` | The provider answered with nothing. Ask again; if it repeats, try another `LLM_MODEL`. |
| `Unauthorized` (HTTP 401) | `AGENT_API_KEY` is set and the caller did not send the matching `Authorization: Bearer` header. |
| Port 8000 already in use | Stop the other program using port 8000, then run `docker compose up` again. |
| `env file .env not found` | You skipped step 2: copy `.env.example` to `.env`. |

If the settings are wrong, the agent tries to start a few times, then stays stopped with the error as the last line. Fix `.env` and run `docker compose up` again. If the terminal is still attached and busy, press Ctrl+C first.

To see what the agent is doing: `docker compose logs`. To stop it: `docker compose down`.
