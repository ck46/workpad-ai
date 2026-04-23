# Workpad AI — v1 Backlog

Task list for implementing v1. Source of truth for scope and decisions: [`V1_SPEC.md`](./V1_SPEC.md).

The original wedge A+ (M0–M3 below) is **complete**. The consolidated v1 direction (auth + projects + library + sources + search + scaffolding) adds Phases 1–6. Check items off as they land.

---

## Phase 1 — Auth + projects (≈ 2 weeks)

Authenticated multi-user app shell; no product features added yet.

Broken into substeps 1A–1F that can be landed and tested independently. Items already shipped before Phase 1 was formally opened are marked `[x]` with their landing commit or date.

### 1A — Backlog refresh & pre-Phase-1 baseline

- [x] Consolidate v1 direction in docs (V1_SPEC, V1_BACKLOG, PRODUCT_VISION, EXPANSION_HYPOTHESES, CLAUDE.md; archive PERSONAL_MVP and WEB_MULTIUSER specs). *This commit.*
- [x] Baseline auth shipped pre-Phase-1 — `User` + `UserSession` models, `POST /api/auth/{signup,signin,signout}`, `GET /api/auth/me`, scrypt password hashing, 30-day HttpOnly cookie (`wp_session`), `get_current_user` dependency. ([`apps/api/src/app/auth.py`](../apps/api/src/app/auth.py))
- [x] Baseline ownership shipped pre-Phase-1 — `Conversation.owner_id` FK, all library queries scoped by caller. ([`apps/api/src/app/core.py`](../apps/api/src/app/core.py))

**Naming note:** shipped endpoints are `/signup` `/signin` `/signout` (not `/sign-up` etc). Frontend `auth.ts` calls the hyphenless form. Keep hyphenless — more ergonomic — and treat the earlier backlog naming as superseded.

**Baseline SHA note:** an earlier revision of this doc named `f2844f2` as the baseline-auth commit. That SHA was lost to a rebase and no longer exists in the repo; the code is live, the provenance isn't recoverable from git history — don't chase the hash.

### 1B — Password reset + auth tests

- [x] `PasswordResetToken` SQLAlchemy model (id, user_id FK CASCADE, token_hash, expires_at, used_at, created_at). *Commit `a9fdc0b`.*
- [x] `POST /api/auth/reset-request` — takes `{ email }`. Returns 202 on unknown email to avoid enumeration. Per-user 60s cooldown. Logs the reset URL to the app logger (no SMTP in v1; a real mailer is a separate concern). *Commit `a9fdc0b`.*
- [x] `POST /api/auth/reset-confirm` — takes `{ token, new_password }`. Consumes the token, updates `password_hash`, revokes ALL live `UserSession` rows for that user, leaves caller logged out. *Commit `a9fdc0b`.*
- [x] New `apps/api/tests/test_auth.py` covering signup/signin/signout/me/reset-request/reset-confirm: email normalization, duplicate rejection, short-password rejection, wrong-password signin 401, fresh cookie on signin, signout revocation, expired-session anonymity, unknown-email 202 with no URL logged, neutral-log behavior, cooldown, token reuse, token expiry, bogus token, short-new-password rejection. *Commit `e6f05c9`; 18 new tests.*
- [x] Also repaired `tests/test_library_api.py` (3 tests were 401-failing since `f2844f2` introduced auth) and added a shared `authed_client` / `authed_user` fixture in `conftest.py`. *Commit `b5218f1`.*

**Exit:** Forgotten-password round trip works end-to-end locally. `uv run pytest` is green with 60 tests (was 42).

### 1C — Project schema + endpoints

