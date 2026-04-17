# Workpad AI

Workpad AI is a split-pane chat and artifact workspace built around OpenAI GPT-5.4. The left side behaves like a modern chat app, while the right side is a durable work surface for drafts, code, and structured documents.

For the product vision, see [docs/PRODUCT_VISION.md](./docs/PRODUCT_VISION.md). For the committed v1 scope, see [docs/V1_SPEC.md](./docs/V1_SPEC.md).

> **Security note.** This is a single-user, localhost-only tool. There is **no authentication or authorization** on any API endpoint — anyone who can reach the API can read, modify, or delete every conversation and artifact. Do **not** expose the backend to a public network, a shared host, or the open internet. Run it on `localhost` or behind a VPN/SSH tunnel you control.

## Stack

- Frontend: React, TypeScript, Vite, Tailwind CSS, Zustand, Monaco, TipTap
- Backend: Python, FastAPI, SQLAlchemy, SQLite, OpenAI Responses API
- Package managers: `yarn` for the frontend, `uv` for the backend
- Local orchestration: Docker Compose

## Run Locally

### Docker Compose

1. Copy `.env.example` to `.env` and set `OPENAI_API_KEY`.
2. Run:

```bash
docker compose up --build
```

3. Open `http://localhost:3000`.

### Without Docker

Backend:

```bash
cd apps/api
uv sync
uv run uvicorn src.app.main:app --reload --host 0.0.0.0 --port 8000
```

Frontend:

```bash
cd apps/web
yarn install
yarn dev
```

## Key Behavior

- Streaming chat uses Server-Sent Events from the FastAPI backend.
- GPT-5.4 uses the Responses API with a strict `canvas_apply` tool.
- Artifact edits are versioned and persisted in SQLite.
- Markdown artifacts render in TipTap; code artifacts render in Monaco.
