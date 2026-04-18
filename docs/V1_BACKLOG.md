# Workpad AI — v1 Backlog

Task list for implementing the v1 wedge (**A+**: draft RFC from transcript + GitHub repo with live-resolving citations and drift badges). Source of truth for scope and decisions: [`V1_SPEC.md`](./V1_SPEC.md).

Check items off as they land. Move finished milestones to an "archive" section if this gets long.

---

## M0 — Schema + GitHub Client (≈ 1 week)

Foundation. Nothing user-facing ships in M0.

### Database schema
- [x] Add `spec_type` (nullable, default NULL) column to `Artifact` SQLAlchemy model in `apps/api/src/app/core.py`.
- [x] Define `SpecSource` SQLAlchemy model (id, artifact_id FK, kind, payload JSON, created_at).
- [x] Define `Citation` SQLAlchemy model (id, artifact_id FK, anchor, kind, target JSON, resolved_state, last_checked_at, last_observed JSON).
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
- [ ] Keep `canvas_apply` tool schema intact for legacy flows (do not break existing generic artifacts).

### Drafter (`rfc_drafter.py`)
- [ ] Create new module `apps/api/src/app/rfc_drafter.py`.
- [ ] Build repo index: file tree, top-level directory names, README content, manifest file (`package.json`, `pyproject.toml`, `go.mod`, etc. — pick first found).
- [ ] Pass 1: call model with `pick_relevant_files` tool and `tool_choice` forcing it.
- [ ] Pass 2: fetch picked files via `github_client` + cache, build system + user prompt, call model with `draft_rfc` tool.
- [ ] Parse and validate each citation's `target` against the repo snapshot; drop invalid citations (log them as `draft_drop` events for prompt iteration).
- [ ] Persist `Artifact` (`spec_type="rfc"`, content = markdown_body), `SpecSource` (transcript + repo with `ref_pinned`), and `Citation` rows in one transaction.

### Draft endpoint
- [ ] Add `POST /api/specs/draft` route in `main.py`.
- [ ] Request body: `{ conversation_id?, transcript, repo_url, repo_token_ref? }`.
- [ ] SSE event sequence: `draft.pass1.started` → `draft.pass1.completed` (with selected paths) → `draft.pass2.started` → `draft.citations` (streamed as they land) → `artifact.created` → `stream.completed`.
- [ ] Error events for: repo unreachable, invalid PAT, transcript missing, model failure.

### Extend existing endpoints
- [ ] `GET /api/artifacts/{id}` returns citations inline.
- [ ] `GET /api/conversations/{id}` returns `spec_type` for each artifact.

### Frontend: new-spec modal
- [ ] Component for the modal (in `App.tsx` for now — do not break the file up unless a larger refactor is scheduled).
- [ ] Transcript textarea with character count.
- [ ] Repo URL input (accept `org/name` or full `https://github.com/...` URL; parse on submit).
- [ ] Optional PAT input; otherwise server uses `GITHUB_DEFAULT_TOKEN`.
- [ ] "Draft RFC" button → opens SSE to `/api/specs/draft`.
- [ ] Progress UI: "Selecting relevant files…" → "Drafting…" → "Verifying citations…" → done.

### Frontend: Citation TipTap node
- [ ] Install/implement a custom TipTap inline node that matches `[[cite:<anchor>]]` tokens.
- [ ] Render as non-editable pill with a kind-specific icon (file, PR, commit, transcript) + truncated target (e.g. `auth.ts:42`).
- [ ] No popover or status badge yet — those are M2.
- [ ] Ensure pills survive copy/paste and export cleanly.

### Frontend: store changes
- [ ] Extend Zustand store with `citations: Citation[]` for the active artifact.
- [ ] Action `draftSpec({ transcript, repoUrl, token? })` orchestrates the SSE stream.
- [ ] Update `selectConversation` / `persistActiveArtifact` to round-trip citations correctly.

### Exit criterion
- [ ] User flow: open app → "New RFC" → paste a real transcript → enter a real repo URL → click Draft → RFC streams in with citation pills that point at valid files/PRs/commits.

---

## M2 — Verify / Drift (≈ 1 week)

The "living" half of the wedge. Make stale spec obvious.

### Backend: verifier
- [ ] Create new module `apps/api/src/app/citation_verifier.py`.
- [ ] `verify_citations(artifact_id, session) -> VerifyResult`:
  - [ ] Resolve current HEAD sha for each repo referenced.
  - [ ] For `repo_range`: fetch file at HEAD (via cache), hash the *pinned* line range from draft-time content, compare to `content_hash_at_draft`.
  - [ ] If mismatched, run a content-match search to suggest a new line range; write to `last_observed`.
  - [ ] For `repo_pr`: fetch PR; update metadata; `live` unless deleted.
  - [ ] For `repo_commit`: confirm SHA resolves; `live` or `missing`.
  - [ ] For `transcript_range`: always `live`.
