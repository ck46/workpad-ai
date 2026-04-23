# Workpad AI

Workpad AI is a split-pane chat and artifact workspace built around OpenAI GPT-5.4. The left pane handles conversation; the right pane is a persistent work surface for drafts, code, notes, and structured documents.

This repository contains the current local-first implementation: a React/Vite frontend, a FastAPI backend, and a SQLite database. Docker Compose is the primary way to run the full stack in development.

> **Security note.** This is a single-user, localhost-only tool. There is **no authentication or authorization** on any API endpoint. Anyone who can reach the API can read, modify, or delete every conversation and artifact. Do **not** expose the backend to a public network, a shared host, or the open internet. Run it on `localhost` or behind a VPN or SSH tunnel you control.

## Repo Layout

| Path | Purpose |
| --- | --- |
| `apps/web` | React + Vite frontend |
| `apps/api` | FastAPI backend, SQLite-backed app state, AI integrations |
| `docs` | Product vision, specs, and migration notes |
| `docker-compose.yml` | Full-stack local orchestration |

For backend-specific details, see [apps/api/README.md](./apps/api/README.md).

## Stack

- Frontend: React, TypeScript, Vite, Tailwind CSS, Zustand, Monaco, TipTap
- Backend: Python 3.11+, FastAPI, SQLAlchemy, SQLite, OpenAI Responses API
- Tooling: `yarn` for the frontend, `uv` for the backend
- Local orchestration: Docker Compose

## Run With Docker

1. Copy `.env.example` to `.env`.
2. Set `OPENAI_API_KEY`.
3. Optionally set `GITHUB_DEFAULT_TOKEN` if you want to use the RFC drafting and citation verification flows against GitHub repositories.

```bash
docker compose up --build
```

Then open `http://localhost:3000`.

Service endpoints:

- Web UI: `http://localhost:3000`
- API: `http://localhost:8088`
- API health check: `http://localhost:8088/healthz`

## Run Without Docker

Backend:

```bash
cd apps/api
uv sync --extra dev
uv run uvicorn src.app.main:app --reload --host 0.0.0.0 --port 8000
```

Frontend:

```bash
cd apps/web
yarn install
yarn dev
```

Notes:

- Before starting the backend directly, export `OPENAI_API_KEY` in your shell or create `apps/api/.env`.
- The backend reads `.env` from `apps/api` when run directly; Docker Compose reads the repo-root `.env`.
- The frontend falls back to `http://localhost:8000` when `VITE_API_URL` is unset.

## Common Development Commands

Backend:

```bash
cd apps/api
uv run pytest
uv run ruff check
uv run mypy
```

Frontend:

```bash
cd apps/web
yarn build
```

## Current Behavior

- Chat streams from the FastAPI backend over Server-Sent Events.
- GPT-5.4 is wired through the Responses API with a strict `canvas_apply` tool.
- Artifact edits are versioned and persisted in SQLite.
- Markdown artifacts render in TipTap; code artifacts render in Monaco.
- The backend also supports RFC drafting, GitHub-backed source fetching, and citation verification workflows.

## Product Docs

- [docs/PRODUCT_VISION.md](./docs/PRODUCT_VISION.md): long-term product direction
- [docs/V1_SPEC.md](./docs/V1_SPEC.md): original RFC-focused wedge
- [docs/WEB_MULTIUSER_SPEC.md](./docs/WEB_MULTIUSER_SPEC.md): current multi-user web direction and migration plan
- [docs/PERSONAL_MVP_SPEC.md](./docs/PERSONAL_MVP_SPEC.md): prior single-user product direction
