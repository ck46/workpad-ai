# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Product Direction

Workpad AI is **"living specs for small engineering teams (2–10) and serious individuals"** — PRDs, RFCs, ADRs, design notes, run notes wired to their source systems (GitHub repos, meeting transcripts, uploaded files, images, etc.) so they don't rot.

- `docs/PRODUCT_VISION.md` — long-horizon vision. Source of truth for where the product is going (CLI, MCP server, coding-agent interop, agents, cloud connectors — all post-v1).
- `docs/V1_SPEC.md` — **consolidated v1 spec**. Auth + projects (top-level container, no workspace layer) + four pad types + five source kinds + scaffolding + search/ask. Supersedes the earlier narrow-wedge v1 and the personal/multi-user branches.
- `docs/V1_BACKLOG.md` — phases 1–6 task list. The original wedge A+ (M0–M3: RFC drafting + citations + drift) is **complete** and kept as archive at the bottom; the consolidated direction builds on top of it.
- `docs/archive/` — `PERSONAL_MVP_SPEC.md` and `WEB_MULTIUSER_SPEC.md`, kept for historical context. Do not build against them.

**Design principle: first session must produce value.** A new user arrives with one input (pasted transcript, uploaded doc, dragged folder, chat message) and lands inside a populated project with a real pad. Manual setup is the fallback path, not the default. When making UX decisions, ask: *does this step sit between the user and their first useful pad?* If yes, cut it.

`README.md` describes the *current implementation* (split-pane chat + pad with `canvas_apply`, plus the shipped RFC drafting flow), which predates the consolidated direction — treat the docs above as source of truth for direction.

## Commands

### Docker Compose (primary dev loop)
```bash
docker compose up --build           # full stack; web on :3000, api on :8088
docker compose up -d --build web    # rebuild & restart frontend only (code changes)
docker compose up -d --build api    # rebuild & restart backend only
docker compose ps                   # check container health
```
The web container runs `yarn dev` (Vite), so any `src/` change triggers HMR inside the container. Use rebuild-web only when `package.json`, config files, or non-HMR resources change.

### Backend — `apps/api`
```bash
cd apps/api
uv sync                                                      # install deps
uv run uvicorn src.app.main:app --reload --port 8000         # local dev without docker
uv run pytest                                                # run tests (tests/ is currently empty)
uv run pytest tests/path/test_file.py::test_name -v          # single test
```

### Frontend — `apps/web`
```bash
cd apps/web
yarn install
yarn dev                    # Vite dev server on :3000
yarn build                  # tsc --noEmit && vite build (runs typecheck)
yarn preview                # preview the production build
```
`yarn build` is the canonical typecheck — there's no separate `tsc` script.

### Env
Copy `.env.example` → `.env` and set `OPENAI_API_KEY`. The backend reads env via `pydantic-settings` in `Settings` (`apps/api/src/app/core.py`).

## Architecture

### Big picture
Split-pane app: chat on the left, durable pad workspace on the right. User messages flow to FastAPI, which streams back Server-Sent Events carrying assistant text *and* pad mutations. The AI model decides when to create/update a pad via a structured tool call; the backend applies the mutation, persists a version, and streams the pad back to the client in the same SSE stream.

### SSE streaming contract (`apps/api/src/app/openai_service.py`)
`WorkpadOpenAIService.stream_chat` is a **two-pass** call against the OpenAI Responses API:
1. **First pass.** Streams assistant text deltas (`assistant.message.*` events) and collects any `canvas_apply` function calls.
2. If a tool was called: backend applies it via `apply_canvas_tool`, emits `pad.started` / `pad.delta` / `pad.completed` events, and runs a **second pass** with `tool_choice="none"` and the `previous_response_id` so the model can produce a closing natural-language reply grounded in the tool result.

Frontend (`apps/web/src/App.tsx`, `readSseStream`) consumes these events and updates the Zustand store accordingly.

### `canvas_apply` tool
Single structured tool the model calls to mutate pads. Defined in `openai_service.py::_tool_schema`, validated server-side into `CanvasToolCall` (`schemas.py`), applied by `apply_canvas_tool` (`core.py`). Three actions:
- `create` — new pad.
- `replace` — full rewrite.
- `patch` — ordered search-and-replace edits (`SearchReplacePatch`); fails loudly on missing targets unless `allow_missing=True`.

Every mutation bumps `Pad.version` and writes an `PadVersion` row — the history is immutable and kept forever.

