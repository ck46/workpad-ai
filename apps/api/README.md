# workpad-ai-api

FastAPI backend for Workpad AI. Serves the split-pane chat + pad
workspace, drafts and verifies RFCs against GitHub repos, and owns
the SQLite schema for users, projects, pads, sources, and citations.

See `../../CLAUDE.md` for the big picture and `../../docs/V1_SPEC.md`
for the consolidated v1 direction.

## Run it

```bash
uv sync --extra dev                                    # install everything incl. dev tooling
uv run uvicorn src.app.main:app --reload --port 8000   # local dev server
uv run pytest                                          # full test suite
uv run ruff check                                      # lint (scoped — see pyproject.toml)
uv run mypy                                            # type-check (scoped)
```

Copy `../../.env.example` to `../../.env` and set at least
`OPENAI_API_KEY`. `GITHUB_DEFAULT_TOKEN` is required for the RFC
drafter and citation verifier.

Docker is the primary loop — run `docker compose up --build` from the
repo root for the full stack; this README is for people working on the
API in isolation.

## Module map

| Path | Responsibility |
| ---- | -------------- |
| `src/app/main.py` | FastAPI app, route wiring, membership guards, SSE assembly |
| `src/app/core.py` | Shared SQLAlchemy base, engine, settings, export pipeline |
| `src/app/auth.py` | `User`, `UserSession`, `PasswordResetToken`, cookie auth |
| `src/app/projects.py` | `Project`, `ProjectMember`, `Invite`, membership helpers, backfill |
| `src/app/sources.py` | `Source`, `SourceSnapshot`, `PadSourceLink` (Phase 3) |
| `src/app/rfc_drafter.py` | Two-pass drafter — `pick_relevant_files` → `draft_rfc` |
| `src/app/spec_service.py` | SSE glue for `POST /api/specs/draft` + verify-citations |
| `src/app/citation_verifier.py` | Re-resolves repo citations against HEAD, flags drift |
| `src/app/github_client.py` | GitHub API client with conditional GET + `RepoCache` |
| `src/app/scaffold_service.py` | One-input scaffold → project + pad + sources |
| `src/app/openai_service.py` | Chat-side SSE + `canvas_apply` tool for generic pads |
| `src/app/schemas.py` | Pydantic read/request models |
| `src/app/transcripts.py` | Transcript parsing (Otter / Granola / raw paste) |

## Draft flow (M1)

`POST /api/specs/draft` → `spec_service.stream_draft()` emits SSE
events in this order:

1. `draft.pass1.started` — drafter has picked files
2. `draft.pass1.completed` — payload includes chosen paths + reasoning
3. `draft.pass2.started` — model begins writing `draft_rfc`
4. `draft.citations` — one event per citation as they validate
5. `pad.created` — serialized `Artifact` row
6. `stream.completed` — terminal

Errors come back as structured events: `repo_unreachable`,
`invalid_pat`, `transcript_missing`, `model_failure`. The frontend
`Toaster` renders them.

## Verify flow (M2)

`POST /api/pads/{id}/verify-citations` → `citation_verifier.verify_citations()`
re-resolves each repo citation against the current HEAD, updates
`resolved_state`, and writes suggested line ranges to `last_observed`
for stale rows. Capped at 50 citations per pass.

## Where new code goes

- New SQLAlchemy models → dedicated module, registered via a local
  import inside `init_db()` so `Base.metadata.create_all` picks it up.
  `sources.py` is the current template.
- New endpoints → `main.py`, routed through the existing
  `_require_project_member_or_403` guard.
- Anything expensive or stateful (AI calls, GitHub fetches) lives in
  its own `*_service.py` module and is injected into the route via
  constructor deps so tests can stub it.
- Add new modules to `[tool.ruff]` and `[tool.mypy]` `include` /
  `files` lists in `pyproject.toml` so they're linted and typed.