- [x] `Project` model (id, name, created_by_user_id, created_at, updated_at). *Commit `0ee5aa2`.*
- [x] `ProjectMember` model (id, project_id, user_id, role `owner|member`, created_at). Unique on `(project_id, user_id)`. *Commit `0ee5aa2`.*
- [x] `Invite` model with bearer-token semantics (id, project_id, email, token_hash, invited_by_user_id, accepted_at, expires_at, created_at). *Commit `0ee5aa2`.*
- [x] `POST /api/projects` — body `{ name }`. Creates project, adds caller as `owner` member. *Commit `534e62b`.*
- [x] `GET /api/projects` — list projects the caller is a member of. *Commit `534e62b`.*
- [x] `GET /api/projects/{id}` — 403 if caller not a member. Payload includes members + pending invites. *Commit `534e62b`.*
- [x] `POST /api/projects/{id}/invites` — owner-only. Body `{ email }`. Persists token hash; response includes `token` + `accept_url` (v1 has no mailer, caller copies the URL). *Commit `534e62b`.*
- [x] `POST /api/invites/accept` — body `{ token }`. If token valid + unexpired + unused, creates `ProjectMember` for the caller and marks invite accepted. Preserves an existing role when already a member (no accidental downgrade). *Commit `534e62b`.*
- [x] `apps/api/tests/test_projects.py` — 15 tests covering create (auth + blank-name), list scoping, detail membership guard + payload shape, owner-only invite creation, accept_url shape, invalid email, end-to-end invite flow, reuse rejection, expiry, bogus token, role preservation, accept auth guard. *Commit `a268dc1`.*

**Exit:** From the test suite end-to-end: signup user A, create project, issue invite, signup user B, accept invite, user B sees project in `GET /api/projects` and `GET /api/projects/{id}` as a `member`. 75 tests green (was 60).

### 1D — Scope pads + conversations to projects

- [x] Add nullable `project_id` FK to `Pad` (Artifact) and `Conversation`; SQLite ALTER + index in `_ensure_*_schema`. *Commit `5ce6f3b`.*
- [x] One-shot backfill on startup: group existing pads + conversations by owner; create a `"Personal"` project per owner and assign their rows to it. Orphan owner_ids (user deleted) and orphan artifacts (conversation deleted) stay with `project_id=NULL` and out of the library. *Commit `4d6d3a9`.*
- [x] Backfill is idempotent — selects only rows whose `project_id` is still NULL; safe to call every boot. *Commit `4d6d3a9`.*
- [x] Enforce `project_id` at the service layer on new pads/conversations via helper guards `_require_project_member_or_403`, `_require_artifact_access`, `_require_conversation_access` in `main.py`. *Commit `5b882dc`.*
- [x] `list_library_artifacts` and `list_conversations` filter by `project_id`; endpoint-level membership check replaces the old owner_id filter. All pad/conversation list + detail + mutate endpoints routed through the guards. *Commit `5b882dc`.*
- [x] `project_id` carried on `Artifact` rows (denormalized) and exposed via existing list/detail payloads.
- [x] Tests: backfill idempotency + orphan handling (6 tests in `test_projects_backfill.py`, commit `4d6d3a9`). Cross-project isolation (8 tests in `test_project_isolation.py`, commit `8e337f0`): non-member 403s on every pad/conversation endpoint, create-time validation (foreign project_id 403, cross-project conversation attach 400), list-endpoint query contract, happy-path invited-member access.

**Exit:** Existing local DB loads after migration with all pads under a per-user "Personal" project. Attempting to read a pad whose project you don't belong to returns 403. Test suite is 90 green (was 75 before Phase 1D).

### 1E — Frontend auth pages wired to backend

The marketing + signin/signup/forgot UI already existed in `apps/web/src/components/PublicPages.tsx` (hash routing) with `apps/web/src/lib/auth.ts` helpers. This substep wired the remaining flows.

