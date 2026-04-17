# Workpad AI — v1 Spec (Wedge A+)

> Draft + live-resolving citations + drift badges. One user, one repo, one transcript, one spec type.

See `docs/PRODUCT_VISION.md` for the long-horizon vision. This document intentionally narrows scope.

## The 60-Second Demo

The success criterion for v1. If a staff engineer can watch this and ask "when can I have it?", v1 is done.

1. User starts a new RFC, pastes a meeting transcript, points at a GitHub repo.
2. AI drafts the RFC. Inline citations appear as pills: `[src/auth.ts:42–58]`, `[#PR-234]`, `[commit abc1234]`, `[transcript:4:12–5:03]`.
3. Hovering a repo citation previews the current code at that location.
4. User closes the spec. Time passes. Code evolves.
5. User reopens the spec. A top-of-document banner reads **"3 citations have drifted since you wrote this."**
6. Stale citations show amber badges; clicking shows a before/after diff. Missing citations (path gone) show red.

That is the whole wedge. Everything else is v2.

## Scope — In

- Artifact type: **RFC only** (one type).
- Sources: **GitHub repo** (read-only) and **pasted transcript** (plain text). Nothing else.
- AI capabilities: **draft** (from sources) and **verify** (re-resolve citations on demand).
- Citation kinds: repo file/line range, repo PR, repo commit, transcript timestamp range.
- Drift detection: on spec open, re-fetch repo citations; compare content hash; render status.
- Existing features retained: TipTap markdown editing, Monaco (unused in v1 but stays in the codebase for later spec types), version history on the artifact, exports.

## Scope — Out (Punt List)

Explicit non-goals for v1. Anything here requires a scope-change conversation, not a "while we're at it."

- Slack / Teams / Discord integration
- Figma / Excalidraw / Mermaid / image upload
- Meeting recording, note-taker plugins, A/V upload, transcription
- Other spec types (ADR, PRD, post-mortem, runbook)
- Spec library search, tagging, backlinks, cross-spec citations
- Multi-user, sharing, comments, permissions
- Notifications or scheduled re-verification (manual "Verify" only in v1)
- Linear / Jira / GitHub Issues as first-class sources
- Onboarding answer mode
- Self-hosted deployment story
- OAuth for GitHub (PAT only in v1)
- Organization / workspace concept (single-user local app for v1)
- Billing, accounts, auth of any kind

## Data Model

Extensions to the existing schema (`apps/api/src/app/core.py`). Existing `Conversation`, `Message`, `Artifact`, `ArtifactVersion` tables stay.

### `Artifact` — extend

Add:
- `spec_type: str` — enum-ish. v1: `"rfc"` only. Default `"rfc"` for new artifacts created via the v1 flow. Existing markdown artifacts stay as plain content; `spec_type` nullable.

### `SpecSource` — new

An immutable record of a source attached to a spec at draft time. Used later for re-resolution and provenance.

- `id`
- `artifact_id` (FK → `Artifact`)
- `kind`: `"transcript" | "repo"`
- `payload`: JSON — shape depends on kind:
  - `transcript`: `{ "text": "...", "hash": "...", "segments": [{ "start": "00:04:12", "end": "00:05:03", "text": "..." }] | null }` — `segments` is populated at draft time when timestamp markers (e.g. `HH:MM:SS` or `[HH:MM:SS]`) are detected in the paste; otherwise null, and `transcript_range` citations fall back to character-offset ranges inside `text`.
  - `repo`: `{ "repo": "org/name", "ref_pinned": "sha_at_draft_time" }` — `ref_pinned` is the commit SHA at HEAD when the spec was drafted. All repo citations store claims *as of this SHA*; drift is computed by comparing current HEAD against it.
- `created_at`

Existing untyped artifacts (created before v1) keep `spec_type = NULL`, have no `SpecSource` or `Citation` rows, and render as plain markdown with no citation UI. The new flow is purely additive — no migration, no breakage.

### `Citation` — new

One row per inline citation in a spec.

- `id`
- `artifact_id` (FK → `Artifact`)
- `anchor`: stable string ID — emitted by the model, used to locate the citation in the markdown source (e.g. `[[cite:a3f9]]`)
- `kind`: `"repo_range" | "repo_pr" | "repo_commit" | "transcript_range"`
- `target`: JSON — shape depends on kind:
  - `repo_range`: `{ "repo": "...", "ref_at_draft": "sha", "path": "...", "line_start": 42, "line_end": 58, "content_hash_at_draft": "..." }`
  - `repo_pr`: `{ "repo": "...", "number": 234, "title_at_draft": "..." }`
  - `repo_commit`: `{ "repo": "...", "sha": "..." }`
  - `transcript_range`: `{ "source_id": "...", "start": "00:04:12", "end": "00:05:03" }`
