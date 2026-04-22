# Workpad AI — Product Vision

> Living specs for engineering teams. Specs that stay wired to the systems they describe.

## Elevator Pitch

Engineering specs — PRDs, RFCs, ADRs, post-mortems, runbooks — rot the moment they are written. They are disconnected from the code they describe, the meetings where they were debated, the Slack threads where tradeoffs were argued, and the diagrams that once made them legible. By the time a new engineer, a staff engineer, or a future version of the same author tries to reread them, the reasoning is no longer recoverable.

Workpad AI turns specs into **living pads**: persistent, cross-linked documents that stay wired to their sources. The AI can draft a spec from a repo, a meeting transcript, and a diagram; cite those sources inline; detect when the code has drifted from what the spec claims; and answer onboarding questions from the spec library plus the live state of the system.

The result is a spec that is still *readable*, *trustworthy*, and *useful* six months after it was written.

## The Problem

Specs die for predictable reasons:

- **They are written once and never reread.** The team moves on; the spec becomes a historical pad.
- **They are disconnected from their sources.** The RFC cites "the discussion in the architecture review" with no link. The ADR says "we decided X because Y" with Y nowhere recoverable.
- **They drift silently.** Code evolves; the spec that described it does not. By the time someone notices, the spec is misleading rather than helpful.
- **They have no reuse story.** Teams re-solve the same problems because the prior decisions are undiscoverable.
- **They live in write-only tools.** Confluence, Notion, GitHub wikis — all become document graveyards without an active reader.

The result: teams either (a) stop writing specs, (b) keep writing them but treat them as ceremony, or (c) invest enormous effort in a wiki hygiene culture that rarely survives the next reorg.

## The Insight

Specs should be *anchored to live sources*, not copies of them. A decision in an ADR should not just say "we chose X because of the benchmark" — it should link to the benchmark, the PR where the alternative failed, the Slack thread where the tradeoff was discussed, the meeting where the call was made. When the reader reopens the spec later, the reasoning is still recoverable because the citations resolve against current systems.

Once specs are wired to their sources, AI becomes genuinely useful:

- It can **draft** a spec by reading the raw materials (repo + transcript + diagram).
- It can **verify** a spec by checking its claims against current code and flagging drift.
- It can **answer** questions by combining the spec library with live system state.
- It can **connect** specs across the library, suggesting related decisions and prior art.

The product is not "Notion with an AI sidebar." It is a workspace where specs and their sources live together, and the AI reads both.

## Target User

**Primary:** Engineering teams of roughly 10–80 people using GitHub + Slack. Startups from seed through Series B/C. Too small to justify Confluence + Atlassian Rovo; too serious to dump everything in plain Notion.

Who inside the team cares:
- **Staff / principal engineers** writing RFCs and ADRs — biggest pain, most willing to try a new tool.
- **Eng managers** trying to keep institutional knowledge from walking out the door.
- **New hires** — the onboarding use case is the retention driver.

**Secondary (later):** Larger orgs (80–500 engineers) at the team level, where a single team adopts the tool without enterprise procurement.

**Non-target (for now):** Solo developers, open-source projects, enterprise BigCo procurement cycles.

## Pad Types

Specs are first-class, typed, and cross-linked:

- **PRD** — what we are building, for whom, and why.
- **RFC** — how we propose to build it, alternatives considered.
- **ADR** — a decision record: context, options, choice, consequences.
- **Design doc** — longer technical design, often includes diagrams.
- **Post-mortem** — what went wrong, what we learned, what changed.
- **Runbook** — operational how-to for a system.
- **Onboarding doc** — what a new hire needs to know about a domain.
- **Clause / block (reusable)** — a chunk of content that appears in many specs (e.g. "our standard auth setup," "how we handle feature flags").

Every pad has:
- A stable ID and permalink
- A type (from the list above)
- A set of linked sources (repo paths, PR numbers, transcript sections, Slack permalinks, diagram handles)
- A set of linked pads (backlinks, citations)
- Version history

