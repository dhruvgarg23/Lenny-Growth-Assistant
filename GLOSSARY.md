# Glossary

Domain language for the Lenny Growth Assistant. Terms only — no implementation details.

- **Transcript**: a single Markdown source from Lenny's Podcast or Newsletter archive. Transcripts are the sole ground truth; anything not in them cannot be claimed.
- **Chunk**: a retrieval unit cut from a transcript (~800 characters), prefixed with its title and guest. What retrieval ranks and what answers cite.
- **Session**: one persistent conversation: an ordered sequence of user and assistant messages.
- **Grounded answer**: a response synthesized strictly from retrieved chunks, with every core assertion traceable to a cited chunk.
- **Source (citation)**: the attribution attached to a grounded answer — episode title, guest, and excerpt — letting the reader verify each claim without leaving the conversation.
- **Confidence**: the fused ranking score behind a set of retrieved chunks; below threshold, the assistant must abstain rather than guess.
- **Abstention**: the explicit, polite response given when no chunk meets the confidence threshold, plus guidance toward supported topics.
- **Mode**: the output contract the user selects — `chat`, `ship30`, or `artifact`. Explicit selection always wins; it is never overridden by keyword guessing.
- **Ship 30 essay**: a ~1,250-word atomic essay in the Ship 30 for 30 form (strong headline, 1/3/1 rhythm, bold subheads, bulleted frameworks, actionable takeaway).
- **Artifact**: a reusable rendered output — Markdown or HTML/CSS — produced beside the conversation and isolated from the application.
