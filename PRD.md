# PRD — The Lenny Growth Assistant

## 1. Forward Deployment Brief

### User & problem
**Primary user:** Product/Growth IC and PM leader on a 3–15 person product team. Secondary: founder/PM manager building team rituals.

**Job:** “When I face a product or growth question (onboarding, activation, PLG, pricing, retention) I need a grounded, citable synthesis of what Lenny’s Podcast guests actually said, plus a ready-to-share essay and artifact — without learning prompts or verifying hallucinations.”

**Current pain:**
- 300+ episode corpus (269 in community archive, 50 in public starter) — search is keyword, not semantic, and answers lack provenance.
- Copy-paste into docs loses formatting; generating a memo means manual structuring and citation lookup.
- Teams need both exploratory chat and publishable output, but lack prompt/safety expertise.

**Assistant removes:** search overhead, synthesis labor, formatting, and citation chasing. Users get streaming answers with source chips, a 1,250-word Ship30 essay on demand, and a rendered doc beside chat — all grounded.

### Success metric
- **Product:** Grounded answer rate ≥85% on 50 gold Q set (answer cites ≥1 transcript chunk, 0 unsupported claims per rubric). Out-of-scope abstention precision ≥90%.
- **Operational:** p95 chat latency <2.5s (retrieval + first token) and `db_ok && ollama_reachable` health green on first `docker compose up`. Error paths emit structured `detail` and remediate (“start Ollama…”).

### Assumptions (brief incomplete → recorded choices)
1. Use public starter `LennysNewsletter/lennys-newsletterpodcastdata` (50+10 files + `index.json`) as knowledge base; paid 313 archive is upgrade path.
2. Evaluator runs locally (no paid key) → Ollama mandatory, Anthropic/OpenAI optional fallback, not required for demo.
3. English only, markdown transcripts, no audio ingestion.
4. Single-tenant demo (no auth) — schema reserves `user_id` for future.
5. Local embeddings `all-MiniLM-L6-v2` 384d to keep retrieval free and fast; LLM is the toggle that matters.
6. Corpus static for eval; refresh is manual `ingest.py`, not cron.
7. HTML artifacts are untrusted model output → sandbox containment, not sanitizer perfection.
8. Postgres + pgvector is required (Supabase/Railway noted as alt) for Docker one-command.

### Scope choices

| Included | Intentionally excluded | Why |
|---------|------------------------|-----|
| Chat with session persistence (Postgres), hybrid retrieval, citations, follow-ups, abstain | Multi-tenant auth, per-user RLS, billing | Timebox; schema pluggable |
| Ship 30 for 30 essay skill (dedicated tool, not raw prompt), ~1,250 words | Lens of 30 essays / schedule / Notion tracker | Single-essay requirement only |
| Markdown + HTML artifact generation + split-pane viewer | PDF/PNG export, version history, collaborative edits | Not in brief; viewer proves render+sandbox |
| Model toggle (Ollama + one cloud path), UI-visible, fallback errors | Multiple cloud vendors, auto-fallback | Explicit control > magic |
| Ingest CLI with checksum incremental, `index.json` trace | Real-time crawler, MCP live sync | Keep reproducible; future extension |
| Docker Compose one-command, health, structured logs, resilience | K8s, CI, hosted deploy, Grafana | Operability without heavy infra |
| Tests for retrieval, routing, artifacts, prompts | Heavy integration DB fixtures on CI | Mockable, fast; DB covered by manual smoke |

### Risks & trade-offs

| Risk | Mitigation | Trade-off |
|------|------------|-----------|
| Hallucination | Grounded system prompt + RRF citations + abstain threshold 0.10 + footer sources | Lower coverage on thin topics vs free generation |
| Local-model quality | Temperature 0.2, prompt guards, streaming, note “cloud better for essay polish” | `llama3.1:8b` faster/cheaper but weaker formatting vs Sonnet |
| Latency/cost | Local MiniLM (384d), HNSW, top-k 8 caps LLM tokens, embeddings before DB conn | 384d recall < 1024/1536, but indexer fits RAM |
| Data leakage | Strip transcripts before embed, demo tenant isolation, never log raw context | No PII indexing; minimal logs |
| Unsafe HTML | Sandboxed iframe `sandbox="allow-scripts"` w/o `allow-same-origin`, CSP, bleach+DOMPurify, block `script/on*/form/url()` | Interactive JS allowed, but no cookie/DOM exfil |
| Ollama down / keys missing | `GET /api/health` reports `ollama_reachable`, SSE `error` with remediation, not 500 | Requires evaluator to start Ollama |
| Low corpus coverage | Starter 60 files documented; advise upgrade to full archive | Starter sufficient for eval, not exhaustive |