### Database
SQLAlchemy + SQLite (file: `apps/api/data/workpad.db`). Four tables, all defined in `apps/api/src/app/core.py`:
- `Conversation` — holds messages + pads; title auto-derives from the first user message.
- `Message` — role + content, chronological per conversation.
- `Pad` — latest state of a canvas document (markdown / python / html / etc.). Optimistic concurrency via `version` + `expected_version` on manual edits (`update_pad_manually`).
- `PadVersion` — full snapshot per change with the tool summary that produced it.

`get_engine` / `get_session_factory` are `lru_cache`'d module-level singletons. Tests must clear them if they mutate settings.

### Export pipeline (`core.py::export_pad`)
Markdown pads are parsed into a block list by `_iter_markdown_blocks` and rendered to `.md` / `.html` / `.txt` / `.docx` / `.pdf` via `python-markdown`, `python-docx`, and `reportlab`. All exports share the same block parser — fix the parser once, all formats benefit.

### Frontend
- **Single-file architecture.** `apps/web/src/App.tsx` (≈1000+ lines) contains types, Zustand store, API helpers, SSE handling, and all UI components. The `src/components`, `src/store`, `src/lib`, `src/types` directories exist but are empty scaffolding — do *not* treat them as the source of truth. Refactoring out of the monolith is an open task, not done piecemeal.
- **Editors.** `MarkdownEditor` (TipTap) for `content_type === "markdown"`; `@monaco-editor/react` for code content types. Undo/redo dispatches into whichever editor is active via refs.
- **Canvas theme.** Per-user light/dark toggle scoped to the inner editor only; the outer panel shell, header, toolbar, and sidebar stay dark. Preference persists in `localStorage` (`workpad-canvas-theme`). Same pattern for the sidebar collapse state (`workpad-sidebar-collapsed`).
- **Autosave.** `useAutosave` debounces `persistActivePad` after each change. Optimistic-concurrency via `expected_version` on the PUT.

## Conventions & gotchas

- **CORS.** Backend accepts `http://localhost:3000` and `host.docker.internal:3000` by default. Docker web container connects to api through port 8088 on the host.
- **Empty API submodules.** `apps/api/src/app/api/`, `core/`, `db/`, `models/`, `schemas/`, `services/` directories exist but are empty. Actual code lives at `app/core.py`, `app/schemas.py`, `app/openai_service.py`, `app/main.py`. Treat the subdirs as aspirational until someone populates them.
- **Model env.** `OPENAI_MODEL` defaults to `gpt-5.4`, `OPENAI_REASONING_EFFORT` to `medium`. Both are read from `Settings`.
- **Pad concurrency.** `update_pad_manually` raises `ValueError` (→ 409) on version mismatch. The frontend refetches on 409; don't silently retry.

## Commits

- **Step-by-step, incremental.** Never bundle unrelated changes into one big commit. Each commit is a small, logically coherent unit that builds on the previous one and is independently reviewable.
- **When multiple changes are pending, commit them one at a time.** Split doc rewrites, schema changes, endpoint additions, frontend wiring, and terminology renames into separate commits even if they all arose in the same session.
- **Trailer format.** End every commit message with a single trailer line: `AI assistant: <model>` — for example `AI assistant: Claude Opus 4.7 (1M context)`. Do **not** use the `Co-Authored-By:` line; the AI is an assistant, not a co-author.

## Product scope constraints

- **No legal/contracts vertical.** The maintainer works on a similar legal-AI product elsewhere; this project must stay out of that space. See `docs/PRODUCT_VISION.md` "What This Is Not."
- **Small teams + individuals.** Target is 2–10 person engineering teams and serious individual engineers. The app must feel equally useful to one person and to a small team. Do not add enterprise features (SSO, SCIM, fine-grained ACLs, admin consoles, billing) without an explicit scope change.
- **Projects as top-level container.** No workspace layer above projects. A project has members (roles: `owner | member`, nothing more). If a feature would justify adding roles/visibility/ACLs, defer it unless there's a concrete user asking.
- **v1 non-goals (hard list).** CLI, MCP server, cloud connectors (GitHub App OAuth, Slack, Drive, Figma, Linear, Jira), coding-agent plugins (Claude Code, Codex, Cursor), agents management, speech/audio/video, native Excalidraw, polished landing page, comments/mentions/notifications/inbox, scheduled background jobs. These are all real vision items — they live in `PRODUCT_VISION.md` and are explicitly out of v1.