## Source Integrations

The full integration layer. Not all of these ship on day one — see "Candidate v1 Wedges" below.

### Code
- **GitHub** — read-only access to a repo: files, PRs, commits, issues.
- **GitLab / Bitbucket** — equivalent support later.
- **Linked code blocks** — quote a function by path + line range; the quote re-resolves on read.

### Meetings
- **Transcript paste** — paste any transcript text, no integration required.
- **Transcript upload** — drop a file (.txt, .vtt, .srt) from any source.
- **Audio / video upload** — transcribe on our side (Whisper or similar).
- **Note-taker imports** — accept webhook or API from Granola, Fireflies, Otter, Read.ai, Circleback, tl;dv.
- **Direct platform plugins** — Zoom Marketplace, Microsoft Teams, Google Meet. Joins the meeting, captures the transcript, posts a draft back.

### Chat
- **Slack** — read-only access to selected channels; cite permalinks; optionally post spec links back to the channel.
- **Microsoft Teams** — equivalent.
- **Discord** — for open-source / community orgs.

### Design
- **Figma** — embed frames; capture the link so the embed re-resolves.
- **Excalidraw** — native support; allow drawing inside the canvas.
- **Mermaid** — text-based diagrams rendered inline.
- **Image upload** — paste screenshots, whiteboard photos, hand-drawn sketches. AI reads them.

### Tickets
- **Linear** — reference issues and projects; link specs to delivery work.
- **Jira** — equivalent for larger orgs.
- **GitHub Issues** — basic support via the GitHub integration.

### Knowledge
- **Web pages** — paste URL; AI fetches and summarizes; link persists.
- **PDF upload** — for externally authored specs, papers, vendor docs.

## AI Capabilities

Five distinct modes, powered by the same underlying model:

### 1. Scaffold mode (first-run)
User arrives with raw material — a pasted transcript, an uploaded doc, a dragged folder, or just a chat message. AI infers project shape (name, likely pad type, relevant sources) and produces a populated project with a drafted first pad. This is the default onboarding path.

### 2. Draft mode
"Draft an RFC from this Slack thread + this PR + this meeting transcript." AI produces a coherent first draft with inline citations. The user edits; the canvas tool applies structured changes.

### 3. Verify / drift detection
"Is this ADR still accurate?" AI checks the claims in the spec against the current state of the linked sources (does the function still exist? did the API change? is the flag still in code?) and flags mismatches. Over time, this runs on a schedule, not just on demand.

### 4. Onboarding mode
A new hire asks a question. AI answers from the spec library, with citations, and falls back to the live repo when the library does not cover it. Questions that cannot be answered reveal gaps in the library, which become drafts to fill.

### 5. Cross-link intelligence
When writing a new spec, AI suggests related specs from the library ("this looks like the rate-limiting ADR from Q3"), extracts reusable clauses, and builds a graph of spec-to-spec citations. Over time, the library is a graph, not a folder.

## Interface Surfaces

Workpad is a web app first, but the spec library is valuable from any surface where a user does technical thinking. The long-horizon surface set:

### Web app
The primary, canonical surface. Hosts the library, the pad editor, threads, search, and collaboration. See `docs/V1_SPEC.md`.

### CLI client
A `workpad` command-line client for engineers who live in the terminal. Authenticates against the hosted app. Can:
- draft a pad from a local repo path + a pasted transcript
- search the library, pipe results to stdout
- open a pad in the terminal (readable markdown with citation footnotes)
- push a local file or folder as a source
- sync a local directory with project sources so drafts stay up to date

