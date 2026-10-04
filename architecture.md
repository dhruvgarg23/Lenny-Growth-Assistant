# Architecture

## The Lenny Growth Assistant

## 1. System Architecture

```text
React 19 Frontend (Vite)
       │
       │ HTTP / Server-Sent Events (SSE)
       ▼
FastAPI Backend Service
  ├── Session Management Service
  ├── Chat Orchestration Service
  ├── Intent Router
   ├── Retrieval Service (Hybrid RRF)
   ├── LLM Facade (Ollama / Anthropic / Groq adapters)
  └── Artifact Sanitization Service
       │
       ├────────────────────────────────┐
       ▼                                ▼
PostgreSQL 16 + pgvector       Pluggable Model Providers
  ├── documents                  ├── Ollama (Local llama3.1:8b)
  ├── chunks                     ├── Anthropic (Cloud Claude 3.5)
  ├── sessions                   └── Groq (Cloud Llama 3.3)
  └── messages
```

## 2. Component Boundaries

### Frontend (`frontend/src/`)
- **Responsibilities:** Session state management, SSE stream consumption, message timeline rendering, interactive source citation cards, split-pane artifact canvas, and live model/provider selection.
- **Technologies:** React 19, Vite, Tailwind CSS v4, Lucide React, DOMPurify.

### FastAPI Service (`backend/app/`)
- **Responsibilities:** Request lifecycle, Pydantic input/output validation, CORS headers, distributed request correlation ID injection (`X-Request-ID`), structured logging, and SSE streaming.

### Skill Prompts (`backend/app/services/prompts.py`, `backend/app/skills/ship30/`)
- **Responsibilities:** Mode-specific prompt assembly (grounded chat, Ship 30 essay, artifact) and the 5-pillar Ship 30 for 30 playbook. Multi-turn tool calling does not exist yet — a future agent loop belongs behind the conversation module's seam as an adapter, not as a parallel pipeline.

### Retrieval Service (`backend/app/services/retrieval.py`)
- **Responsibilities:** `HybridRetrieval` — dense vector cosine search (`pgvector`), lexical full-text search (`tsvector`), Reciprocal Rank Fusion (RRF) score merging — constructed with injected session, embed function, and result sizes; returns typed `Passage` tuples. Serve-time and ingest-time embedding share one path (`app/services/embeddings.py`).

### LLM Facade (`backend/app/services/llm/`)
- **Responsibilities:** Stream-only facade over per-provider adapters (`ollama.py`, `groq.py`, `anthropic.py`); shared telemetry (TTFT, chunk counts), `<think>` token filtering, upstream error categorisation.

### Artifact Service (`backend/app/services/artifacts.py`)
- **Responsibilities:** Safe extraction of code blocks, HTML sanitization via Bleach and CSSSanitizer (tinycss2), attribute allowlisting, and security warning reporting.

## 3. Database Schema

```text
┌─────────────────────────────────────────┐
│               documents                 │
├─────────────────────────────────────────┤
│ id           VARCHAR(64) PRIMARY KEY    │
│ title        VARCHAR(255) NOT NULL      │
│ source_path  VARCHAR(512) NOT NULL      │
│ guest        VARCHAR(255)               │
│ content      TEXT NOT NULL              │
│ checksum     VARCHAR(64) NOT NULL       │
│ created_at   TIMESTAMPTZ DEFAULT now()  │
│ updated_at   TIMESTAMPTZ DEFAULT now()  │
└────────────────────┬────────────────────┘
                     │ 1
                     │
                     │ N
┌────────────────────▼────────────────────┐
│                chunks                   │
├─────────────────────────────────────────┤
│ id           VARCHAR(64) PRIMARY KEY    │
│ document_id  VARCHAR(64) FK REFERENCES  │
│ chunk_index  INT NOT NULL               │
│ content      TEXT NOT NULL              │
│ embedding    VECTOR(384) NOT NULL       │
│ tsv          TSVECTOR NOT NULL          │
│ metadata     JSONB DEFAULT '{}'         │
│ created_at   TIMESTAMPTZ DEFAULT now()  │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│               sessions                  │
├─────────────────────────────────────────┤
│ id           VARCHAR(64) PRIMARY KEY    │
│ user_id      VARCHAR(64)                │
│ title        VARCHAR(255) NOT NULL      │
│ created_at   TIMESTAMPTZ DEFAULT now()  │
│ updated_at   TIMESTAMPTZ DEFAULT now()  │
└────────────────────┬────────────────────┘
                     │ 1
                     │
                     │ N
┌────────────────────▼────────────────────┐
│               messages                  │
├─────────────────────────────────────────┤
│ id           VARCHAR(64) PRIMARY KEY    │
│ session_id   VARCHAR(64) FK REFERENCES  │
│ role         VARCHAR(32) NOT NULL       │
│ content      TEXT NOT NULL              │
│ mode         VARCHAR(32) DEFAULT 'chat' │
│ meta         JSONB DEFAULT '{}'         │
│ created_at   TIMESTAMPTZ DEFAULT now()  │
└─────────────────────────────────────────┘
```

