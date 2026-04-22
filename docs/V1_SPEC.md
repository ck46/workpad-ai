# Workpad AI — v1 Spec (Consolidated)

> Living specs for small engineering teams (2–10) and serious individuals. Projects hold pads, threads, sources, and uploaded files. AI drafts, grounds, and searches across it all.

**Supersedes:** the narrow wedge-A+ spec (previous `V1_SPEC.md`), `docs/archive/PERSONAL_MVP_SPEC.md`, and `docs/archive/WEB_MULTIUSER_SPEC.md`. Those remain readable in `docs/archive/` for historical context.

**See also:** `docs/PRODUCT_VISION.md` for the long-horizon vision (CLI, MCP, connectors, coding-agent interop, etc. — all explicitly out of v1 scope).

---

## What v1 Is

Workpad AI v1 is a hosted web app (also runnable locally) where a small engineering team — or one engineer — keeps durable technical pads (RFCs, ADRs, design notes, run notes) wired to the sources that justify them.

The shape:

- You sign in. You create or join a **project**. A project has members.
- Inside a project, you have a **library** of pads, a set of **threads** (AI conversations scoped to the project), and a set of **sources** (repos attached via URL + PAT, pasted transcripts, notes, uploaded files, uploaded images).
- You can draft a pad from sources, write one by hand, ask questions across the library, and see when citations drift from the current code.
- Everything in a project is visible to every member of that project. No finer-grained permissions in v1.

The north star is unchanged: **opening Workpad for technical thinking should feel more natural than opening a blank doc or a blank chat.**

## Design Principle — First Session Produces Value

v1 succeeds or fails on the first session. A new user should end their first five minutes inside a populated, useful project — not an empty shell that demands setup before delivering any value. Every flow that touches onboarding must reduce friction toward that outcome.