- [ ] Cap at 50 citations per pass; return `{ truncated: true, remaining: N }` when exceeded.
- [ ] Persist updated `resolved_state`, `last_checked_at`, `last_observed`.

### Verify endpoint
- [ ] Add `POST /api/artifacts/{id}/verify-citations` route.
- [ ] Returns updated citations (full `CitationRead` list) + summary: `{ live, stale, missing }` counts.
- [ ] Optional query param `force=true` to bypass same-minute dedupe.

### Frontend: citation status
- [ ] Extend Citation pill with status badge (green/amber/red) based on `resolved_state`.
- [ ] Click pill → popover with:
  - [ ] Source kind + target summary (path, PR title, commit SHA, timestamp).
  - [ ] Status label.
  - [ ] If stale: "moved to `lib/auth/verify.ts:12-28`" (from `last_observed`).
  - [ ] "View in GitHub" link.

### Frontend: drift banner
- [ ] Banner component at the top of `WorkpadPane` when any citation is stale/missing.
- [ ] Text: `"N of M citations have drifted since draft at <sha[:7]>"`.
- [ ] Clicking the banner scrolls to the first stale citation.

### Frontend: verify trigger
- [ ] Auto-verify on spec open (once per session; dedupe by artifact id).
- [ ] Manual "Verify citations" button in the workpad toolbar (next to Copy / Download).
- [ ] Loading state while verifying; error state with retry on failure.

### Exit criterion
- [ ] Create a spec against a test repo; edit the cited file in the repo (rename the function); reopen the spec; stale badge + drift banner appear; popover shows the new location.

---

## M3 — Polish (≈ 1 week)

Make the 60-second demo tight.

### Backend
- [ ] `GET /api/citations/{id}/preview` — returns current content around the target (with a small context window).
- [ ] `GET /api/citations/{id}/diff` — for stale citations, returns unified diff between draft-time and current content.
- [ ] Update markdown export (`core.py::export_artifact`) to render citation pills as footnotes: `content[^cite-a3f9]` with a `[^cite-a3f9]: path/file.ts L42-58 (https://github.com/...)` footer.
- [ ] Ensure HTML / DOCX / PDF exports include citation links too (adapt `_iter_markdown_blocks` or post-process).
- [ ] Add graceful errors for: repo unreachable (403/404), expired PAT (401), file 404 at HEAD.

### Frontend
- [ ] Citation hover preview (200ms debounce; fetch via `/preview`; cache in session).
- [ ] Stale citation diff view (collapsed by default; expand on click).
- [ ] Error toasts for repo / auth failures during draft and verify.
- [ ] Empty-state for new-spec modal if `GITHUB_DEFAULT_TOKEN` is missing: link to setup instructions.
- [ ] Polish: loading skeletons for citations while draft streams.

### Exit criterion
- [ ] The 60-second demo from `V1_SPEC.md` runs end-to-end without surprises. Record it.

---

## Cross-cutting / infra

Not tied to a single milestone. Pick up as needed.

- [ ] Decide: OpenAI vs Anthropic for the two-pass drafting. (Model selector already exists in `App.tsx`; backend `rfc_drafter.py` should be provider-agnostic or select based on request.)
- [ ] Add `apps/api/tests/conftest.py` with reusable fixtures (in-memory SQLite, mock GitHub, mock model).
- [ ] `ruff` + `mypy` config for the backend (small scope — just the new modules).
- [ ] Structured logging around draft and verify passes (model, tokens, latency, dropped citations).
- [ ] `apps/api/README.md` or module docstrings covering the draft + verify flow end to end.
- [ ] Initialize git repository at the project root (currently not a git repo — see `CLAUDE.md`).
- [ ] CI workflow (GitHub Actions): `yarn build` + `uv run pytest` on PR.

---

## Preflight (do before M0)

- [ ] Re-read `V1_SPEC.md` end-to-end.
- [ ] Generate a GitHub PAT with `repo:read` scope; set `GITHUB_DEFAULT_TOKEN` locally.
- [ ] Identify the repo you'll use as the demo target for M1 smoke tests.
- [ ] Confirm `docker compose up --build` still runs cleanly on current `main`.

---

## Demo-readiness checklist (run before showing anyone)

- [ ] Fresh browser profile — no stale localStorage.
- [ ] Fresh DB (`rm apps/api/data/workpad.db` then restart).
- [ ] Pre-seed a transcript and repo URL in a text file for quick paste.
- [ ] Verify citations survive a page reload.
- [ ] Verify the drift detection triggers on an actual code move (not just a line-number shift).
- [ ] Record the 60-second demo to share async.