### Database Indexes
- **Vector Search:** HNSW index on `chunks.embedding` using cosine distance (`vector_cosine_ops` with $m=16, ef\_construction=64$).
- **Lexical Search:** GIN index on `chunks.tsv` for full-text search.
- **Relational Lookups:** B-Tree index on `chunks.document_id`, `messages.session_id`, and `messages.created_at`.

## 4. Ingestion Flow

```text
Source Transcripts (Markdown)
             │
             ▼
Parse Frontmatter & index.json Metadata
             │
             ▼
Recursive Character Splitting (800 chars / 100 overlap)
             │
             ▼
Prepend Context Header ("{title} — guest: {guest}")
             │
             ▼
Compute MD5 Checksum (Skip unchanged documents)
             │
             ▼
Batch Embeddings Generation (sentence-transformers/all-MiniLM-L6-v2, 384d)
             │
             ├──────────────────────────┐
             ▼                          ▼
Insert Dense Vector (pgvector)   Generate Lexical TSVector (to_tsvector)
             │                          │
             └────────────┬─────────────┘
                          ▼
             Commit to PostgreSQL Database
```

- Incremental ingestion compares document MD5 checksums to skip unchanged files.
- Running `scripts/ingest.py --reset` truncates tables and performs a fresh rebuild.

## 5. Retrieval Flow (Hybrid RRF)

```text
User Query
    │
    ├──────────────────────────────────────────────┐
    ▼                                              ▼
Generate Query Embedding (384d)         Normalize Search Query Text
    │                                              │
    ▼                                              ▼
Dense Vector Search (HNSW Cosine)       Full-Text Lexical Search (ts_rank_cd)
Top 30 Candidates                              Top 30 Candidates
    │                                              │
    └──────────────────────┬───────────────────────┘
                           ▼
          Reciprocal Rank Fusion (RRF, k = 60)
          Score = Σ [ 1 / (60 + Rank_vector) + 1 / (60 + Rank_lexical) ]
                           │
                           ▼
          Select Top K Results (Default K = 8)
                           │
                           ▼
          Confidence Check (Score ≥ 0.01)
          ├─► Pass: Inject chunks into grounding prompt
          └─► Fail: Trigger polite out-of-scope abstention
```

## 6. Agent Routing

```text
User Request
     │
     ▼
Intent Router (`app/services/agent_router.py`)
     │
     ├── Explicit Mode / Trigger: "ship 30", "essay", "1250 words"
     │   └──► Route: `ship30` (Executes Ship 30 for 30 Skill)
     │
     ├── Explicit Mode / Trigger: "artifact", "html", "render", "markdown doc"
     │   └──► Route: `artifact` (Generates sanitized Markdown/HTML artifact)
     │
     └── Default Mode
         └──► Route: `chat` (Executes Grounded Conversational Q&A)
```

The router prevents every request from being handled as a generic chat completion, directing requests to dedicated prompt and tool pipelines.

## 7. Skills

Mode-specific behavior is prompt assembly, not tool calling — no agent runtime
or tool schemas exist in the codebase (a previous `backend/app/agent/` duplicate
pipeline was deleted as uncalled dead code; see ADR-worthy note below). The
conversation module (`backend/app/services/conversation.py`) selects prompts by
explicit mode:

- **chat** → `build_grounded_messages`: grounded Q&A with citations.
- **ship30** → `build_ship30_messages`: applies the 5-pillar Ship 30 for 30
  playbook ([`backend/app/skills/ship30/SKILL.md`](backend/app/skills/ship30/SKILL.md))
  — ~1,250-word atomic essay, high-voltage headline, 1/3/1 rhythm, bold
  subheads, bulleted frameworks, grounded citations.
- **artifact** → `build_artifact_messages`: generates Markdown or HTML for the
  split-pane viewer; HTML is sanitized by `backend/app/services/artifacts.py`.

A future multi-turn tool-calling loop (e.g. `search_transcripts`,
`render_artifact`) belongs behind the conversation seam, reusing its retrieval,
abstention, and persistence rather than re-implementing them.

## 8. Model Provider Architecture

```text
                        FastAPI Chat Service
                                 │
                                 ▼
                     LLM Provider Abstraction
                      (`backend/app/services/llm/facade.py`)
                                 │
         ┌───────────────────────┼───────────────────────┐
         ▼                       ▼                       ▼
   Local Provider          Cloud Provider          Cloud Provider
   Ollama Service         Anthropic Claude          Groq Service
  (Async HTTP API)     (AsyncAnthropic SDK)     (AsyncOpenAI Client)
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 ▼
                    Unified Async Token Stream
```

The LLM abstraction encapsulates provider-specific communication formats, streaming protocols, and authentication headers behind a single asynchronous generator interface.

## 9. Model Toggle

The system supports dynamic model selection via environment variables (`.env`) and live runtime switching via the API (`POST /api/config/switch`) and UI dropdown.

- **`ollama`:** `llama3.1:8b` (Default local evaluation runner)
- **`anthropic`:** `claude-3-5-sonnet-20241022`, `claude-3-5-haiku-20241022`, `claude-3-opus-20240229`
- **`groq`:** `llama-3.3-70b-versatile`, `openai/gpt-oss-120b`, `llama-3.1-8b-instant`

*Failure behavior:* There is intentionally **no automatic silent fallback**. If a chosen provider is unavailable (e.g. Ollama daemon stopped or missing API key), the system immediately returns an explicit, structured error with remediation steps.

## 10. Streaming Architecture

```text
Client (Browser EventSource)
       │
       │ POST /api/sessions/{id}/chat/stream
       ▼
FastAPI Endpoint
       │
       ├──► event: status    {"stage": "retrieving", "message": "Searching Lenny transcripts…"}
       ├──► event: sources   {"sources": [...], "confidence": 0.032}
       ├──► event: status    {"stage": "generating", "message": "Drafting answer…"}
       ├──► event: token     {"delta": "According to Elena Verna..."}  (Repeated)
       ├──► event: artifact  {"artifact": {"type": "html", "content": "...", "warnings": []}}
       └──► event: done      {"latency_ms": 1420, "request_id": "req-123", ...}
```

If an exception occurs during streaming, an `event: error` envelope is dispatched containing the error classification and request ID.

## 11. API Endpoints

### Health & Configuration
- `GET /api/health` — Returns status of PostgreSQL database, Ollama reachability, active provider, and active session count.
- `GET /api/config` — Returns allowed models and non-sensitive runtime configuration.
- `POST /api/config/switch` — Switches active provider and model at runtime.

### Sessions
- `POST /api/sessions` — Creates a new conversation session.
- `GET /api/sessions` — Lists recent sessions ordered by `updated_at`.
- `GET /api/sessions/{id}` — Retrieves session metadata.
- `DELETE /api/sessions/{id}` — Deletes a session and cascades deletion to all associated messages.
- `GET /api/sessions/{id}/messages` — Retrieves ordered conversation history for a session.

### Chat
- `POST /api/sessions/{id}/chat/stream` — SSE streaming endpoint emitting status, sources, token deltas, and artifact payloads. Streaming is the only chat transport; the conversation pipeline (`app/services/conversation.py`) is transport-agnostic and tested through its own seam.

## 12. Request Tracing

Every incoming HTTP request is assigned a unique `X-Request-ID` by `RequestIdMiddleware` (or adopts an upstream header if provided). This ID is:
- Attached to the request state.
- Injected into all structured log entries.
- Returned in the HTTP response headers.
- Included in SSE `done` and `error` payloads for deterministic debugging.