- `resolved_state`: `"live" | "stale" | "missing" | "unknown"`
- `last_checked_at`
- `last_observed`: JSON — e.g. current content hash and current line range after re-resolution

## User Flows

### Author flow

1. User clicks **New RFC**.
2. Modal: textarea for transcript, dropdown for GitHub repo (or "+ Connect repo" entering a repo URL + PAT).
3. On **Draft**:
   - Backend stores a `SpecSource` row for the transcript.
   - Backend fetches a lightweight repo snapshot: tree (paths only), last 20 PRs (titles + numbers), recent commit SHAs (to define `ref_at_draft`). Stores a `SpecSource` row for the repo with `ref_at_draft = HEAD sha`.
   - Backend calls the model with a new tool `draft_rfc` whose schema produces `{ title, markdown_body, citations: [...] }`. The markdown body contains `[[cite:<anchor>]]` tokens; `citations` is the list with full target data keyed by anchor.
   - On completion, backend creates the `Artifact` (markdown content with citation tokens inline), writes all `Citation` rows, and streams the result to the client.
4. Artifact opens in the workpad. TipTap renders citation tokens as pills with live data.

### Reread flow

1. User opens an existing spec.
2. Client requests the spec; server returns artifact + citations with their last resolved state.
3. Client calls `POST /api/artifacts/{id}/verify-citations` (lazy, on first open OR manual button).
4. Server iterates citations and compares *pinned SHA* (from `target.ref_at_draft`) against *current HEAD*, using the `repo_cache` table to avoid duplicate fetches:
   - For `repo_range`: fetch the file at current HEAD; compute the hash of the pinned line range; if it matches `content_hash_at_draft` → `live`. If the file exists but the quoted content has moved or changed → `stale`; write observed hash + any discovered new line range to `last_observed`. If the path is gone at HEAD → `missing`.
   - For `repo_pr`: fetch PR; `live` unless deleted; changes in open/merged/closed state are surfaced but do not mark stale.
   - For `repo_commit`: verify SHA still resolves at HEAD's history; `live` or `missing`.
   - For `transcript_range`: always `live` — transcripts are frozen at draft.
5. Server returns updated states; client paints badges and a top-of-spec summary ("N citations have drifted since draft at `sha[:7]`").

### Manual edit flow

User can still edit markdown directly. Citation tokens are preserved as immutable marks in TipTap (cannot be partially edited, only removed wholesale). A future feature will let users add citations manually via a "+" in the toolbar; not in v1.

## Technical Shape

### Backend (FastAPI)

New / extended:
- `db`: add `spec_type` column to `artifacts`; new `spec_sources`, `citations`, and `repo_cache` tables via SQLAlchemy migration.
- `github_client.py`: thin wrapper over `httpx` to call GitHub REST + GraphQL. No PyGithub (too heavy). Sends conditional requests (`If-None-Match` with stored ETag) to conserve the 5K/hr budget.
- `repo_cache`: SQLite table keyed by `(repo, ref, path)` storing `content BLOB, content_hash, etag, fetched_at`. Populated by `github_client` reads; consulted on every subsequent read of the same `(repo, ref, path)`. Shared between draft and verify passes. Entries expire after 24h or on explicit invalidation.
- `rfc_drafter.py`: runs the two-pass draft flow (see AI Integration), persists sources and citations.
- `citation_verifier.py`: batch verification for a spec; caps at 50 citations per pass with a graceful "truncated" response for larger specs.
- Routes:
  - `POST /api/specs/draft` — body: `{ transcript, repo_url, repo_token_ref }`. Streams SSE; creates artifact + sources + citations.
  - `POST /api/artifacts/{id}/verify-citations` — returns updated citation states.
  - `GET /api/artifacts/{id}` — existing; now also returns citations.
- Settings: add `GITHUB_DEFAULT_TOKEN` env var for v1 single-user use. (Later: per-repo tokens in DB.)

### Frontend (React + TipTap)

New / extended:
- Citation TipTap node: custom extension that renders `[[cite:<anchor>]]` tokens as a pill with status badge. Non-editable internals; click → popover with source preview.
- New-spec modal: transcript textarea + repo picker (URL + optional PAT stored server-side).
- Drift banner component at the top of the workpad when the current artifact has citations with `resolved_state != "live"`.
- Citation popover: shows the current code (fetched on hover) and, for stale citations, a minimal diff.
- "Verify citations" toolbar button (glass-button style, next to Copy / Download).

### AI Integration

- New tool `draft_rfc` replaces `canvas_apply` for the v1 flow. Strict schema:
  ```
  { title: string,
    markdown_body: string,  // contains [[cite:<anchor>]] tokens
    citations: [
      { anchor: string,
        kind: "repo_range" | "repo_pr" | "repo_commit" | "transcript_range",
        target: {...}        // shape per kind
      }
    ]
  }
  ```
