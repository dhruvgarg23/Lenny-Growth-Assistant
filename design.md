# design.md — Lenny Growth Assistant UI/UX

## Principles

1. **Grounded trust first:** every answer shows where it came from. Source chips and inline `[source: path]` citations are affordances, not footnotes — they earn click-through and verification.
2. **Skimmability over prose:** bold subheads, bullets, 1/3/1 rhythm in essays; chat is Markdown with `prose` scale, not long paragraphs.
3. **No prompt literacy:** modes are explicit pills (Chat / Ship 30 essay / Artifact) rather than hidden keywords; placeholders guide.
4. **Fail visibly, not silently:** abstain language is consistent (“I don’t have support…”), offline Ollama has reachable badge + banner.
5. **Split attention, not context switch:** chat left, artifact right (desktop), drawer on mobile — user never loses conversation.

## Information architecture

```
Header [logo + title + Provider badge (OLLAMA • reachable) | DB | version]
├─ Sidebar (300px, md+) — New chat | session list (title + count) | Delete
├─ Chat pane (flex-1) — empty state (3 example Q + tips) → message stream → status pill → sources chips
├─ Composer — mode pills (chat / ship30 / artifact) + [markdown|html toggle] + textarea (Enter / Shift+Enter) + Send
└─ Artifact pane (520px, xl+, or drawer on <xl / mobile) — type badge | Copy | Close → Markdown prose or sandboxed iframe → security note
```

**Nav model:** single page app, no router; `activeId` drives `GET /api/sessions/{id}/messages`. Health polls on mount only (not hot loop).

## Key interaction states

| State | UI |
|-------|----|
| **Empty / no session** | Centered “No session. Create one” + CTA |
| **Empty chat** | Card with 3 example prompts (click to fill), tip chips for Ship30/artifact |
| **Streaming** | Assistant bubble grows with `ReactMarkdown`, sources appear above tokens after `sources` event; status pulsing dot |
| **Abstain** | Assistant text “I don’t have support…”, sources empty, suggestions |
| **Ship30 essay** | Same bubble but longer; content itself has H1 + `###` subheads; persisted as message |
| **Artifact** | `ArtifactViewer` replaces placeholder; `artifact.type` badge; Copy writes raw; iframe has `sandbox="allow-scripts allow-popups"` and note about isolation |
| **Error** | Streaming text appends `> ⚠️ {detail}`; e.g., Ollama not reachable remediation |
| **Offline DB** | Health header shows “DB degraded”; sessions list may be empty |
| **Deleting** | Native `confirm()` then optimistic remove |

## Responsive behavior

- **≥1280px (xl):** 3 columns — sidebar 300 + chat flex + artifact 520.
- **768–1279px:** sidebar visible, artifact **hidden** until `artifact` arrives → still hidden xl drawer hint; artifact toggles as overlay? Current: xl-only pane, mobile drawer covers all when open — keeps chat scrollable underneath.
- **<768px:** sidebar collapses to `hidden md:flex` (future: hamburger drawer — intentionally excluded per scope).
- **Composer:** pills wrap on narrow, textarea grows to 32 lines, Send is thumb-reachable.
- **Typography:** `prose-sm` in bubbles, `text-sm` elsewhere, `antialiased`, `scrollbar-thin`.

**Test matrix:** 1440, 1024, 768, 375 widths; Chrome, Safari; keyboard only (Tab → composer → Send), screen reader live region on `status`.

## Accessibility

- Semantic `header`, `main`, `button` with `disabled` state, `textarea` with placeholder, focus ring (`focus:ring-1` zinc-900).
- Message list is `div` with `role=log` potential (future): currently `scrollIntoView` for new tokens; ARIA `live="polite"` on status to announce “Searching…”.
- Color contrast: zinc-900 on white, emerald/amber badges meet WCAG AA; no color-only meaning (badge also has text “reachable”).
- Artifact iframe has `title="artifact"`; links get `rel="noopener noreferrer"`; Copy is button, not icon-only.
- No keyboard traps; `Enter` sends, `Shift+Enter` newline; `Esc` not yet closing drawer (future).

## Design decisions & trade-offs

| Decision | Alternative | Why |
|----------|-------------|-----|
| Mode pills instead of slash commands | `/ship30` hidden syntax | Discoverability; evaluators see features without docs |
| `DOMPurify` + `bleach` double sanitize | Sanitizer only server or client | Defense in depth; either side degrade-safe |
| `react-markdown + remark-gfm` | `dangerouslySetInnerHTML` | No script injection, tables/lists native |
| `sandbox="allow-scripts"` w/o `allow-same-origin` | `allow-same-origin` for nicer styling | Security: isolates null origin, cookies unreachable (see architecture.md) |
| Local MiniLM vs OpenAI embeddings | OpenAI 1536 | Zero key, fast ingest, private |
| `lucide-react` not yet used heavily | Heavier icon set | Keep bundle ~398KB → 125KB gzip |

## Component inventory

- `SessionSidebar.jsx:20` — list + new/delete
- `ChatPane.jsx:18` — empty state, `SourceChips`, `ReactMarkdown`, streaming
- `ArtifactViewer.jsx:12` — `DOMPurify.sanitize`, `srcDoc` iframe vs `prose`, Copy/Close, security footer
- `App.jsx:60` — state: `health/config/sessions/activeId/messages/input/mode/artifactType/streaming*`, `streamChat` controller, `fetchHealth` on mount

## Future polish (out of scope)

- Hamburger drawer for mobile sidebar, `Esc` to close artifact, theme toggle, session rename inline, message copy, per-message feedback thumbs, token cost badge, `prefers-reduced-motion`, `cmd+K` command palette, `aria-live` for tokens.