## 13. Security Model

### HTML Artifact Sandbox
Generated HTML is treated as untrusted third-party code. Isolation is achieved through a defense-in-depth pipeline:
1. **Server-Side Sanitization:** `bleach` and `tinycss2` strip dangerous tags (`<script>`, `<iframe>`, `<object>`, `<embed>`, `<form>`, `<meta>`), remove all inline event handlers (`on*`), and restrict CSS properties.
2. **Client-Side Sanitization:** `DOMPurify` runs on the markup before rendering.
3. **Iframe Isolation:** The rendered document is mounted inside an `<iframe>` configured with:
   ```html
   <iframe sandbox="allow-scripts" srcdoc="..." />
   ```
   Crucially, `allow-same-origin` is **omitted**. This enforces a `null` origin, preventing the rendered document from reading application cookies, local storage, or accessing the parent DOM.

### Secrets Management
- All credentials (`ANTHROPIC_API_KEY`, `GROQ_API_KEY`, `DATABASE_URL`) are read exclusively from environment variables.
- The `GET /api/config` endpoint exposes only boolean configuration flags (`anthropic_configured`, `groq_configured`) and never leaks raw keys.
- `.env` files are excluded from source control via `.gitignore`.

### Session Isolation
- All message read and write operations are strictly scoped by `session_id`.
- Foreign key constraints ensure clean cascade deletion when sessions are removed.

## 14. Deployment Topology

```text
Host Environment
 ├── Ollama Daemon (Port 11434)
 │
 └── Docker Compose Network
      ├── frontend (Nginx, Port 80)
      │    └── Proxies /api/* ──► backend:8000
      ├── backend (FastAPI, Port 8000)
      │    ├── Connects to PostgreSQL:5432
      │    └── Connects to Ollama via host.docker.internal:11434
      └── postgres (PostgreSQL 16 + pgvector, Port 5432)
```

## 15. Health and Failure Handling

The `GET /api/health` check monitors:
1. **Database Health:** Executes `SELECT 1` to verify connection pool responsiveness.
2. **Ollama Reachability:** Queries `GET /api/tags` on the Ollama endpoint to verify the local daemon is active.
3. **Graceful Degradation:** If Ollama is offline or an API key is missing, the chat endpoint emits a structured `PROVIDER_UNREACHABLE` or `AUTH_FAILURE` SSE event with explicit instructions to resolve the issue.

## 16. Performance Considerations

- **Approximate Nearest Neighbor Search:** HNSW indexing avoids full vector table scans during retrieval.
- **Candidate Pool Filtering:** Vector and lexical queries retrieve top 30 candidates before computing Reciprocal Rank Fusion, keeping memory usage minimal.
- **Batched Ingestion:** Ingestion processes embeddings in configurable batches (default: 32 chunks) utilizing CPU vectorization.
- **Streaming Responsiveness:** Tokens stream immediately as generated, maintaining sub-1.5s time-to-first-token.

## 17. Evaluation Strategy

The architecture supports automated evaluation across six core dimensions:
- **Retrieval Relevance:** Recall@K and Precision@K against gold PM/Growth query sets.
- **Groundedness:** Proportion of claims directly supported by retrieved transcript context.
- **Abstention Behavior:** Correct abstention rate on out-of-scope queries (e.g. general trivia or non-PM questions).
- **Format Compliance:** Word count and structural adherence for Ship 30 essays.
- **Sanitization Efficacy:** Block rate against XSS injection test vectors in generated artifacts.
- **Latency & Throughput:** TTFT and token generation rate across local and cloud providers.

## 18. Known Limitations

- **Corpus Ingestion:** Transcripts are ingested via a manual CLI trigger (`scripts/ingest.py`) rather than an automated live scraping pipeline.
- **Single-Tenant Scope:** Designed for local forward-deployment evaluation without multi-user auth or role-based access controls.
- **No Automatic Provider Fallback:** Selected providers fail explicitly rather than silently masking issues by routing to alternative models.
- **Fixed Embedding Dimensions:** The vector store is optimized for 384-dimensional embeddings (`all-MiniLM-L6-v2`); changing embedding models requires running `ingest.py --reset`.
