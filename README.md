# Documentation Agent

An AI-agent that answers questions about **your own documents** (PDF, Word, Markdown, text). Other agents and platforms can chat with it.

No programming needed. You only need:

- [Docker Desktop](https://www.docker.com/products/docker-desktop/), installed and open.
- An API key from an AI company (Anthropic, OpenAI, Google Gemini, on-prem, etc.).

## Start it in 5 steps

1. **Get the project.** Download the ZIP, unzip it, and open a terminal inside the folder. Otherwise, you can also clone it.
2. **Make your settings file.** Copy `.env.example` and name the copy `.env`:
   Then open `.env` in a text editor and fill it in (see the next section).
3. **Add your documents.** Put your files in the `documents/` folder.
4. **Run it.** With Docker Desktop open, type in your terminal of the project:
   ```
   docker compose up
   ```
   The first time takes a few minutes. Keep the window open while the agent is working.
5. **Check it works.** When you see `Uvicorn running on http://0.0.0.0:8000`, open <http://localhost:8000/.well-known/agent-card.json>. If you see text with your agent's name, it works.

## What to write in `.env`

| Setting | What to put |
|---|---|
| `AGENT_NAME` | A name for your agent. |
| `AGENT_DESCRIPTION` | One sentence about what it knows. |
| `LLM_MODEL` | The AI to use, like `anthropic/claude-sonnet-5-5`, `openai/gpt-4o` or `gemini/gemini-2.5-flash`. |
| `LLM_API_KEY` | The key (like a password) your AI company gave you. |
| `PUBLIC_URL` | (Optional) The address where others reach your agent. On your own computer, leave it. On a server, write its real address (e.g. `https://agent.mycompany.com`), or the platform will look for the agent on `localhost` and not find it. |
| `AGENT_API_KEY` | (Optional) A password you invent to protect your agent (not the AI key). Anyone who doesn't send it is refused. Leave empty only on your own computer; on a server, use a long random one. |

Changed `.env`? Run `docker compose up -d` again.

## Your documents

- Works with **PDF, DOCX, MD and TXT** files. Folders inside `documents/` are fine: everything inside them is read too, and answers mention the file with its folder (e.g. `manuals/guide.pdf`).
- Added, changed or deleted a file? Run `docker compose restart`.

## Good to know

- Without `AGENT_API_KEY`, anyone who can reach the agent can ask about your documents. On your own computer that's fine; on a server, set a password.
- Pieces of your documents are sent to the AI company you chose so it can write answers.
- Only add documents you trust.

## If something goes wrong

| What you see | What to do |
|---|---|
| `Missing ... in your .env file` | That setting is empty. Fill it in and run `docker compose up` again. |
| `LLM_MODEL must look like provider/model` | Write it like `anthropic/claude-sonnet-5-5`. |
| `No documents found` | Add files to `documents/`, then `docker compose restart`. |
| `The LLM provider returned an error` | Usually a wrong or expired key, no credit, or a wrong model name. |
| `Unauthorized` | The password (`AGENT_API_KEY`) was missing or wrong. |
| `Port 8000 already in use` | Add `AGENT_PORT=8001` to `.env` (any free number), run `docker compose up` again, and use that number instead of 8000 in the addresses. |
| `env file .env not found` | You skipped step 2. |

Useful commands: `docker compose logs` (see what it's doing) and `docker compose down` (stop it). After restarting your computer, run `docker compose up -d` again.