- **Two-pass drafting.**
  - **Pass 1 (file selection).** Send the model a cheap repo *index* — file tree (paths only), top-level directory summaries, README contents, `package.json` / `pyproject.toml` / equivalent manifest — along with the full transcript. Ask it via a `pick_relevant_files` tool to return up to ~15 file paths it believes are relevant to drafting the RFC, plus a short reasoning string. Model handles domain jargon that grep-by-identifier heuristics miss.
  - **Pass 2 (draft).** Fetch the selected files in full (via `repo_cache`), plus recent PR titles and commit summaries. Call the model with `draft_rfc` to produce the final RFC with citations pointing only into material the model actually saw.
- Server-side validation: every citation's `target` is checked against the repo snapshot before persisting. Invalid citations (non-existent paths, line ranges past EOF) are silently dropped and logged for prompt iteration.
- `canvas_apply` tool remains for non-v1 flows (existing markdown artifacts still editable).

## Decisions Locked for v1

Decisions made 2026-04-17, folded into the sections above for reference:

1. **Ref strategy.** Pin citations to the commit SHA at draft time; drift is computed by comparing the pinned SHA against current HEAD.
2. **File selection.** Two-pass drafting — model picks relevant files from a cheap repo index in pass 1, then drafts with full contents in pass 2.
3. **Rate limits.** SQLite `repo_cache` table keyed by `(repo, ref, path)` with ETags for conditional requests. Cap v1 verify at 50 citations per pass.
4. **Citation syntax.** `[[cite:<anchor>]]` tokens in stored markdown; TipTap renders them as non-editable inline pills; exports render them as markdown footnotes with source links.
5. **Transcripts.** Stored as a blob. Timestamp markers (`HH:MM:SS` style) parsed into segments at draft time when present; character-offset ranges used as fallback.
6. **Existing artifacts.** Additive-only. Untyped artifacts keep `spec_type = NULL`, no migration, no citation UI.

## Milestones

Rough sizing, assuming solo / evenings-and-weekends pace.

### M0 — Schema + GitHub client (≈ 1 week)
- Add `spec_type` to `artifacts`; add `spec_sources`, `citations`.
- `github_client.py`: get tree, get file (raw), get PR, get commit, search code.
- Env-var-based PAT.
- Unit tests for the client.
- **Exit criterion:** from a Python REPL, can fetch a file + compute a content hash for a range.

### M1 — Draft flow (≈ 2 weeks)
- `rfc_drafter.py` + `draft_rfc` tool schema.
- `POST /api/specs/draft` SSE endpoint.
- New-spec modal in the frontend.
- Citation TipTap node (render only; no interactions yet).
- **Exit criterion:** paste transcript + repo URL → RFC with citation pills appears in the workpad.

### M2 — Verify / drift (≈ 1 week)
- `citation_verifier.py`.
- `POST /api/artifacts/{id}/verify-citations`.
- Badges on citations; drift banner.
- Auto-verify on open; manual "Verify" button.
- **Exit criterion:** editing the repo (moving a function) and reopening the spec produces a stale badge + diff.

### M3 — Polish (≈ 1 week)
- Hover preview on citations (fetch on demand, cache for session).
- Stale-citation diff view.
- Export preserves citations as markdown footnotes with source links.
- Error states (repo unreachable, PAT expired, file 404).
- **Exit criterion:** the 60-second demo runs end to end without surprises.

**Total:** ~5 weeks of focused work. Add buffer; realistically 6–8.

## Dependencies to Add

- Backend: `httpx` (probably already transitively via FastAPI), `githubkit` (optional; nice typed client).
- Frontend: `@tiptap/core` extensions — a custom node implementation (no new dep).

## Risks

- **Draft quality.** If the RFC draft is not noticeably better than "paste transcript + repo README into Claude," the wedge fails. Mitigation: invest in prompt quality and the relevant-file selection heuristic early.
- **Citation hallucination.** The model may invent paths or line numbers. Mitigation: validate every citation server-side against the repo snapshot; silently drop invalid ones before storing (and log them for prompt iteration).
- **GitHub rate limits on larger repos.** Mitigation: cache aggressively; in v1, cap at 50 citations per verify pass with a graceful message.
- **The demo reads as "neat" but not "need."** Biggest product risk. Mitigation: before M2, walk through the flow with 2–3 staff engineers we have access to; if no pull, reconsider before M3 polish.

## What Comes Next (v1.5+, not part of this spec)

For context only; implementing any of these is out of scope for v1.

- ADR type (tighter structure: context / options / decision / consequences).
- Scheduled re-verification + weekly drift digest.
- Slack integration for permalink citations.
- Image / diagram upload with vision.
- Spec library search and cross-spec backlinks.
- Meeting transcript imports from note-taker webhooks.
