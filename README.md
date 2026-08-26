# The Lenny Growth Assistant

A full-stack, AI-powered conversational web application that ingests transcripts from Lenny's Podcast and Newsletter, provides strictly grounded answers with source citations, generates structured Ship 30 for 30 essays, and renders interactive Markdown and HTML/CSS artifacts in a sandboxed side-by-side viewer. Designed for forward-deployment evaluation with one-command local startup via Ollama, pgvector hybrid retrieval, and optional cloud model switching (Anthropic Claude, Groq).

## Features

- **Grounded conversational Q&A:** Synthesizes answers directly from podcast transcripts with guest attribution and confidence checks.
- **Source citations:** Transparent excerpts and document paths for every factual claim.
- **Ship 30 for 30 essays:** Dedicated content skill generating ~1,250-word atomic essays adhering to the 5 writing pillars.
- **Markdown/HTML artifacts:** Generates formatted memos, comparison matrices, and interactive prototypes.
- **Local Ollama:** Mandatory offline demo runner using `llama3.1:8b` with zero external API dependencies.
- **Anthropic / Groq cloud models:** Pluggable cloud intelligence via Anthropic Claude Agent SDK or Groq.
- **Hybrid retrieval:** Combines pgvector dense embeddings (384d) and lexical TSVector search via Reciprocal Rank Fusion (RRF).
- **Sandboxed artifact rendering:** Multi-layer containment via Bleach sanitization and isolated iframe sandbox.

## Architecture Overview

```text
React (Vite UI)
      ↓
FastAPI (REST / SSE)
      ↓
Agent / Retrieval (Hybrid RRF)
      ↓
PostgreSQL + pgvector
      ↓
Ollama (Local) / Anthropic Claude / Groq (Cloud)
```

For detailed implementation specifications, database schemas, and security models, see [`architecture.md`](architecture.md).

## Prerequisites

- **Docker Desktop** (with Compose v2)
- **Ollama** (for local model evaluation)
- **Node 20+** (for local frontend development)
- **Python 3.11+** (for local backend development)

## Installation

### Clone
```bash
git clone https://github.com/dhruvgarg23/Growth_Assistant.git
cd Growth_Assistant
```

### Environment
```bash
cp backend/.env.example backend/.env
```

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `ollama` | Active model provider (`ollama`, `anthropic`, `groq`) |
| `OLLAMA_MODEL` | `llama3.1:8b` | Local model name for Ollama |
| `OLLAMA_BASE_URL` | `http://host.docker.internal:11434` | Ollama service endpoint |
| `ANTHROPIC_API_KEY` | *(empty)* | Anthropic API key (optional) |
| `ANTHROPIC_MODEL` | `claude-3-5-sonnet-20241022` | Anthropic Claude model (optional) |
| `GROQ_API_KEY` | *(empty)* | Groq API key (optional) |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Groq model (optional) |
| `DATABASE_URL` | `postgresql+asyncpg://lenny:lenny@postgres:5432/lenny_growth` | PostgreSQL connection string |
| `EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | Dense embedding model |
| `VECTOR_DIM` | `384` | Embedding vector dimension |

Full configuration is documented in [`backend/.env.example`](backend/.env.example).

## Local Model Setup (Mandatory Demo)

### Ollama
```bash
ollama serve
ollama pull llama3.1:8b
ollama list
```

Set in `backend/.env`:
```env
LLM_PROVIDER=ollama
OLLAMA_MODEL=llama3.1:8b
```

## Cloud Model Setup (Optional)

### Anthropic
```env
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-api03-...
ANTHROPIC_MODEL=claude-3-5-sonnet-20241022
```

### Groq
```env
LLM_PROVIDER=groq
GROQ_API_KEY=gsk_...
GROQ_MODEL=llama-3.3-70b-versatile
```

*Note: There is no automatic provider fallback; failure produces actionable error guidance in the UI and logs.*

## Run with Docker (Recommended)

```bash
docker compose up --build
```

- **Application:** [http://localhost](http://localhost)
- **Backend:** [http://localhost:8000](http://localhost:8000)
- **API docs:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Health:** [http://localhost:8000/api/health](http://localhost:8000/api/health)

## Ingest Knowledge Base

Inside the running Docker container:
```bash
docker compose exec backend python scripts/ingest.py --reset
```

Smoke test (dry run on 3 files):
```bash
docker compose exec backend python scripts/ingest.py --dry-run --limit 3
```

## Local Development (Without Docker)

### Backend
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# Ensure DATABASE_URL points to localhost:5432
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

## Tests

### Automated Backend Tests
```bash
cd backend
pytest -v
```

### Frontend Build Test
```bash
cd frontend
npm run build
```

## Troubleshooting

| Issue | Cause & Solution |
|---|---|
| **Database unavailable** | Verify PostgreSQL container is running (`docker compose ps postgres`). Ensure `DATABASE_URL` matches your environment (`postgres:5432` in Docker, `localhost:5432` locally). |
| **Ollama unavailable** | Start the daemon with `ollama serve` and verify the model exists (`ollama pull llama3.1:8b`). In Docker, ensure `host.docker.internal` is reachable. |
| **Vector dimension mismatch** | `VECTOR_DIM` must match the embedding model output dimension (384 for `all-MiniLM-L6-v2`). After changing, run `python scripts/ingest.py --reset`. |
| **Artifact not rendering** | Check browser console. Ensure iframe sandbox attributes allow scripts without same-origin. Inspect backend logs for HTML sanitizer rejections. |
| **Port already in use** | If port 80, 8000, or 5432 is occupied, terminate the conflicting process (`lsof -i :8000`) or adjust mapped ports in `docker-compose.yml`. |

## Project Structure

```text
Growth_Assistant/
├── README.md                 # Setup and operational guide
├── PRD.md                    # Product requirements & discovery brief
├── design.md                 # UI/UX specification & interaction states
├── architecture.md           # Technical architecture & contracts
├── docker-compose.yml        # Multi-container orchestration
├── backend/                  # FastAPI service, pgvector RAG, agent tools
│   ├── app/                  # Application code (routes, services, agent)
│   ├── data/source/          # Vendored transcripts & index.json
│   ├── scripts/ingest.py     # Transcript ingestion & chunking script
│   └── tests/                # Automated pytest suite
└── frontend/                 # React 19 + Vite + Tailwind UI
    └── src/                  # Components, chat pane, artifact viewer
```

## Documentation

| Document | Purpose |
|---|---|
| [`README.md`](README.md) | Setup and operation |
| [`PRD.md`](PRD.md) | Product requirements and discovery brief |
| [`design.md`](design.md) | UI/UX principles and interaction states |
| [`architecture.md`](architecture.md) | Technical architecture, schemas, and security |

## Demo

A 2–3 minute video walkthrough covering:
1. Business problem and user persona overview.
2. Live product demo running on **local Ollama** (`llama3.1:8b`).
3. Ship 30 for 30 essay generation & side-by-side Sandboxed HTML/Markdown artifact rendering.
4. Discussion of one technical trade-off (local 384d CPU embeddings vs cloud model latency and cost).

## Attribution & License

Transcripts courtesy of Lenny Rachitsky's podcast and newsletter archive. Code released under the MIT License.
