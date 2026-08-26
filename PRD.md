# Product Requirements Document

## The Lenny Growth Assistant

## 1. Product Overview

The Lenny Growth Assistant is a specialized AI conversational application that turns Lenny’s Podcast and Newsletter transcript archives into an internal intelligence system for product and growth teams. It enables users to ask complex strategic questions, receive strictly grounded answers with transcript citations, draft structured Ship 30 for 30 essays, and generate interactive Markdown or HTML/CSS artifacts inside a sandboxed split-pane viewer without requiring prompt engineering or model infrastructure knowledge.

## 2. User

### Primary Users
- **Product Managers:** Looking for real-world frameworks on activation, retention, pricing, PMF, and prioritization from industry leaders.
- **Growth ICs & Leads:** Designing viral loops, acquisition funnels, PLG motions, and experimentation programs based on practitioner benchmarks.
- **Founders:** Seeking proven operating principles for early-stage scaling, hiring, and product-market fit.

### User Context
Users routinely face high-stakes product decisions where generic LLM advice is too superficial and prone to hallucination. While Lenny's transcript archive contains deep, practitioner-tested answers, manually finding, verifying, and formatting relevant insights into shareable team memos or executive summaries is tedious and time-consuming.

## 3. Problem

### Current Problem
Lenny's Podcast and Newsletter corpus contains world-class product and growth knowledge, but:
- **Information is distributed across transcripts:** 300+ long-form interviews make targeted discovery difficult.
- **Keyword search loses semantic context:** Traditional search engines return word matches without understanding conceptual relationships (e.g. connecting "retention loops" to "cohort decay").
- **Manual synthesis is slow:** Extracting actionable takeaways and writing structured memos requires hours of manual review.
- **Generic LLMs can hallucinate unsupported advice:** Standard cloud chatbots generate plausible-sounding strategies that no guest ever recommended.

### User Pain
- Loss of trust when AI tools invent metrics, quotes, or frameworks.
- Copy-pasting raw text into external docs loses rich formatting, styling, and provenance.
- Context switching between research, synthesis, and presentation formats.

## 4. Product Goals

1. **Make transcript knowledge conversationally accessible:** Provide intuitive conversational exploration over the podcast and newsletter library.
2. **Keep answers grounded in the available corpus:** Attribute claims directly to guest transcripts and fail closed when information is absent.
3. **Make useful outputs directly reusable:** Transform answers into atomic Ship 30 essays or visual HTML/Markdown artifacts on demand.
4. **Provide a reproducible local demo:** Guarantee complete local operability using Ollama without requiring external paid API keys.
5. **Provide clear failure behavior:** Surface structured, actionable remediation messages whenever services, models, or databases encounter issues.

## 5. Success Metrics

| Metric | Target | Evaluation Status |
|---|---|---|
| **Retrieval Relevance** | Recall@8 ≥ 80% on 50 PM/Growth benchmark queries | *Planned benchmark* |
| **Groundedness** | ≥ 85% of responses contain verified citations to source transcripts | *Planned benchmark* |
| **Abstention Correctness** | ≥ 90% precision when abstaining on out-of-scope/unsupported prompts | *Planned benchmark* |
| **Streaming Responsiveness** | Time-To-First-Token (TTFT) < 1.5s locally, < 800ms on cloud | *Measured in local tests* |
| **Test Coverage** | 33 passing automated backend tests covering retrieval, routing, sessions, health, and security | *Measured (33/33 passed)* |
| **Deployment Reproducibility** | One-command startup via `docker compose up --build` | *Verified* |

## 6. Assumptions

- The provided transcript corpus (50 podcast episodes + 10 newsletters) serves as the sole ground truth.
- Evaluators have access to local hardware capable of running Ollama (`llama3.1:8b`).
- Cloud providers (Anthropic Claude, Groq) are optional extensions and must not block baseline local execution.
- All LLM-generated HTML markup is untrusted by default and must be isolated.
- Ingestion is triggered via manual CLI during initial setup rather than continuous background crawling.

## 7. Scope

### In Scope
- Strictly grounded conversational chat with episode/guest source attribution.
- Out-of-scope abstention handling for unsupported topics.
- Ship 30 for 30 essay generation (~1,250 words) adhering to the 5-pillar skill.
- Native split-screen Artifact Viewer supporting Markdown and sanitized HTML/CSS.
- Persistent session and message management in PostgreSQL.
- Hybrid retrieval combining dense vector similarity (pgvector) with lexical full-text search (TSVector) fused via RRF.
- Model switching between local Ollama and cloud providers (Anthropic, Groq).
- Iframe sandboxing with script execution enabled and same-origin access blocked.

### Out of Scope
- User authentication and role-based multi-tenant authorization.
- Automated cron-based transcript scraping and background re-indexing.
- Hosted cloud production deployment (e.g. AWS/GCP/K8s clusters).
- Live web search or external data enrichment.
- Automatic hidden fallback across LLM providers.

