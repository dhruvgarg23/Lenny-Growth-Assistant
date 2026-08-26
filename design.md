# Design Specification

## The Lenny Growth Assistant

## 1. Design Principles

### Grounding First
Sources should be visible as part of the answer rather than hidden behind a separate research workflow. Citations and guest attributions appear inline and in interactive chips directly attached to each message.

### Conversation as the Primary Interface
The user should be able to ask follow-up questions without repeatedly reconstructing context. The chat stream maintains conversational context across multiple turns.

### Output-Oriented
The interface should support not only answers but reusable outputs such as structured essays and interactive artifacts that can be copied, inspected, or shared immediately.

### Progressive Disclosure
Advanced functionality (e.g. artifact format selection, model switching, detailed transcript source excerpts) should remain accessible without cluttering or overwhelming the primary chat flow.

### Failure Should Be Actionable
Errors should tell the user exactly what happened and provide explicit, actionable remediation steps (e.g. CLI commands to start Ollama or configure missing keys) rather than generic alert dialogs.

## 2. Information Architecture

```text
Application
│
├── Session Sidebar (Collapsible)
│   ├── + New Chat Action
│   └── Session List (Title, Timestamp, Delete)
│
├── Chat Workspace
│   ├── Header
│   │   ├── Brand & Description
│   │   ├── Model / Provider Dropdown Selector
│   │   └── System Status Indicators (DB, Version)
│   ├── Conversation Feed
│   │   ├── Message Bubbles (User / Assistant)
│   │   ├── Source Citation Chips
│   │   └── Dynamic Status Indicators (Retrieving / Generating)
│   └── Composer Bar
│       ├── Mode Selector (Chat / Ship 30 / Artifact)
│       ├── Artifact Type Selector (Markdown / HTML)
│       ├── Multiline Textarea (Auto-expanding)
│       └── Send / Stop Controls
│
└── Artifact Workspace (Split-Pane / Drawer)
    ├── Artifact Header (Type Badge, Warnings, Close/Toggle)
    └── Rendered Content Area (Sandboxed Iframe / Markdown Viewer)
```

## 3. Primary Screens

### Chat
- **Purpose:** Conversational exploration, product research, and strategic synthesis.
- **Contains:** Session navigation, chronological message history, transcript source chips with excerpt previews, expanding composer, and live provider status badges.

### Ship 30
- **Purpose:** Long-form, highly structured atomic essay writing.
- **Behavior:** The conversation remains active in the stream while the generated ~1,250-word essay is formatted with bold subheadings, 1/3/1 sentence structures, bulleted frameworks, and a sources footer.

### Artifact
- **Purpose:** Producing reusable visual or structured outputs (comparison matrices, launch checklists, strategy one-pagers).
- **Behavior:** The artifact workspace expands beside the conversation on desktop, rendering Markdown tables or interactive HTML/CSS prototypes natively.

## 4. Key Interaction States

### Empty State
When a new session is started, the chat feed displays a clean greeting card explaining the assistant's capabilities alongside one-click example prompts (e.g., *"How do top PMs improve onboarding activation?"*, *"What are the core loops for B2B PLG?"*).

### Loading State
When a query is submitted, the UI shows real-time progress indicators (*"Searching Lenny transcripts…"*, *"Drafting answer…"*) reflecting actual pipeline stages without false delays.

### Streaming State
Tokens render progressively as they arrive from the Server-Sent Events (SSE) stream, providing immediate visual feedback with smooth auto-scrolling.

### Sources Available
When transcript chunks are retrieved, interactive source chips appear above or below the answer displaying the episode title, guest name, and confidence score. Clicking a chip reveals the exact excerpt.

### No Supporting Evidence (Abstention)
When a prompt falls outside Lenny's podcast archives or retrieval confidence is low, the assistant displays a polite abstention message and suggests valid domain topics.

### Provider Offline
If the selected provider (e.g. Ollama daemon) is unreachable, the UI displays an amber warning badge with direct remediation instructions (*"Start Ollama with: `ollama serve && ollama pull llama3.1:8b`"*).

### Artifact Generating
The artifact workspace enters a subtle loading state while preserving conversational context in the chat pane.

### Artifact Error
If generated HTML fails validation or contains malicious constructs, the viewer displays a structured error with sanitization warnings while preserving the raw output for inspection.

