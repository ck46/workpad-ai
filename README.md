# Workpad AI

**Living specs for small engineering teams (2–10) and serious individuals.** PRDs, RFCs, ADRs, design notes, and run notes that stay wired to the sources that justify them — repos, meeting transcripts, uploaded files, images — so they don't rot.

Long-horizon direction: [`docs/PRODUCT_VISION.md`](./docs/PRODUCT_VISION.md). Consolidated v1 scope: [`docs/V1_SPEC.md`](./docs/V1_SPEC.md). Phase-by-phase progress: [`docs/V1_BACKLOG.md`](./docs/V1_BACKLOG.md).

## Status

v1 is in progress. The original RFC drafting + citation-drift wedge (M0–M3) is shipped; Phases 1 (auth + projects) and 2 (pads under projects + scaffold) are complete, and Phase 3 (sources) is landing stream by stream. Track the state in the backlog.

## Repo Layout

| Path | Purpose |
| --- | --- |
| `apps/web` | React + Vite frontend |
| `apps/api` | FastAPI backend, SQLite-backed state, AI integrations |
| `docs` | Product vision, v1 spec, backlog, archived earlier specs |
| `docker-compose.yml` | Full-stack local orchestration |

Backend details, module map, and the M1/M2 SSE event sequences: [`apps/api/README.md`](./apps/api/README.md).

## Stack

- Frontend: React, TypeScript, Vite, Tailwind CSS, Zustand, Monaco, TipTap
- Backend: Python 3.11+, FastAPI, SQLAlchemy, SQLite, OpenAI Responses API
- Tooling: `yarn` (frontend), `uv` (backend), Docker Compose for local orchestration

## Run It

Copy `.env.example` to `.env` and set `OPENAI_API_KEY`. Optionally set `GITHUB_DEFAULT_TOKEN` to enable the RFC drafting + citation verification flows against real repos.

```bash
docker compose up --build
```

- Web UI: <http://localhost:3000>
- API: <http://localhost:8088> (`/healthz` returns `{"status": "ok"}`)

The web container runs Vite with hot reload, so edits under `apps/web/src/` refresh without a rebuild. Rebuild only when `package.json`, Vite config, or non-HMR resources change:

```bash
docker compose up -d --build web   # frontend only
docker compose up -d --build api   # backend only
```

## Run Without Docker

```bash
# Backend
cd apps/api
uv sync --extra dev
uv run uvicorn src.app.main:app --reload --port 8000

# Frontend (in another shell)
cd apps/web
yarn install
yarn dev
```

The frontend falls back to `http://localhost:8000` when `VITE_API_URL` is unset. `OPENAI_API_KEY` must be in your shell or in `apps/api/.env` when running the backend outside Docker.

## Development Commands

```bash
# Backend
cd apps/api
uv run pytest              # full suite
uv run ruff check          # lint (scoped to new modules)
uv run mypy                # type-check (scoped to new modules)

# Frontend
cd apps/web
yarn build                 # tsc --noEmit && vite build
```

## Further Reading

- [`docs/PRODUCT_VISION.md`](./docs/PRODUCT_VISION.md) — long-horizon vision (CLI, MCP, connectors, coding-agent interop; all post-v1)
- [`docs/V1_SPEC.md`](./docs/V1_SPEC.md) — consolidated v1 scope and data model
- [`docs/V1_BACKLOG.md`](./docs/V1_BACKLOG.md) — phase-by-phase task list
- [`docs/archive/`](./docs/archive/) — earlier single-user and multi-user spec branches, kept for historical context
- [`CLAUDE.md`](./CLAUDE.md) — conventions and commit style for AI-assisted work on this repo
