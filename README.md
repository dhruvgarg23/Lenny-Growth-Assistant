# The Lenny Growth Assistant

Grounded conversational assistant over **Lenny’s Podcast transcripts** — chat with citations, **Ship 30 for 30 essays (~1,250 words)**, and **rendered Markdown/HTML artifacts** side-by-side.

Built for the Forward Deployed Engineer brief: one-command Docker, flexible LLM toggle (Ollama default, Anthropic/OpenAI optional), pgvector RAG, sandboxed artifacts, and handoff-ready docs.

![Stack](https://img.shields.io/badge/FastAPI-009688?style=flat) ![React 19](https://img.shields.io/badge/React-19-61DAFB) ![pgvector](https://img.shields.io/badge/pgvector-HNSW-blue) ![Ollama](https://img.shields.io/badge/Ollama-llama3.1:8b-black)

---

## Architecture at a glance

```
React 19 + Vite + Tailwind v4          FastAPI (app/main.py) ──► Pi LLM Wrapper (Ollama / Anthropic / OpenAI)
  |  /api/sessions  /api/config        ->  Sessions (Postgres)
  |  /api/sessions/{id}/chat/stream (SSE) -> hybrid retrieval (pgvector HNSW + tsv RRF k=60) -> grounded prompts
  |  Artifact Viewer (sandboxed iframe)    -> Ship30 skill (5 pillars) + artifact sanitizer (bleach/DOMPurify)
  |
  Postgres 16 + pgvector (documents/chunks, sessions/messages, HNSW + GIN)
  Ollama (host.docker.internal:11434) — llama3.1:8b + nomic-embed not needed (local MiniLM)
```

See `architecture.md` for DB schema, API contracts, ingestion flow, and security model. See `PRD.md` for discovery brief and `design.md` for UX.

---

## Prerequisites

- **Docker Desktop** (Compose v2) — for one-command run (Postgres + backend + frontend)
- **Node 20+ / npm** — for local frontend dev (optional if using Docker)
- **Python 3.11+** — for backend local dev / ingest
- **Ollama** (for local demo) — `brew install ollama` then `ollama serve` + `ollama pull llama3.1:8b`

Check: `docker --version`, `ollama --version`, `python3 --version`, `node --version`

---

## Quick Start (Docker — recommended)

```bash
# 1. Env — no secrets needed for Ollama demo
cp backend/.env.example backend/.env
# (optional) edit backend/.env: set LLM_PROVIDER, OLLAMA_MODEL, etc. Cloud keys optional

# 2. Run (builds pgvector DB, backend, frontend)
docker compose up --build
# Frontend → http://localhost       (nginx, proxied /api → backend)
# Backend  → http://localhost:8000  (FastAPI docs at /docs)
# Health   → http://localhost:8000/api/health

# 3. Ingest transcripts (first time, inside Docker or host)
# Host (with local Postgres via Docker):
DATABASE_URL=postgresql://lenny:lenny@localhost:5432/lenny_growth python backend/scripts/ingest.py
# Or exec inside backend container:
docker compose exec backend python scripts/ingest.py --reset
# Dry check:
python backend/scripts/ingest.py --dry-run --limit 3
```

**One-command startup:** after first ingest, `docker compose up` is enough; data persists in `pgdata` volume.

**To stop:** `docker compose down` (add `-v` to reset DB)

---

## Local dev (without Docker)

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # then ensure DATABASE_URL points to localhost
# Start Postgres manually (or via docker compose up postgres -d)
alembic -c alembic.ini upgrade head
uvicorn app.main:app --reload --port 8000
# → http://localhost:8000/docs

# Ingest (needs sentence-transformers, first run downloads ~90MB)
python scripts/ingest.py --limit 5   # smoke 5 files
python scripts/ingest.py             # full 60 files

# Frontend
cd frontend
npm install
npm run dev
# → http://localhost:5173  (proxies /api → :8000)
```

---

## Environment variables

See `.env.example` and `backend/.env.example` (identical). Safe defaults, never commit real secrets:

| Var | Default | Purpose |
|-----|---------|---------|
| `LLM_PROVIDER` | `ollama` | `ollama` \| `anthropic` \| `openai` — visible in UI badge |
| `OLLAMA_BASE_URL` | `http://host.docker.internal:11434` | Ollama HTTP (Docker uses `host-gateway`) |
| `OLLAMA_MODEL` | `llama3.1:8b` | Chat model for Ollama |
| `EMBEDDING_PROVIDER` | `local` | `local` \| `ollama` \| `openai` |
| `EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | 384d, batched 32 |
| `VECTOR_DIM` | `384` | Must match embedding model |
| `DATABASE_URL` | `postgresql+asyncpg://lenny:lenny@postgres:5432/lenny_growth` | Override to `localhost` for host runs |
| `ANTHROPIC_API_KEY` | `` | Optional — enables `anthropic` provider |
| `OPENAI_API_KEY` | `` | Optional — enables `openai` provider |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `800` / `100` | RecursiveCharacterTextSplitter |
| `RETRIEVAL_K` / `CANDIDATE_K` | `8` / `30` | Hybrid top-k |
| `RAG_MIN_CONFIDENCE` | `0.10` | Abstain threshold on RRF score |
| `CORS_ORIGINS` | `http://localhost:5173,http://localhost:80,http://localhost` | CSV |

**Switching providers:** set `LLM_PROVIDER` + key, restart backend, UI badge updates. Health `GET /api/config` and `GET /api/health` report selected + `ollama_reachable`. If selected provider unavailable, `POST /api/sessions/{id}/chat/stream` emits SSE `error` with remediation, not 500.

---

## API

Base: `/api` (via nginx `/api → backend:8000/api`)

- `GET /api/health` → `{status, version, provider, ollama_reachable, db_ok, active_sessions}`
- `GET /api/config` → `{provider, retrieval, llm_models}`
- `POST /api/sessions` `{title?}` → `{id, title, user_id, created_at, updated_at, message_count}`
- `GET /api/sessions` → list (50, desc updated_at)
- `GET /api/sessions/{id}` / `DELETE /api/sessions/{id}`
- `GET /api/sessions/{id}/messages` → ordered messages
- `POST /api/sessions/{id}/chat/stream` (SSE) body `{message, mode: chat|ship30|artifact, artifact_type?: markdown|html}` — events: `status → sources → token* → artifact? → done` or `error`
- `POST /api/sessions/{id}/chat` (non-stream) → `{content, sources, mode, artifact, confidence}`

**Health & error contracts:** structured `{detail}` on 4xx/5xx, `X-Request-ID`. See `backend/tests/test_health.py:1`.

---

## Knowledge base — ingestion

- **Source:** `LennysNewsletter/lennys-newsletterpodcastdata` — starter pack 50 podcasts + 10 newsletters vendored at `backend/data/source/` with `index.json` trace.
- **Flow:** `scripts/ingest.py` reads `index.json`, parses frontmatter markdown, chunks `RecursiveCharacterTextSplitter(800/100)` with header `"{title} — guest: {guest}"` prepended (improves retrieval), embeds `all-MiniLM-L6-v2` 384d normalized, batch 32, inserts `documents` + `chunks` (vector + tsv), checksum incremental, trigger populates `tsv`.
- **Trace:** every chunk retains `source_path` enumerable via citations `[source: podcasts/jen-abel-3.md]`.
- **Refresh:** `python scripts/ingest.py --reset` re-embeds; incremental on checksum change; cron not scheduled (manual).

See `architecture.md` for schema and hybrid SQL.

---

## Frontend — artifact viewer

- Chat 60% / artifact 40% split on desktop (drawer on mobile).
- Markdown → `react-markdown + remark-gfm` (safe).
- HTML → sanitized client + server (`bleach` + `DOMPurify`), rendered `srcDoc` in `<iframe sandbox="allow-scripts allow-popups" referrerPolicy="no-referrer">` **without** `allow-same-origin`. See `architecture.md` “Security”.

---

## Ollama — local demo (mandatory)

```bash
ollama serve &
ollama pull llama3.1:8b
ollama list
# Health should turn green in UI badge: OLLAMA • reachable
curl http://localhost:11434/api/tags
```

If Ollama not running, chat stream returns `error: Ollama is not reachable at OLLAMA_BASE_URL…` with guidance. Docker backend uses `host.docker.internal:11434` via `extra_hosts: host-gateway`.

---

## Tests

```bash
cd backend
pip install -r requirements.txt
pytest -v
# → 23 passed (health, routing, RRF, artifacts, prompts)
# manual UI checklist: see Tests section in PRD.md / below
```

**Manual UI test plan (2 min):**

1. Start `docker compose up`, wait `api/health: db_ok true`
2. Open `http://localhost`, click + New chat, send “How to improve onboarding activation?” → streaming tokens + sources chips
3. Send out-of-scope “Capital of Mars?” → abstains: “I don’t have support…”
4. Switch mode → Ship30, send “How Lenny guests think about retention loops” → ~1,200-word essay with bold subheads + bullets
5. Switch mode → Artifact html, send “HTML one-pager comparing PLG vs sales-led” → artifact pane renders, iframe sandbox attr inspectable, no script execution
6. Resize to 375px → drawer stacks, keyboard nav, Enter+Shift behavior
7. Stop Ollama → chat shows structured error, no crash

---

## Troubleshooting

| Symptom | Fix |
|--------|-----|
| `DB health failed` / `status degraded` | Check `docker compose ps postgres`, `docker compose logs postgres`; ensure `DATABASE_URL` matches compose (`postgres:5432` inside Docker, `localhost:5432` on host). Run `alembic upgrade head`. |
| `Ollama is not reachable` | `ollama serve` + `ollama pull llama3.1:8b`; curl `http://localhost:11434/api/tags`. In Docker, ensure `extra_hosts: host.docker.internal:host-gateway`. |
| Ingest `ModuleNotFoundError sentence_transformers` | `pip install -r requirements.txt` (downloads torch ~400MB). Use `--limit 3` for smoke. |
| Frontend `vite build` fails `ENOENT` | Run `npm install --prefix frontend`, then `npm --prefix frontend run build`. |
| `vector(384)` mismatch | `VECTOR_DIM` must equal embedding model dim. After change, `python scripts/ingest.py --reset`. |
| Artifacts not rendering | Check browser console, inspect `iframe[sandbox]` lacks `allow-same-origin`; HTML sanitizer blocks `script/on*` — see logs. |
| Port 5432/8000/80 busy | `lsof -i :8000` then change ports in `docker-compose.yml` + `vite.config.js` proxy. |

---

## Project structure

```
Growth_Assistant/
├── docker-compose.yml      # postgres pgvector + backend + frontend
├── .env.example / backend/.env.example
├── backend/
│   ├── app/main.py, config.py, middleware/request_id.py
│   ├── app/routes/{health,sessions,chat}.py
│   ├── app/services/{database,embeddings,llm,retrieval,prompts,artifacts,agent_router}.py
│   ├── app/skills/ship30/SKILL.md
│   ├── app/models/{db, schemas}.py
│   ├── scripts/ingest.py, data/source/{podcasts,newsletters,index.json}
│   ├── alembic/{env.py,versions/001_initial.py}, alembic.ini
│   └── tests/{test_health,test_routing,test_retrieval,test_artifacts,test_prompts}.py
├── frontend/
│   ├── src/{App.jsx, components/{ChatPane,ArtifactViewer,SessionSidebar}, lib/api.js}
│   ├── vite.config.js, index.html, package.json
│   └── Dockerfile, nginx.conf
├── PRD.md, design.md, architecture.md
└── agent_transcripts/
```

---

## Handoff — extend this system

- **Add cloud provider:** set `ANTHROPIC_API_KEY`, change `LLM_PROVIDER=anthropic` — `app/services/llm.py:1` handles streaming uniformly.
- **Swap embedding model:** change `EMBEDDING_MODEL` + `VECTOR_DIM`, ingest `--reset`, HNSW rebuild is automatic.
- **Custom skill:** add `app/skills/<name>/SKILL.md` + route in `agent_router.py:1`.
- **Evals:** see `architecture.md` “Evaluation” — 50 Q set, recall@k + groundedness harness.

**Demo video & submission:** upload 2–3 min Loom with camera, show Ollama toggle + streaming + artifact, cover one tradeoff (local 384d vs cloud latency/cost) — link in submission form https://forms.gle/LgotDHNVxW1mbzNE7 (due 25/08/26 EOD).

---

## License & attribution

Transcripts property of Lenny Rachitsky, used via public starter pack `LennysNewsletter/lennys-newsletterpodcastdata:52`. MIT for code.

