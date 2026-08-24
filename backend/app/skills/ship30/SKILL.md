# Ship 30 for 30 — Lenny Growth Essay Skill

**Purpose:** Turn grounded Lenny transcript answers into a ~1,250-word Ship 30 for 30–style essay that is skimmable, actionable, and cited.

## Principles encoded (from Ship30 sources)

### Pillar extracts
1. **Atomic Essay:** One niche idea, 250-word sweet spot expanded via Lean Writing to ~1,250 words; start small, gather data, double-down.
2. **Headline Formula (5 pieces):** Who (niche PM/growth audience) + What (topic) + Why (outcome) + Promise + Number/scope. Be CLEAR not clever. Increase voltage with specificity.
3. **Hook:** Single-sentence opener (6 types: strong declarative, provocative Q, contrarian, moment-in-time, vulnerable, weird insight) + 1/3/1 rhythm (1 sentence / 3 sentences / 1 sentence doors).
4. **Formatting is 10x:** Every section opens single sentence; turn lists → bullets; bolded subheads every ~100 words; selective bold on sentences; never block paragraphs >3 lines.
5. **Actionability:** Specific useful takeaway + CTA, story over definition, show personal/PM context.

### Output contract
- Input: `{query, history, contexts: [{title,guest,source_path,content}]}` (contexts pre-fused via RRF)
- Output: Markdown H1 + optional deck + 3-5 `###` sections + Sources footer. Inline citations `[source: path]`. 1150-1350 words.
- Fail closed: if context insufficient, do not hallucinate stats; narrow scope and cite what exists.

### Routing
Trigger phrases: `ship 30`, `ship30`, `atomic essay`, `essay`, `1,250 words`. Routed via `app/services/agent_router.py`.

### Citation enforcement
Every section must include ≥1 citation. Footer `#### Sources` lists cited paths.