---

## 2. Flows

### Primary: grounded chat
1. User picks/creates session → types question → POST `/api/sessions/{id}/chat/stream` → SSE `status:retrieving` → hybrid retrieval (embed before DB), `sources` chips → `generating` → streaming `token` → persist `assistant` message → `done`.

### Ship 30 essay
- Trigger: explicit mode `ship30` or phrase `ship 30`/`atomic essay`/`1,250 words` → route → `build_ship30_messages` (headline formula, hook, 3–5 bold subheads, 1/3/1, bullets, bold sentences, CTA) + context → stream essay, footer sources → persists as message with artifact nil but essay as content.

### Artifact
- Trigger: `artifact` + `markdown|html` → `build_artifact_messages` (HTML: style block, no script, cite spans) → generate → sanitize via `artifacts.py` → SSE `artifact` payload → split-pane render (`srcDoc` iframe sandbox or markdown). Mobile drawer.

---

## 3. Acceptance criteria

**3.1 API, sessions, persistence**
- [ ] `POST /api/sessions` creates independent session; `GET /api/sessions/{id}/messages` preserves history
- [ ] Messages persisted in Postgres with `session_id, timestamps, meta.sources`
- [ ] Health `GET /api/health` returns provider + ollama_reachable + db_ok

**3.2 LLM toggle**
- [ ] `LLM_PROVIDER` env switches Ollama/Anthropic/OpenAI without code change; UI badge visible; `GET /api/config` reflects it; missing key yields 503 guidance

**3.3 Knowledge base**
- [ ] Transcripts vendored at `backend/data/source/` with `index.json`; `scripts/ingest.py` chunks 800/100, embeddings 384d, HNSW+GIN, traceable `source_path`
- [ ] Answers cite ` [source: path]` and source chips

**4.1 Grounded chat**
- [ ] Follow-up preserves history; out-of-scope abstains with “I don’t have support…”

**4.2 Ship30**
- [ ] ~1,150–1,350 words, H1 headline, hook, 3–5 bold `###`, bullets, selective bold, takeaway, grounded cites

**4.3 Artifact viewer**
- [ ] Renders md and html beside chat (not just code), sandbox `allow-scripts` w/o `allow-same-origin`, sanitization documented what’s permitted/blocked

**5. Deployment**
- [ ] `cp backend/.env.example backend/.env && docker compose up --build` boots; `.env.example` safe defaults; structured logs; resilience cases handled

---

## 4. Implementation plan

**Phase 0** — Scaffold (this repo): FastAPI, pgvector schema, React — **done** (`856ec67`)

**Phase 1** — Persistence + sessions — **done** (`001_initial.py`)

**Phase 2** — Vendor 60 transcripts + ingest (MiniLM 384d) — **done** (`f921e57`, `scripts/ingest.py:234`)

**Phase 3** — Retrieval hybrid RRF + Pi LLM wrapper SSE + prompts — **done** (`app/services/{retrieval,llm,prompts}`)

**Phase 4** — Ship30 skill + artifact sanitization — **done** (`app/skills/ship30/SKILL.md`, `services/artifacts.py`)

**Phase 5** — Frontend chat/artifact viewer + provider badge — **done** (`frontend/src/App.jsx:234`)

**Phase 6** — Tests (23), docs (this PRD + `design.md` + `architecture.md` + `README.md`), observability, manual checklist — **in progress**

---

## 5. Manual test plan (UI)

See README “Manual UI test plan” — 7 steps: streaming+sources, abstain, Ship30, artifact HTML, resize, a11y, offline Ollama error.

## 6. Evaluation

- **Dataset:** 50 gold Q over vendored corpus (PLG, onboarding, pricing, retention, talent density).
- **Metrics:** recall@8, abstain precision, citation rate, groundedness, p95 latency, cost/answer.
- **Harness:** `backend/tests/test_retrieval.py` RRF unit + future `eval/evaluate.py` RAGAS (faithfulness/relevancy).

## 7. Open decisions (documented)

- Embedding 384 vs 768 — chose 384 for speed/memory; HNSW `m=16, ef=64`; upgrade by bumping `VECTOR_DIM` + `ingest --reset`.
- Provider wrapper: Pi SDK’s `HarnessConfig` inspired shape but implemented lean `llm.py` facade to keep deps light; Pi SDK can be dropped in via `pi_coding_agent` import later.