### MCP server
Workpad exposes its library + drafting capabilities as an **MCP (Model Context Protocol) server**, so other AI clients — Claude (Desktop, Code), Codex, Gemini, ChatGPT with MCP, and future clients — can:
- query the library (grounded ask over the user's projects)
- fetch specific pads as context
- draft into Workpad from those clients
- attach sources back to a project

This matters because the library is the product. It should be reachable from any AI the user is already using.

### Coding-agent interop
Beyond MCP, first-class export and plugin paths to coding agents:
- **Claude Code** — a plugin that lets Claude Code read relevant pads as context, open a scratch PR against a design note, and run drift verification inline
- **Codex / Cursor / OpenAI Codex** — export a pad as context or a prompt
- **Aider, Continue, and OSS coding agents** — a shared context-export format pads can be rendered into
- **Reverse:** coding agents can push back into Workpad (e.g. "I implemented this; here's the PR link" auto-attaches a `repo_pr` citation)

### Editor plugins (later)
VS Code / JetBrains extensions that surface the relevant ADR/RFC when a developer opens a file. Not a priority until MCP and web are solid.

## Agents (later)

Agents management becomes a useful concept once the library and integrations are mature. The vision:

- **Drift agents** — scheduled workers that re-verify citations across a project and summarize drift for an inbox.
- **Onboarding agents** — a long-running agent a new hire can converse with over weeks; it remembers what's been asked, flags gaps in the library, drafts the missing docs.
- **Research agents** — given a question, explore the library + live sources + the web and return a grounded report.
- **Refactor-aware agents** — watch a repo; when code moves significantly, open a suggested ADR update.

Agents are a post-library capability, not a v1 primitive. The library and integrations must be rock-solid first; otherwise the agents have nothing to operate on.

## Input Modalities

### Text
Paste, type, drag markdown, paste from clipboard. The baseline.

### Files and folders
Markdown, text, PDFs, code files, uploaded as sources. Folders as zip / drag-drop.

### Images
Screenshots, Figma exports, whiteboard photos, hand-drawn sketches. Vision + OCR.

### Speech
Speech-to-text input in chat and pad editing. Dictation for users who think aloud or are away from a keyboard. Later: direct audio uploads for short clips (meeting snippets, voice notes).

### Media uploads (later)
Short audio clips, video clips. Transcribed on our side or via partner integration (see Source Integrations).

## Knowledge Base Model

Not just "a list of pads per conversation." The library is the product.

- **Typed pads** (see above) with stable IDs.
- **Backlinks** — every pad shows which other pads cite it.
- **Tags and domains** — pads organize by system ("auth," "billing," "data pipeline").
- **Source references** — every pad stores the sources it cites; sources are live, not snapshots.
- **Reusable blocks** — clauses that appear in many specs; edit once, reflected everywhere with versioning.
- **Search** — full-text + semantic search across pads, sources, and past conversations.
- **Graph view (later)** — visualize the spec graph: which decisions depend on which, which systems have the most decisions, which specs have drifted.

The library is what makes the tool stick. Conversations are ephemeral; the library is durable.

## Differentiation

Against the obvious incumbents:

- **Notion / Notion AI** — generic pages; AI is bolted on, not wired to repos/meetings. No staleness detection. No typed specs.
- **Confluence + Atlassian Rovo** — enterprise-only, slow UX, expensive procurement. Serves large orgs that already have Jira.
- **Linear** — great for tickets, intentionally not a docs tool. Potential partner.
- **GitHub Wiki / repo-native docs** — no AI, no cross-linking beyond markdown, barely maintained.
- **Swimm, Mintlify, Docusaurus** — documentation for shipped systems, not decision-making for in-progress systems.
- **Granola / Fireflies / Otter** — meeting notes, one-off. No spec library. Potential partners/sources.
- **ChatGPT Canvas / Claude.ai pads** — single-session pads, no library, no integrations, no drift detection.

The wedge: **AI-native specs for eng teams, wired to the systems they describe.** No single incumbent combines these.

## Philosophy

- **Conversation is for orchestration; the workpad is for durable work.** (Carry-over from the current product principle.)
- **Specs are anchored to sources, not copies of them.** Citations resolve live.
- **The library is the product.** Pads accumulate; value compounds.
- **Bring your own capture.** Don't compete on meeting recording, note-taking, or diagramming — consume their output.
- **Drift is a feature.** Detecting that a spec no longer matches reality is as valuable as drafting it.
- **First session must produce value.** A new user arrives with one input — a pasted transcript, an uploaded doc, a dragged folder, a chat message — and lands inside a populated project with a real pad. Manual setup is the fallback, not the default. Any step between the user and their first useful pad is friction to remove.

## What This Is Not

- Not a meeting recorder or note-taker (we consume transcripts).
- Not a generic wiki (we are opinionated about pad types).
- Not a project management tool (we link to tickets; we don't replace them).
- Not a documentation generator for end users (we serve internal specs).
- Not an enterprise CLM / legal tool (explicit non-goal).

## Open Questions

Things we have discussed but not resolved:

1. **v1 scope.** The full vision has many source integrations. v1 cannot. Which one source + which one AI capability ships first? (See "Candidate v1 Wedges" below.)
2. **Self-serve vs. sales-led.** Does a 40-person eng team discover this through a staff engineer's side-exploration (self-serve, low-friction) or through a company-wide pilot (sales-led, slower)?
3. **Hosting.** Self-hosted option for security-sensitive teams vs. cloud-only for speed of iteration.
4. **Pricing model.** Per-seat? Per-pad? Per-team? Flat team fee is the norm for this audience.
5. **Build vs. partner on note-takers.** Direct Zoom/Teams/Meet plugins vs. webhooks from Granola/Fireflies. Partner is cheaper; direct is more defensible.
6. **Open-source strategy.** Is the core open (to drive adoption in eng communities) with paid hosted / paid team features? Or closed?
7. **AI provider.** OpenAI Responses API today. Claude/other models for specific tasks (citations, long-context)?
8. **Data model for drift detection.** How do we store the "claim" a spec makes about code in a way that can be re-checked later? This is the hardest technical problem.

## v1 Scope

The committed v1 scope lives in [`V1_SPEC.md`](./V1_SPEC.md). Summary:

- Hosted web app (runnable locally) with password auth
- **Projects** as the top-level container (no workspace layer above them)
- **Four pad types:** RFC, ADR, design note, run note
- **Five source kinds:** repo, transcript, note, file upload, image upload
- **One-input scaffolding** as the default onboarding path (paste or upload → populated project)
- Project-scoped search + grounded ask
- Keep the already-shipped RFC drafting + citation verification + drift detection

Target audience: small engineering teams (2–10) and serious individual engineers. The app must feel equally useful to one person and to a small team.

### What is explicitly NOT in v1 (kept here as vision)

- CLI client
- MCP server
- Cloud connectors (GitHub App OAuth, Slack, Drive, Figma, Linear, Jira, etc.)
- Coding-agent plugins (Claude Code, Codex, Cursor)
- Agents management
- Native Excalidraw drawing surface
- Speech input / audio-video upload + transcription
- Polished landing page (placeholder until v1 is functional)
- SSO, billing, scheduled background jobs, comments, notifications

### Historical wedge candidates

Earlier thinking sketched several narrow wedges (repo+transcript → RFC; repo+ADR+drift; onboarding bot; etc.). **Wedge A+ (repo + transcript → RFC with drift) was built and shipped** as the starting substrate. The consolidated v1 generalizes that substrate outward; the individual wedge framing is retained here only for historical reference.

## Recommended Next Steps

1. Build Phase 1 of `V1_SPEC.md` (auth + projects + authenticated shell).
2. Keep the shipped RFC drafting + citation + drift stack working through every migration.
3. Put scaffolding (one-input onboarding) in front of 2–3 staff engineers as soon as Phase 2 ships. The first-session-value principle needs real-user validation early.
4. Revisit this document after Phase 4 to prune or commit the vision items that earned their way in.

---

*This document is the long-horizon vision. It is intentionally broader than what we will build first. Use it to keep v2+ decisions aligned; do not use it as a v1 checklist.*