- [x] Signin form wired to `signIn()` (pre-existing from `f2844f2`).
- [x] Signup form wired to `signUp()` (pre-existing).
- [x] Forgot-password form wired to `POST /api/auth/reset-request` with a neutral confirmation screen that matches the backend's 202-on-unknown behavior. Submitting state + inline error slot. *Commit `72a5f1d`.*
- [x] Reset-confirm page at `#/reset?token=...` → `POST /api/auth/reset-confirm`. Three states (missing token / form / success); matching-password + ≥8-chars validation; router extended to parse `#/<slug>?token=...`. *Commit `e9024de`.*
- [x] Invite-accept page at `#/invite?token=...`. Four states (missing token / anonymous / signed-in prompt / accepted). Calls `acceptInvite()` and routes to the new project on success. *Commit `339e5ae`.*
- [x] Anonymous-visitor invite round-trip: clicking "Sign in" or "Create an account" on `#/invite` stashes the token in sessionStorage; after auth the user is bounced back to `#/invite?token=...` instead of `#/app`. *Commit `3fa93f0`.*
- [x] Session bootstrap: `main.tsx::Root` calls `fetchCurrentUser()` on mount, renders a neutral loading shell while auth resolves, routes unauthenticated callers to the marketing page. (Pre-existing.)
- [x] Account menu in sidebar: initials avatar opens a popover with "Signed in as <email>", appearance toggle (light/dark/auto), and Sign out → calls `signOut()` and routes back to `#/marketing`. (Pre-existing from the reskin.)
- [x] API helpers added in `lib/auth.ts`: `requestPasswordReset`, `confirmPasswordReset`, `acceptInvite`, `stashPendingInvite`, `takePendingInvite`. *Commit `a25cea6`, extended in `3fa93f0`.*
- [x] Server errors surface via the existing `ErrorBanner` component (bad credentials, duplicate email, invalid token, short password, etc.).

**Exit met:** A fresh browser profile can complete every flow without touching the URL bar — sign up, sign out, sign back in, forget password, reset via the dev-logged URL, sign in with the new password, accept an invite from `#/invite?token=...`. `yarn build` typechecks and bundles green.

### 1F — Project switcher + project home

- [x] `lib/projects.ts` — thin fetch client for the Phase 1C endpoints (listProjects, createProject, getProjectDetail, createInvite) + shared types. *Commit `22f1170`.*
- [x] Current-project state in `useWorkbenchStore`: `projects`, `currentProjectId`, `setCurrentProject`, `upsertProject`. `currentProjectId` persisted to `localStorage` under `workpad-current-project` and reconciled against the live list on bootstrap. Brand-new users with no projects get an auto-created `Personal` client-side so the store always has something scoped. *Commit `f5149f1`.*
- [x] Every `/api/conversations` + `/api/library/artifacts` call now carries `project_id`. `startNewConversation`, `setShowArchived`, `draftSpec` (+ `NewSpecModal`), and `LibraryHome.tsx` all pull the current project from the store. *Commit `f5149f1`.*
- [x] Sidebar `ProjectSwitcher` component — dropdown listing the caller's projects + role badges, "New project" and "Project settings" entries, outside-click-to-close, active row highlighted with signal-soft. *Commit `f60a4e6`.*
- [x] `NewProjectModal` — name input + Create; on success upserts into the store, switches, and closes. Esc / outside-click to dismiss. *Commit `7ee3105`.*
- [x] `ProjectSettingsModal` — fetches `GET /api/projects/{id}`, renders members list (with owner/member badges) + pending invites + an owner-only invite form. New invites auto-copy the `accept_url` to the clipboard with a confirmation note that v1 has no mailer. *Commit `7ee3105`.*
- [x] `EmptyProjectHero` in `LibraryHome.tsx` — when `totalArtifacts === 0`, renders a dashed-border "Start your first pad" panel with a visibly-disabled scaffold drop zone ("Coming in Phase 2") and two working CTAs (Draft with AI → `NewSpecModal`; Start a blank pad → `startNewConversation`). Sets expectations against the "first session produces value" design principle. *Commit `b3016d9`.*

**Exit (Phase 1 end-to-end):** User A signs up → auto-Personal project → switches to create project "Acme" from the sidebar switcher → opens Project settings → invites `b@example.com` → copy the `accept_url` → user B opens it → signs up → lands on `#/invite?token=...` (token preserved via sessionStorage) → clicks Accept → switches into "Acme" → sees the same pads user A created → creates a pad which user A then sees. Existing SQLite DBs migrate under each owner's "Personal" project with no data loss.

---

## Phase 2 — Pads under projects + stub scaffold (≈ 2 weeks)