Concretely: the user arrives with one input (a pasted transcript, an uploaded doc, a dragged folder, or even a chat message describing what they're working on) and the product scaffolds a project around it — named, with the input attached as a source and a first pad drafted. Manual project setup exists but is not the default path.

This is not just a feature. It is the test for every UI decision: *does this step sit between the user and their first useful pad?* If yes, cut it.

## What Is Already Shipped

The narrow wedge (wedge A+ in `PRODUCT_VISION.md`) is built and passing tests. See `V1_BACKLOG.md` for the M0–M3 checklist. Summary:

- GitHub repo + pasted transcript → drafted RFC with inline citation pills
- Citation verification re-resolves repo citations and surfaces drift via status badges
- Hover preview, stale-citation diff, export with citation footnotes
- SQLite schema for `Pad`, `Citation`, `SpecSource`, `RepoCache`, `Conversation`, `Message`

This substrate is kept and extended. Nothing here is thrown away.

## What v1 Adds

Four layers on top of the shipped wedge.

### 1. Auth + projects

- Password auth (sign up, sign in, reset password; email verification optional).
- **Project** as the top-level container. No workspace layer above it.
- Roles: `owner` and `member`. That's it.
- Invite by email, accept via signed link.
- A single user can belong to multiple projects.

### 2. Library + pad types

- Library-first navigation inside a project.
- Four pad types: `rfc`, `adr`, `design_note`, `run_note`.
- Manual pad creation (blank document of any type).
- AI drafting generalized across all four types.
- Pad-to-pad references (`pad_ref` citation kind).

### 3. Sources + search

- Source kinds: `repo`, `transcript`, `note`, `file`, `image`.
- File upload: markdown, text, PDFs, code files, folders (drag-drop or zip).
- Image upload: screenshots, Figma exports, whiteboard photos, hand-drawn sketches. AI reads them via a vision model and extracts text via OCR.
- Project-scoped search (keyword + semantic) over pads, transcripts, notes, extracted file text, citation excerpts.
- Grounded ask: *"What did we decide about auth?"* returns an answer with citations back to the pads and source chunks that support it.

### 4. One-input scaffolding

- User arrives with a single piece of raw material: a pasted transcript, an uploaded PDF or doc, a dragged folder, or a chat message describing what they're working on.
- System infers project name, likely pad type, and relevant additional sources (e.g. a repo URL mentioned in the transcript). Creates the project, attaches the input as a source, and drafts a first pad.
- User lands inside a populated project. From there they invite teammates, attach more sources, or keep drafting.
- Manual setup (create empty project → attach sources → draft) still exists but is the secondary path.

## Explicit Non-Goals (Not in v1)

Anything here requires an explicit scope change, not a "while we're at it." These are all listed in `PRODUCT_VISION.md` as future directions.

- CLI client
- MCP server (for Claude / Codex / Gemini / other clients)
- OAuth cloud connectors: GitHub App, Google Drive, Slack, Figma, Linear, Jira, Discord, Notion, Confluence
- Native Excalidraw drawing surface (live Mermaid still renders in markdown)
- Speech input in chat
- Audio / video upload + in-app transcription
- Coding-agent export or plugins (Claude Code, Codex, Cursor)
- Agents management / multi-agent orchestration
- Polished landing page / marketing site (placeholder is fine until v1 is functional)
- Self-hosted enterprise deployment story
- SSO / SAML / SCIM
- Billing / payments
- Fine-grained permissions (per-pad ACL, viewer role, restricted visibility)
- Comments, mentions, notifications, inbox
- Scheduled background re-verification
- Graph visualization of the pad graph
- Cross-project retrieval
- PM-style workflow (assignees, reviews, approvals)

## Primary User Flows

### A. First session: scaffold from one input (the default path)

1. Sign up. (Email verification is optional and non-blocking.)
2. Landing screen is a single dropzone / paste area with three affordances:
   - paste text (transcript, notes, draft fragment, or "what are you working on?")
   - upload a file or folder (PDF, doc, zip, image)
   - paste a repo URL
3. User provides any one of these. Clicks **Scaffold**.
4. Backend runs a **scaffold pass**:
   - infer project name from the input
   - infer likely pad type (`rfc | adr | design_note | run_note`) from content cues
   - detect any repo URLs referenced in the input; offer to attach if a PAT is available, skip cleanly if not
   - attach the input as the first source
   - draft a first pad (Phase 5+) or create a stub with a generated outline (Phase 2+)
5. User lands inside a populated project with a draft pad open. Invite teammates as an optional next step, not a required one.

### B. Start a new project manually

1. Sign up or already signed in.
2. Click **New project** (secondary affordance in the app shell).
3. Name it, land on empty project home, attach sources and draft from there.

### C. Draft a pad from sources

1. From the library, click **New pad**.
2. Pick type (RFC / ADR / design note / run note).
3. Pick mode: *blank* or *draft from sources*.
4. Attach sources: pick existing or attach new (repo URL, paste transcript, upload file, upload image).
5. Optionally select prior pads as drafting context.
6. Click **Draft**. Pad streams in with inline citations across all source kinds.

### D. Write by hand

1. New pad → blank → choose type → write.
2. Attach sources at any point; AI can ground claims on request.

### E. Ask across the project

1. Open the Ask panel.
2. Ask a question.
3. Get a grounded answer with citations to pads and source chunks.
4. Click citations to jump to the pad or the source excerpt.

### F. Reopen a stale pad

1. Open an old RFC.
2. Drift banner: *"3 citations have drifted since draft at `sha[:7]`."*
3. Click a stale pill → diff popover shows before/after.
4. Edit or re-ground claims as needed.

## Scaffolding Model

The scaffold flow is a meta-capability that combines existing primitives (project creation, source attachment, pad drafting) into one action. No new subsystem; the magic lives in the UX and the inference step.

**`POST /api/scaffold`** accepts:

- `text` (optional) — pasted content
- `file_ids` (optional) — IDs of files pre-uploaded via a separate upload endpoint
- `repo_url` (optional) — repo reference
- `hint` (optional) — user-provided nudge ("this is a postmortem", "RFC about caching")

The handler:

1. Picks the primary input. If multiple, combines them.
2. Calls the model with a `scaffold` tool that outputs: `{ project_name, pad_type, pad_title, detected_repo_urls: [...], outline_sections: [...] }`.
3. Creates the project, makes the caller the `owner`.
4. Creates `Source` + `SourceSnapshot` rows for the input.
5. If `pad_type` is inferred and the drafter is available, kicks off a draft stream. Otherwise creates a stub pad with the outline.
6. Returns project + initial pad IDs, then streams the draft if one is in progress.

**Progressive capability:**

- Phase 2 ships stub-scaffolding: project + source + stub pad with an outline. No live drafting yet.
- Phase 5 upgrades scaffolding to produce a real draft using the generalized drafter.
- Incremental improvements (better title inference, repo auto-detection, pad-type detection) ship between those phases.

The flow is designed so its minimum viable version lands in Phase 2 and its richest version lands by Phase 5, not all-at-once in one phase.

## Project Model

Top-level container. No workspace above it.

**`Project`:**
- `id`
- `name`
- `created_by_user_id`
- `created_at`, `updated_at`

**`ProjectMember`:**
- `id`, `project_id`, `user_id`
- `role`: `owner | member`
- `created_at`

**`Invite`:**
- `id`, `project_id`, `email`, `token_hash`, `invited_by_user_id`
- `accepted_at` nullable, `expires_at`, `created_at`

If someone needs read-only access, they don't belong on the project yet. Don't build viewer/admin/restricted until the need is real.

## Pad Model

Pads are durable project objects.

**`Pad`:**
- `id`
- `project_id`
- `pad_type`: `rfc | adr | design_note | run_note`
- `title`
- `content_markdown`
- `content_type`: `markdown | code` (code for the Monaco path; unused in the default flow)
- `summary`
- `status`: `draft | active | archived`
- `owner_user_id`
- `created_by_user_id`
- `created_at`, `updated_at`, `last_opened_at`
- `version` (for optimistic concurrency)

Visibility: every project member sees every pad. No `visibility` column yet.

`PadVersion` already exists — keep the one-row-per-revision model.

## Source Model

Sources are normalized and project-scoped.

### `Source`

- `id`, `project_id`
- `kind`: `repo | transcript | note | file | image`
- `title`
- `provider`: e.g. `github`, `upload`
- `canonical_key` (for dedupe: repo slug, file hash, etc.)
- `provenance_json` (kind-specific metadata)
- `created_by_user_id`
- `created_at`, `updated_at`

### `SourceSnapshot`

Pinned content of a source at a moment in time.

- `id`, `source_id`
- `snapshot_ref` (commit SHA, file hash, transcript hash)
- `content_text` (extracted text for files/PDFs/images; empty for repos — live fetched)
- `content_hash`
- `metadata_json`
- `created_at`

### `PadSourceLink`

Join between pads and sources.

- `id`, `pad_id`, `source_id`, `source_snapshot_id`
- `role`: `primary | context | cited | derived_from`
- `added_by_user_id` nullable
- `added_by_system`
- `created_at`

### Transitional: `SpecSource`

The existing `SpecSource` table stays through Phase 2; Phase 3 backfills to `Source` / `SourceSnapshot` and freezes `SpecSource`. Do not try to mutate it in place.

### File and image handling

- Files stored on disk (local) or object storage (hosted); metadata lives in `Source`.
- Text extraction happens at upload time:
  - `.md`, `.txt`, code files → read directly
  - `.pdf` → `pdftotext` (not layout-aware parsers — scope trap)
  - `.docx` → `python-docx`
  - images → vision model for description + OCR
- Extracted text lands in `SourceSnapshot.content_text` and gets chunked for search.
- Folder upload: zip on the client; server unzips and creates one `Source` per file with a shared parent identifier in `provenance_json`.
- Image size cap: 20 MB. File size cap: 50 MB. Folder zip cap: 200 MB. Adjust from feedback.

## Citation Model

Extend the existing `Citation` table additively.

**Kinds:**

- `repo_range`, `repo_pr`, `repo_commit` (existing)
- `transcript_range` (existing)
- `note_range` (new)
- `file_range` (new — line range in a source file, or page range in a PDF)
- `image_region` (new — optional bounding box; nullable → whole-image reference)
- `pad_ref` (new — reference to another pad)

**New columns:**

- `source_snapshot_id` nullable
- `excerpt_text_at_capture` nullable

Existing repo-drift logic continues to operate on `repo_*` kinds. Other kinds are `live` by definition in v1 (transcripts, notes, files, images, pads are frozen at capture). Drift for non-repo sources is a post-v1 concern.

## Retrieval Model

Project-scoped. No cross-project retrieval in v1.

### What gets indexed in v1

- Pad titles, summaries, body chunks (by heading/section)
- Transcript segments
- Note paragraphs
- Extracted file text chunks (paragraph or page)
- Image descriptions + OCR text
- Citation excerpts
- Pad type, tags

### What does NOT get indexed in v1

- Full semantic index of every repo file. Repo stays citation-referenced with live file reads; we cite and fetch, we don't index.

### Pipeline

1. Keyword search via SQLite FTS5 over titles / summaries / chunk text.
2. Semantic retrieval over chunk embeddings.
3. Merge, dedupe, re-rank (pad type, recency, explicit links, shared sources).
4. Grounded answer generation with citations to pad chunks + source snapshots.

Hybrid from day one. Not semantic-only.

## AI Capabilities

### A. Draft pad (generalized)

Replace the RFC-only drafter with a generalized drafter:

- **Inputs:** pad type, selected sources (any mix of kinds), selected prior pads, template
- **Outputs:** pad body, citations, summary, explicit `pad_ref` links for derived drafts
- Keep the two-pass flow for repo sources (file selection, then draft)

### B. Continue pad

On an open pad:

- expand a section
- rewrite for clarity
- ground a paragraph against current sources
- compare against repo state
- extract decisions

### C. Ask across project

- query → grounded answer with citations
- optional scope filter by pad type, source, tag

### D. Suggest related pads

When viewing or drafting, show related pads ranked by:

1. explicit pad links
2. shared sources
3. shared tags
4. semantic similarity

### E. Drift and verification (already shipped for repos)

- Stays repo-only in v1.
- Generalizes to other sources in a post-v1 phase.

## Auth Model

Password-based. OAuth / SSO is vision.

**`User`:** `id`, `email`, `password_hash`, `email_verified_at`, `created_at`

**`Session`:** `id`, `user_id`, `token_hash`, `expires_at`, `created_at`

**`PasswordResetToken`:** `id`, `user_id`, `token_hash`, `expires_at`, `used_at`

Session-aware routes; signed-out users land on sign-in/sign-up.

## API Direction

Keep existing endpoints during migration; add project-scoped endpoints.

**New:**

- `POST /api/auth/sign-up`, `/api/auth/sign-in`, `/api/auth/sign-out`, `/api/auth/reset`
- `POST /api/scaffold` — the one-input onboarding endpoint; creates a project, attaches a source, drafts a first pad (or creates a stub). SSE-streamed.
- `GET /api/projects`, `POST /api/projects`, `GET /api/projects/{id}`
- `POST /api/projects/{id}/invites`, `POST /api/invites/accept`
- `GET /api/projects/{id}/pads`, `POST /api/projects/{id}/pads`
- `GET /api/pads/{id}`, `PUT /api/pads/{id}` (existing; gain project scoping via pad → project link)
- `POST /api/projects/{id}/sources` (multipart for file/image upload)
- `POST /api/uploads` — pre-upload for scaffold and source flows; returns file IDs to reference
- `POST /api/projects/{id}/search`, `POST /api/projects/{id}/ask`
- `GET /api/pads/{id}/related`

**Kept as-is (scoped through the pad):**

- `POST /api/specs/draft` — stays for now; folds into the generalized drafter endpoint during Phase 5
- `POST /api/pads/{id}/verify-citations`
- `GET /api/citations/{id}/preview`, `GET /api/citations/{id}/diff`

## UI Direction

Authenticated app shell:

- Project switcher (top-left)
- Primary nav: **Library**, **Threads**, **Ask**, **Sources**, **Members**
- Account menu (profile, sign out, settings)
- "New pad" primary CTA

**Public routes:** minimal landing placeholder, sign-in, sign-up, reset password, accept invite.

The single-file `App.tsx` monolith breaks up during this pass — routing + auth shell is the forcing function. Target structure:

- `src/routes/` — auth, project home, library, pad, ask, members
- `src/components/library/`
- `src/components/pad/`
- `src/components/sources/`
- `src/components/ask/`
- `src/store/` — project, pads, auth

## Build Order

Six phases. Do not start the next until the previous exits.

### Phase 1 — Auth + projects (≈ 2 weeks)

- `User`, `Session`, `PasswordResetToken` tables
- `Project`, `ProjectMember`, `Invite` tables
- `/api/auth/*`, `/api/projects/*`, invite flow
- Authenticated app shell: sign-in, sign-up, project switcher, empty project home

**Exit:** a user can sign up, create a project, invite a teammate, and land on project home.

### Phase 2 — Pads under projects + stub scaffold (≈ 2 weeks)

- Migrate existing pads: add `project_id`, `pad_type`, `status`, `summary`, `last_opened_at`; backfill a default project owned by the first user.
- Rename `SpecType` → `pad_type`; backfill existing RFCs.
- Library view: list, filter by type / status / owner, open pads directly.
- Manual pad creation for all four types.
- "New RFC" → "New pad" with type picker.
- **Stub scaffold:** `POST /api/scaffold` lands in its minimum form — creates a project, attaches a text input as a source, creates a stub pad with an inferred title + outline. No live drafting yet.

**Exit:** pads are clearly shared project objects, openable without opening a thread. A signed-in user can paste text into the scaffold dropzone and land inside a named project with an outlined stub pad.

### Phase 3 — Sources + file/image upload (≈ 2 weeks)

- `Source`, `SourceSnapshot`, `PadSourceLink` tables
- File upload endpoint + storage (disk locally, S3-compatible when hosted)
- Image upload with vision description + OCR
- Backfill `SpecSource` → `Source` / `SourceSnapshot`
- Citation kinds: `note_range`, `file_range`, `image_region`, `pad_ref`

**Exit:** user can attach a PDF, an image, or a folder to a project and use it as a citable source.

### Phase 4 — Search + ask (≈ 2 weeks)

- `SearchChunk`, `SearchEmbedding` tables
- Chunkers for pads, transcripts, notes, extracted file text
- FTS5 + semantic retrieval; hybrid re-ranking
- `/api/projects/{id}/search`, `/api/projects/{id}/ask`
- UI: search box in library, Ask panel

**Exit:** *"What did we decide about auth?"* returns a grounded answer with citations that jump to real pads and source excerpts.

### Phase 5 — Generalized drafting + rich scaffold (≈ 1–2 weeks)

- Drafter accepts any pad type, any mix of source kinds, selected prior pads.
- `pad_ref` citations written for derived drafts.
- `/api/specs/draft` folds into `/api/projects/{id}/pads/draft`.
- **Scaffold upgrade:** the scaffold flow now produces a live-drafted first pad (not just a stub) using the generalized drafter. Detects repo URLs in the input and offers to attach when a PAT is configured.

**Exit:** an ADR drafted from a PR + transcript + a prior RFC is materially better than the same draft without the prior RFC. A first-time user pastes a transcript into the scaffold dropzone and lands on a real drafted pad with citations.

### Phase 6 — Related pads + polish (≈ 1 week)

- `/api/pads/{id}/related` with hybrid ranking
- Drift surfacing in library filters
- Interaction polish (not marketing polish — that's post-v1)

**Exit:** v1 feels coherent end-to-end. Ready to put in front of external users.

**Total:** ~10–11 weeks focused; realistic 14–18.

## Migration Strategy

- All schema changes are additive. No destructive migrations.
- Existing single-user data becomes a default "personal" project, owned by the first user who signs in (or by a configured seed user during Phase 1 cutover).
- `SpecSource` stays in place through Phases 1–2; Phase 3 backfills to the new tables and freezes `SpecSource`.
- `Conversation` / `Message` stay; conversations become threads attached to a project and optionally to a pad.

## Risks

1. **Auth + projects before the memory loop is proven.** Mitigation: Phase 4 (search + ask) is where real value lands. Keep Phases 1–2 functional, not polished.
2. **"Multi-user" slides into enterprise-platform creep.** Mitigation: the non-goals list is hard. Reject "we also need" without a scope decision.
3. **File / image upload pipeline becomes a tar pit.** Mitigation: text-only extraction in v1; images get vision + OCR, nothing fancier; PDFs use `pdftotext`, not layout-aware parsers.
4. **Search quality is mediocre at first.** Mitigation: hybrid keyword + semantic from day one; don't ship semantic-only.
5. **The frontend monolith resists splitting.** Mitigation: routing + auth shell forces a real component tree. Stop patching `App.tsx`.
6. **Citation-across-many-source-kinds balloons model prompt size.** Mitigation: keep the two-pass file-selection pattern for repos; cap non-repo source attachments per draft (e.g. 5 files + 5 images).

## Success Criteria

- A first-time user can paste a transcript or upload a doc and, within 60 seconds, be inside a populated project with a drafted pad — no manual setup in between.
- A two-person team can sign up, create a project, attach a repo + a transcript + a PDF, draft an RFC, search the library, and get a grounded answer to a cross-pad question.
- A single user can use the same app with no sense of it being "for teams only."
- The existing RFC drafting + drift work still functions through the migration.
- Opening Workpad feels more natural than opening a blank doc or a blank chat for technical thinking.

The strongest behavioral test: when a teammate recovers reasoning about a past decision faster than they would by grepping code + slack + old docs, v1 is working. The strongest adoption test: a user who drops in with zero intent leaves their first session with a real pad they want to come back to.