## 5. Responsive Behavior

### Desktop (≥ 1024px)
- **Layout:** Two-column split-pane layout.
- **Dimensions:** Chat workspace takes 60% width; Artifact workspace takes 40% width.
- **Behavior:** Both areas remain visible simultaneously, allowing the user to refine the prompt while inspecting the rendered artifact.

### Mobile & Tablet (< 1024px)
- **Layout:** Single-column layout with overlay drawer.
- **Dimensions:** Chat workspace occupies 100% width; Artifact workspace opens as an animated slide-over drawer or bottom sheet.
- **Target Viewport:** Fully responsive down to 375px viewport width with zero horizontal scrolling.

## 6. Accessibility

- **Keyboard Navigable:** Full keyboard navigation across all interactive controls (sidebar, mode buttons, model menu, composer).
- **Visible Focus States:** High-contrast focus rings on all buttons, links, and input fields.
- **Semantic HTML:** Proper heading hierarchy (`h1` through `h4`), semantic `<button>`, `<nav>`, `<main>`, and `<aside>` elements.
- **Screen Reader Support:** ARIA attributes (`aria-live="polite"` for streaming tokens, `aria-expanded` for dropdowns).
- **Color Contrast:** Minimum 4.5:1 contrast ratio for all standard text against light and dark backgrounds.
- **Keyboard Shortcuts:** `Enter` to send message, `Shift + Enter` to insert a newline.

## 7. Design Decisions

### Why Source Chips?
Displaying source citations directly alongside generated claims builds immediate trust, allowing PMs to verify specific guest insights without leaving the conversation.

### Why Split Chat/Artifact View?
A side-by-side view allows users to iteratively prompt the assistant to modify an artifact (e.g. *"add a pricing tier comparison"*) while seeing the updated rendering live.

### Why a Model Selector in the Header?
Different tasks have varying latency, privacy, and reasoning requirements. Giving evaluators visibility into the active model builds confidence in the system's local vs cloud execution.

### Why Explicit Provider Status?
Showing whether Ollama is connected or if a cloud API key is missing prevents confusing silent failures and provides immediate troubleshooting feedback.

### Why Sandboxed Artifacts?
Generated HTML is untrusted content. Rendering it inside an isolated `<iframe>` prevents malicious scripts or stylesheet injections from accessing application cookies, local storage, or the host DOM.

## 8. Interaction Patterns

### Composer Bar
```text
[ Mode: Chat ▾ ] [ Format: HTML ▾ ]
[ Ask a product or growth question...                        ] [ Send ↵ ]
```
- Supports `Enter` to submit and `Shift + Enter` for multiline input.
- Automatically expands vertical height up to 6 lines as text length increases.

### Model Selector Dropdown
```text
┌───────────────────────────────────────────────┐
│ OLLAMA • llama3.1:8b • local                ▾ │
├───────────────────────────────────────────────┤
│ 🖥️ OLLAMA (LOCAL)                             │
│   ● llama3.1:8b                               │
│ 🧠 ANTHROPIC CLAUDE (CLOUD)                   │
│   ○ claude-3-5-sonnet-20241022                │
│   ○ claude-3-5-haiku-20241022                 │
│ ⚡ GROQ (CLOUD)                               │
│   ○ llama-3.3-70b-versatile                   │
│   ○ openai/gpt-oss-120b                       │
└───────────────────────────────────────────────┘
```

### Source Citation Chips
```text
┌──────────────────────────────────────────────────────────┐
│ 📄 Brian Halligan — Scaling HubSpot (Score: 0.032)       │
│ 📄 Elena Verna — B2B Product-Led Growth (Score: 0.029)   │
└──────────────────────────────────────────────────────────┘
```

## 9. Visual Hierarchy

Priority ordering from highest to lowest:
1. **Active Conversation Stream:** The primary reading area where answers and citations unfold.
2. **Composer Input:** The primary action area where the user inputs questions and sets modes.
3. **Rendered Artifact Canvas:** The visual output pane displaying rendered documents or prototypes.
4. **Source Attribution Details:** Supplementary verification data.
5. **System Controls:** Model switching, session management, and status indicators.

The interface prioritizes reading clarity and content consumption over decorative complexity.