## 8. User Flows

### Flow 1: Grounded Q&A
```text
User ──► New / Existing Session ──► Ask Question ──► Retrieve Transcript Context ──► Generate Grounded Answer ──► Display Sources
```

### Flow 2: Ship 30
```text
User ──► Select Ship 30 Mode ──► Submit Topic ──► Retrieve Supporting Transcripts ──► Apply Ship 30 Skill ──► Generate Essay ──► Display Citations
```

### Flow 3: Artifact
```text
User ──► Select Artifact Mode ──► Specify Format ──► Retrieve Context ──► Generate HTML/Markdown ──► Sanitize Markup ──► Render Side-by-Side
```

### Flow 4: Provider Failure
```text
User ──► Select Provider ──► Provider Unavailable ──► Emit Structured Error ──► Display Remediation Guidance
```

## 9. Acceptance Criteria

### Grounded Chat
- Relevant transcript sources and guest attribution chips are displayed with each answer.
- Questions unsupported by the corpus result in an explicit, polite abstention message.
- Full session conversation history persists across page reloads.
- Responses stream incrementally via Server-Sent Events (SSE).

### Ship 30
- Uses a dedicated skill module (`SKILL.md`) rather than an unstructured one-off prompt.
- Produces approximately 1,250 words (1,150–1,350 word range).
- Uses structured headings (`###`), bulleted frameworks, and selective bold emphasis.
- Delivers an actionable takeaway and clear call-to-action.
- All core assertions cite supporting transcript paths.

### Artifacts
- Markdown tables, lists, and formatted text render cleanly.
- HTML/CSS snippets render natively beside the chat conversation.
- Generated HTML is stripped of malicious tags (`<script>`, `<iframe>`, `on*` handlers, `javascript:` URIs).
- Artifact renders inside an `<iframe>` configured with `sandbox="allow-scripts"` and strictly omitting `allow-same-origin`.
- The rendered artifact is isolated from the parent application's DOM, storage, and cookies.

### Deployment
- A single `docker compose up --build` command boots the entire stack.
- Ollama can be used immediately without requiring external API keys.
- The `GET /api/health` endpoint reports PostgreSQL status and Ollama reachability.
- Missing dependencies or stopped daemons yield clear, actionable error messages.

## 10. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| **Weak Retrieval** | Irrelevant or incomplete answers | Hybrid retrieval fusing dense pgvector embeddings and lexical TSVector search via Reciprocal Rank Fusion ($k=60$). |
| **LLM Hallucination** | Loss of user trust | Grounding system prompts enforcing citations + strict confidence threshold abstention. |
| **Ollama Unavailable** | Local demo failure | Pre-flight health checks in UI and API with direct CLI remediation instructions. |
| **Generated HTML Attacks** | Security vulnerability (XSS/exfiltration) | Multi-layer containment: server-side Bleach sanitization + client-side DOMPurify + sandboxed `<iframe>` without `allow-same-origin`. |
| **Large Ingestion Cost** | Slow initial setup | MD5 checksum verification allowing instant incremental skip of unchanged transcripts. |
| **Cloud Dependency** | Deployment fragility | Local-first default using Ollama `llama3.1:8b` requiring no API keys or internet access for chat. |

## 11. Implementation Plan

### Phase 1 — Foundation
- Docker Compose multi-container setup (PostgreSQL + FastAPI + React).
- PostgreSQL schema setup with `pgvector` extension and Alembic migrations.
- Session and message CRUD REST endpoints.

### Phase 2 — Knowledge Layer
- Transcript parser and chunker (`RecursiveCharacterTextSplitter` 800/100).
- Dense embeddings generation (`sentence-transformers/all-MiniLM-L6-v2` 384d).
- PostgreSQL HNSW vector index and TSVector full-text GIN index.
- Reciprocal Rank Fusion (RRF) search implementation.

### Phase 3 — Agent Layer
- Intent router for `chat`, `ship30`, and `artifact` workflows.
- Anthropic Claude Agent SDK integration with tool schemas.
- Local Ollama streaming runner and Groq cloud integration.
- Ship 30 for 30 skill module (`SKILL.md`).

### Phase 4 — Product Experience
- Server-Sent Events (SSE) streaming with status events.
- Source citation chips with excerpt previews.
- Side-by-side split-screen Artifact Viewer with responsive mobile drawer.
- Live model and provider status dropdown in UI header.

### Phase 5 — Hardening
- HTML sanitization pipeline (Bleach, CSSSanitizer, tinycss2).
- Health monitoring endpoint (`/api/health`) and runtime config inspectability (`/api/config`).
- Distributed request tracing (`X-Request-ID`).
- Comprehensive automated test suite (33 tests) and handoff documentation.
