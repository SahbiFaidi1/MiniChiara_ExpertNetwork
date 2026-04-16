## Internal VC expert-network MVP (Slack-first)

Lightweight internal expert-discovery tool for a VC team. **Not a CRM**: it’s optimized for quickly finding “who do we know in X” and keeping profiles current inside Slack.

### Architecture (MVP)
- **Slack app (Bolt for Python)**: slash commands + modals + Block Kit rendering
- **FastAPI**: single HTTP server that Slack calls (and optional `/api/*` endpoints)
- **Postgres (Supabase recommended)**: source of truth for people + embeddings
- **Semantic retrieval**: embed query → pull top candidates → LLM ranks + explains
- **Strict JSON safety**: LLM output is JSON-parsed + Pydantic-validated, and structured fields are overridden from DB (no hallucinated facts)

### Folder structure
```
main.py
config.py
src/
  db.py
  models.py
  repositories/
    people_repo.py
  services/
    profile_builder.py
    embedder.py
    retriever.py
    ranker.py
    slack_blocks.py
  slack/
    commands.py
    modals.py
    views.py
sql/
  schema.sql
requirements.txt
.env.example
```

### Database schema
Run `sql/schema.sql` in Supabase SQL editor (or via `psql`). It creates:
- `public.people` (structured profiles + `searchable_text`)
- `public.person_embeddings` (pgvector `vector(1536)` embeddings; includes a commented float-array fallback)

### Recommended DB for MVP
- **Best**: **Postgres + pgvector** (managed via **Supabase** in production)
- **Fastest to start locally**: run Postgres+pgvector in Docker (included)

Start local DB:

```bash
docker compose up -d
```

Then set:

```bash
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/expert_network
```

Apply schema:

```bash
source .venv/bin/activate
python3 scripts/setup_db.py
```

### Slack commands (implemented)
- `/expert-search <query>`: semantic search with ranked results + “why relevant”
- `/expert-add`: add a person via modal
- `/expert-view <name>`: view a profile (includes Edit/Delete buttons)
- `/expert-delete <name>`: delete via confirmation modal
- `/expert-help`: help

### Environment setup
1. Create a `.env` file from `.env.example`
2. Fill in:
   - **Slack**: `SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET`
   - **DB**: `DATABASE_URL`
   - **OpenAI**: `OPENAI_API_KEY`
   - **PUBLIC_BASE_URL**: your externally reachable URL (ngrok/cloudflared)

### Create the Slack app
In `api.slack.com/apps`:
- **OAuth & Permissions**
  - Bot token scopes: `commands`, `chat:write`, `chat:write.public`, `im:write`
  - Install the app to your workspace and copy the bot token
- **Slash Commands**
  - Create commands:
    - `/expert-search`
    - `/expert-add`
    - `/expert-view`
    - `/expert-delete`
    - `/expert-help`
  - For each command, set **Request URL** to `https://YOUR_PUBLIC_URL/slack/events`
- **Interactivity & Shortcuts**
  - Enable interactivity
  - Set **Request URL** to `https://YOUR_PUBLIC_URL/slack/events`

### Run locally
1. Install deps:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Start the server:

```bash
uvicorn main:app --reload --port 8000
```

3. Expose it publicly (choose one):

```bash
ngrok http 8000
```

Set `PUBLIC_BASE_URL` to your ngrok URL and update Slack Request URLs to:
- `https://YOUR_NGROK_URL/slack/events`

### Import your existing CSV (Affinity export)
This repo includes an importer that maps common Affinity export columns into `people` and generates embeddings.

Dry-run (inspect parsing without writing to DB):

```bash
python3 scripts/import_csv.py --path "/path/to/export.csv" --limit 3 --dry-run
```

Import a small batch:

```bash
python3 scripts/import_csv.py --path "/path/to/export.csv" --limit 200
```

Then test semantic search:

```bash
python3 scripts/cli.py search "Who do we know in energy trading?"
```

### Notes / MVP limitations
- For simplicity the DB layer uses one connection per request; swap to a pool later.
- If `pgvector` isn’t available, use the schema fallback and set `USE_PGVECTOR=false`.