### Schema updates
- [x] `Pad` (Artifact) already carries `artifact_type` (=pad_type), `status`, `summary`, `last_opened_at`, `project_id` from earlier phases; `spec_type` retained for transitional library queries. *Pre-Phase-2 baseline.*
- [ ] Add `owner_user_id` and `created_by_user_id` columns to `Artifact` for "pads I created" / "owner" filter dimensions. *Deferred — not required to ship the scaffold, and the existing `Conversation.owner_id` trace already lets us derive this if needed.*

### Library view
- [x] Manual pad creation for all four types via `NewPadModal` (type picker tile grid, title input, POSTs to `/api/library/artifacts` with `artifact_type`). Replaces the old behavior where the sidebar "New pad" button only created an empty conversation. *Commit `6047e46`.*
- [x] Sidebar + library hero "New pad" buttons now open `NewPadModal`; "New thread" icon in the chat header still opens an empty conversation (the chat-only flow). *Commit `6047e46`.*
- [x] `GET /api/library/artifacts?project_id=...` already supports filtering by `artifact_type`/`status`/`q` from Phase 1D. The dedicated `GET /api/projects/{id}/pads` alias is a future polish.
- [x] Library list + open works without opening a thread (the existing `LibraryHome` already routes a click straight to the pad).

### Stub scaffold (first-run)
- [x] `POST /api/scaffold` — accepts `text`, `repo_url`, `hint`, optional `project_id`. *Commit `efa14ba`.*
- [x] Scaffold inference: single forced tool call (`infer_scaffold`) produces `{ project_name, pad_type, pad_title, outline_sections, detected_repo_urls }`. Regex fallback extracts `github.com/<owner>/<name>` from raw inputs when the model omits them. *Commit `efa14ba`.*
- [x] Creates project (when no `project_id`) + backing conversation + `Artifact` with markdown outline + `SpecSource` rows for both transcript and repo seeds. Caller becomes owner on a freshly-created project. *Commit `efa14ba`.*
- [x] Tests: 17 covering the pure helpers, the service against a real DB with a scripted AI client (happy path, project reuse, empty-input rejection, non-member rejection on existing projects, regex fallback), and the HTTP endpoint (auth gate, validation, 503 missing-key, mocked happy path). Suite went 90 → 107. *Commit `0e19450`.*
- [x] Functional dropzone in `EmptyProjectHero` (transcript textarea + repo URL + hint). Replaces the disabled "Coming in Phase 2" placeholder. Submits via the new `scaffoldFromInput` store action which scopes to the current project, refreshes the conversation list, and routes to the new pad. *Commit `a1532af`.*
- [ ] File upload as a scaffold input (out of scope for Phase 2 — slots into Phase 3's upload pipeline).

### Exit criterion
- [x] Pads are openable from the library without opening a thread.
- [x] A first-time user can paste text into the scaffold dropzone and land inside a populated project with an outlined stub pad.

**Status:** Phase 2 complete for v1's "first session produces value" path. Remaining items (`owner_user_id` columns, `/api/projects/{id}/pads` alias, file-upload scaffold input) are non-blocking polish and roll into Phase 3 or later.

---

## Phase 3 — Sources + file/image upload (≈ 2 weeks)

### Schema
- [ ] `Source`, `SourceSnapshot`, `PadSourceLink` tables (see `V1_SPEC.md` for fields).
- [ ] Backfill: for each `SpecSource`, create a `Source` + `SourceSnapshot` + `PadSourceLink`. Freeze `spec_sources` writes afterward.

### Upload pipeline
- [ ] `POST /api/uploads` — multipart; returns file IDs. Stores raw file on disk (local) or S3-compatible (hosted).
- [ ] Text extractors: `.md`/`.txt`/code (read), `.pdf` (pdftotext), `.docx` (python-docx), images (vision model + OCR).
- [ ] Folder upload: server-side unzip; one `Source` per file with shared parent id.
- [ ] Size caps: 20 MB images, 50 MB files, 200 MB folder zip.

### Source endpoints
- [ ] `POST /api/projects/{id}/sources` — create source from upload IDs, URL, or paste.
- [ ] `GET /api/projects/{id}/sources`.
- [ ] `GET /api/sources/{id}` (access check via project membership).

### Citation extensions
- [ ] Add `note_range`, `file_range`, `image_region`, `pad_ref` to citation kinds.
- [ ] Add `source_snapshot_id` and `excerpt_text_at_capture` columns to `Citation`.

### Frontend
- [ ] Sources view in project nav.
- [ ] File / folder / image upload UI.
- [ ] Citation pill variants for new kinds.

### Exit criterion
- [ ] User can attach a PDF, an image, or a folder and use it as a citable source in a pad.

---

## Phase 4 — Search + ask (≈ 2 weeks)

### Schema
- [ ] `SearchChunk` table (owner kind/id, chunk type, heading, text, ordinal, hash, metadata).
- [ ] `SearchEmbedding` table (chunk_id, model, vector).
- [ ] SQLite FTS5 virtual table over chunk text.

### Chunkers
- [ ] Pad chunker (by heading/section).
- [ ] Transcript segment chunker.
- [ ] Note paragraph chunker.
- [ ] File text chunker (paragraph / page).
- [ ] Backfill chunks for existing pads + snapshots.

### Retrieval
- [ ] Keyword query via FTS5.
- [ ] Semantic query via embeddings (cosine).
- [ ] Hybrid merge + re-rank (pad type, recency, explicit links, shared sources).

### Endpoints
- [ ] `POST /api/projects/{id}/search` — returns chunk results with pad context.
- [ ] `POST /api/projects/{id}/ask` — SSE-streamed grounded answer + citations.

### Frontend
- [ ] Library search bar.
- [ ] Ask panel (dedicated surface).
- [ ] Result cards jump to pads and source excerpts.

### Exit criterion
- [ ] *"What did we decide about auth?"* returns a grounded answer with citations that jump to real pads and source excerpts.

---

## Phase 5 — Generalized drafting + rich scaffold (≈ 1–2 weeks)

### Drafter
- [ ] Generalize `rfc_drafter.py` → `pad_drafter.py`. Accepts pad type, source mix, prior pads.
- [ ] Templates for each of the four pad types.
- [ ] Write `pad_ref` citations when prior pads are used.
- [ ] `POST /api/projects/{id}/pads/draft` (SSE).

### Scaffold upgrade
- [ ] Scaffold now calls the generalized drafter to produce a real draft, not just a stub outline.
- [ ] Detect repo URLs in the input; attach when a PAT is configured, skip cleanly otherwise.

### Legacy folding
- [ ] Mark `POST /api/specs/draft` deprecated; route internally to the new drafter.

### Exit criterion
- [ ] An ADR drafted from a PR + transcript + a prior RFC is materially better than the same draft without the prior RFC. A first-time user pastes a transcript into the scaffold dropzone and lands on a drafted pad with citations.

---

## Phase 6 — Related pads + polish (≈ 1 week)

- [ ] `GET /api/pads/{id}/related` with hybrid ranking (explicit links, shared sources, shared tags, semantic similarity).
- [ ] Library filter: "has stale citations".
- [ ] Drift badge in pad list rows.
- [ ] Interaction polish (loading states, error toasts, keyboard shortcuts).

### Exit criterion
- [ ] v1 feels coherent end-to-end. Ready to put in front of external users.

---

## Archive — Wedge A+ (M0–M3, complete as of 2026-04-19)

The original narrow wedge shipped. All checkboxes below are complete. Kept for reference.

### M0 — Schema + GitHub Client (≈ 1 week)

Foundation. Nothing user-facing ships in M0.

### Database schema
- [x] Add `spec_type` (nullable, default NULL) column to `Pad` SQLAlchemy model in `apps/api/src/app/core.py`.
- [x] Define `SpecSource` SQLAlchemy model (id, pad_id FK, kind, payload JSON, created_at).
- [x] Define `Citation` SQLAlchemy model (id, pad_id FK, anchor, kind, target JSON, resolved_state, last_checked_at, last_observed JSON).
- [x] Define `RepoCache` SQLAlchemy model (id, repo, ref, path, content BLOB, content_hash, etag, fetched_at; unique index on (repo, ref, path)).
- [x] Ensure `Base.metadata.create_all` covers the new tables on `init_db`.
- [x] Add Pydantic `SpecType`, `CitationKind`, `ResolvedState` enums to `schemas.py`.
- [x] Add Pydantic read models: `SpecSourceRead`, `CitationRead`.

### GitHub client (`github_client.py`)
- [x] Create new module `apps/api/src/app/github_client.py`.
- [x] Implement `get_tree(repo, ref) -> list[str]` — returns file paths at ref.
- [x] Implement `get_file(repo, ref, path) -> FileContent` — raw bytes, sha, etag.
- [x] Implement `get_pr(repo, number) -> PRMeta`.
- [x] Implement `get_commit(repo, sha) -> CommitMeta`.
- [x] Implement `resolve_head(repo) -> sha` — current HEAD sha of default branch (or user-specified branch).
- [x] Wire conditional requests (send `If-None-Match` with cached etag; treat 304 as cache-still-valid).
- [x] Handle rate-limit headers (`X-RateLimit-Remaining`); fail fast with a descriptive error when near zero.

### Cache layer
- [x] Cache read path: check `RepoCache` first; on hit, send conditional GET; on 304 update `fetched_at` and return cached content; on 200 overwrite entry.
- [x] TTL invalidation (24h) — only relevant when ETag-less responses come back.
- [x] Helper: `content_hash_for_range(file_bytes, line_start, line_end) -> str`.

### Settings & env
- [x] Add `GITHUB_DEFAULT_TOKEN` env var to `Settings` (optional; clearly errors if missing when a repo flow is invoked).
- [x] Update `.env.example` with a placeholder for `GITHUB_DEFAULT_TOKEN`.

### Tests
- [x] Unit test for `content_hash_for_range` (stable hashing across newline styles).
- [x] Integration test (offline, mocked httpx) for the cache: fetch → re-fetch → 304 → cache hit.
- [x] Integration test for rate-limit near-zero handling.
- [x] Scaffold `apps/api/tests/` with `conftest.py` providing an in-memory SQLite + fresh `Settings`.

### Exit criterion
- [x] From a Python REPL: `github_client.get_file(repo, sha, path)` returns content; `content_hash_for_range(content, 42, 58)` returns a stable hash; running the same call again hits the cache (304 response or `fetched_at` updated). *Verified 2026-04-17 via the smoke script in the commit body.*

---

## M1 — Draft Flow (≈ 2 weeks)

First user-visible feature. Paste transcript + point at repo → RFC with citation pills.

### Transcript handling
- [x] Implement `parse_transcript(text) -> TranscriptPayload` — detects `HH:MM:SS` / `[HH:MM:SS]` markers; returns `text + hash + segments?`.
- [x] Fallback: character-offset ranges when no timestamps.
- [x] Unit tests with three sample transcripts (Otter-style, Granola-style, rough paste).

### AI tool schemas
- [x] Define `pick_relevant_files` tool schema (strict) — input: transcript + repo index; output: `{ paths: string[], reasoning: string }`, `max_paths: 15`.
- [x] Define `draft_rfc` tool schema (strict) — output: `{ title, markdown_body, citations: [{ anchor, kind, target }] }`.
- [x] Keep `canvas_apply` tool schema intact for legacy flows (do not break existing generic pads).

### Drafter (`rfc_drafter.py`)
- [x] Create new module `apps/api/src/app/rfc_drafter.py` (scaffold with injected deps; methods land in follow-ups).
- [x] Build repo index: file tree, top-level directory names, README content, manifest file (`package.json`, `pyproject.toml`, `go.mod`, etc. — pick first found).
- [x] Pass 1: call model with `pick_relevant_files` tool and `tool_choice` forcing it.
- [x] Pass 2: fetch picked files via `github_client` + cache, build system + user prompt, call model with `draft_rfc` tool.
- [x] Parse and validate each citation's `target` against the repo snapshot; drop invalid citations (log them as `draft_drop` events for prompt iteration).
- [x] Persist `Pad` (`spec_type="rfc"`, content = markdown_body), `SpecSource` (transcript + repo with `ref_pinned`), and `Citation` rows in one transaction.

### Draft endpoint
- [x] Add `POST /api/specs/draft` route in `main.py`.
- [x] Request body: `{ conversation_id?, transcript, repo_url, repo_token_ref? }`.
- [x] SSE event sequence: `draft.pass1.started` → `draft.pass1.completed` (with selected paths) → `draft.pass2.started` → `draft.citations` (streamed as they land) → `pad.created` → `stream.completed`.
- [x] Error events for: repo unreachable, invalid PAT, transcript missing, model failure.

### Extend existing endpoints
- [x] `GET /api/pads/{id}` returns citations inline.
- [x] `GET /api/conversations/{id}` returns `spec_type` for each pad.

### Frontend: new-spec modal
- [x] Component for the modal (in `App.tsx` for now — do not break the file up unless a larger refactor is scheduled).
- [x] Transcript textarea with character count.
- [x] Repo URL input (accept `org/name` or full `https://github.com/...` URL; parse on submit).
- [x] Optional PAT input; otherwise server uses `GITHUB_DEFAULT_TOKEN`.
- [x] "Draft RFC" button → opens SSE to `/api/specs/draft`.
- [x] Progress UI: "Selecting relevant files…" → "Drafting…" → "Verifying citations…" → done.

### Frontend: Citation TipTap node
- [x] Install/implement a custom TipTap inline node that matches `[[cite:<anchor>]]` tokens.
- [x] Render as non-editable pill with a kind-specific icon (file, PR, commit, transcript) + truncated target (e.g. `auth.ts:42`).
- [x] No popover or status badge yet — those are M2.
- [x] Ensure pills survive copy/paste and export cleanly.

### Frontend: store changes
- [x] Extend Zustand store with `citations: Citation[]` for the active pad.
- [x] Action `draftSpec({ transcript, repoUrl, token? })` orchestrates the SSE stream.
- [x] Update `selectConversation` / `persistActivePad` to round-trip citations correctly.

### Exit criterion
- [x] User flow: open app → "New RFC" → paste a real transcript → enter a real repo URL → click Draft → RFC streams in with citation pills that point at valid files/PRs/commits. *Wired end-to-end on 2026-04-18; 33/33 backend tests pass, frontend typechecks + builds, Docker stack boots, `POST /api/specs/draft` streams the structured SSE sequence, and `invalid_pat` is returned when no PAT is set. A live demo run is gated on a `GITHUB_DEFAULT_TOKEN` + `OPENAI_API_KEY` being present in `.env`.*

---

## M2 — Verify / Drift (≈ 1 week)

The "living" half of the wedge. Make stale spec obvious.

### Backend: verifier
- [x] Create new module `apps/api/src/app/citation_verifier.py`.
- [x] `verify_citations(pad_id, session) -> VerifyResult`:
  - [x] Resolve current HEAD sha for each repo referenced.
  - [x] For `repo_range`: fetch file at HEAD (via cache), hash the *pinned* line range from draft-time content, compare to `content_hash_at_draft`.
  - [x] If mismatched, run a content-match search to suggest a new line range; write to `last_observed`.
  - [x] For `repo_pr`: fetch PR; update metadata; `live` unless deleted.
  - [x] For `repo_commit`: confirm SHA resolves; `live` or `missing`.
  - [x] For `transcript_range`: always `live`.
- [x] Cap at 50 citations per pass; return `{ truncated: true, remaining: N }` when exceeded.
- [x] Persist updated `resolved_state`, `last_checked_at`, `last_observed`.

### Verify endpoint
- [x] Add `POST /api/pads/{id}/verify-citations` route.
- [x] Returns updated citations (full `CitationRead` list) + summary: `{ live, stale, missing }` counts.
- [x] Optional query param `force=true` to bypass same-minute dedupe.

### Frontend: citation status
- [x] Extend Citation pill with status badge (green/amber/red) based on `resolved_state`.
- [x] Click pill → popover with:
  - [x] Source kind + target summary (path, PR title, commit SHA, timestamp).
  - [x] Status label.
  - [x] If stale: "moved to `lib/auth/verify.ts:12-28`" (from `last_observed`).
  - [x] "View in GitHub" link.

### Frontend: drift banner
- [x] Banner component at the top of `WorkpadPane` when any citation is stale/missing.
- [x] Text: `"N of M citations have drifted since draft at <sha[:7]>"`.
- [x] Clicking the banner scrolls to the first stale citation.

### Frontend: verify trigger
- [x] Auto-verify on spec open (once per session; dedupe by pad id).
- [x] Manual "Verify citations" button in the workpad toolbar (next to Copy / Download).
- [x] Loading state while verifying; error state with retry on failure.

### Exit criterion
- [x] Create a spec against a test repo; edit the cited file in the repo (rename the function); reopen the spec; stale badge + drift banner appear; popover shows the new location. *Wired end-to-end on 2026-04-19; 34/34 backend tests pass (new verifier E2E asserts live/stale/missing + suggested_range + path_gone), frontend typechecks + builds, Docker stack boots, `POST /api/pads/{id}/verify-citations` returns the expected auth error when no PAT is set. A live run is gated on `GITHUB_DEFAULT_TOKEN` in `.env`.*

---

## M3 — Polish (≈ 1 week)

Make the 60-second demo tight.

### Backend
- [x] `GET /api/citations/{id}/preview` — returns current content around the target (with a small context window).
- [x] `GET /api/citations/{id}/diff` — for stale citations, returns unified diff between draft-time and current content.
- [x] Update markdown export (`core.py::export_pad`) to render citation pills as footnotes: `content[^cite-a3f9]` with a `[^cite-a3f9]: path/file.ts L42-58 (https://github.com/...)` footer.
- [x] Ensure HTML / DOCX / PDF exports include citation links too (adapt `_iter_markdown_blocks` or post-process).
- [x] Add graceful errors for: repo unreachable (403/404), expired PAT (401), file 404 at HEAD. *Error classifier in `spec_service.py` maps to structured `{code, message}` events; frontend `Toaster` surfaces them.*

### Frontend
- [x] Citation hover preview (200ms debounce; fetch via `/preview`; cache in session).
- [x] Stale citation diff view (collapsed by default; expand on click).
- [x] Error toasts for repo / auth failures during draft and verify.
- [x] Empty-state for new-spec modal if `GITHUB_DEFAULT_TOKEN` is missing: link to setup instructions.
- [x] Polish: loading skeletons for citations while draft streams.

### Exit criterion
- [x] The 60-second demo from `V1_SPEC.md` runs end-to-end without surprises. Record it. *Polish shipped on 2026-04-19; 37/37 backend tests pass (new preview + diff coverage), frontend typechecks + builds, Docker stack boots, `GET /api/settings/info` reports secret presence, verify / preview / diff all return structured errors when secrets are absent. A recorded demo is gated on `GITHUB_DEFAULT_TOKEN` + `OPENAI_API_KEY` being set; all backend + frontend paths are wired.*

---

## Cross-cutting / infra

Not tied to a single milestone. Pick up as needed.

- [ ] Decide: OpenAI vs Anthropic for the two-pass drafting. (Model selector already exists in `App.tsx`; backend `rfc_drafter.py` should be provider-agnostic or select based on request.)
- [x] Add `apps/api/tests/conftest.py` with reusable fixtures (in-memory SQLite, mock GitHub, mock model). *Shipped in M0 with `engine` + `session_factory` + `session` fixtures; `StaticPool` added in M1 so multi-session tests see the same in-memory DB.*
- [ ] `ruff` + `mypy` config for the backend (small scope — just the new modules).
- [ ] Structured logging around draft and verify passes (model, tokens, latency, dropped citations).
- [ ] `apps/api/README.md` or module docstrings covering the draft + verify flow end to end.
- [ ] CI workflow (GitHub Actions): `yarn build` + `uv run pytest` on PR.

---

## Demo-readiness checklist (run before showing anyone)

- [ ] Fresh browser profile — no stale localStorage.
- [ ] Fresh DB (`rm apps/api/data/workpad.db` then restart).
- [ ] Pre-seed a transcript and repo URL in a text file for quick paste.
- [ ] Verify citations survive a page reload.
- [ ] Verify the drift detection triggers on an actual code move (not just a line-number shift).
- [ ] Record the 60-second demo to share async.
