# Repository Guidelines

## Project Structure & Module Organization

Polyoddsdrops monitors Polymarket sports markets and serves a React dashboard. `main.py` orchestrates monitoring, market refresh, Redis publishing, SQLite writes, and the API server. Backend code lives in `src/`: `api/` has FastAPI/SSE, `monitoring/` tracks prices and alerts, `websocket/` handles CLOB feeds, `gamma/` and `clob/` wrap external APIs, `db/` owns SQLite, and `config.py` loads env vars. Frontend code lives in `ui/src/`, with UI in `components/`, hooks in `hooks/`, and shared types in `types.ts`. Utility scripts live in `scripts/`. Runtime data is stored under `data/`; do not commit local databases.

## Build, Test, and Development Commands

- `uv sync` installs Python dependencies.
- `cp .env.example .env` creates the required local configuration.
- `uv run python main.py` starts monitoring, Redis publishing, API, and UI.
- `uv run python -m src.api.server` runs only the API server.
- `uv run ruff check .` lints Python; `uv run ruff format .` formats it.
- `cd ui && bun install` installs frontend dependencies.
- `cd ui && bun run dev` starts Vite.
- `cd ui && bun run build` type-checks and builds `ui/dist/`.
- `cd ui && bun run lint` runs ESLint.
- `docker compose up -d --build` runs the stack.

## Coding Style & Naming Conventions

Use Python 3.13, type hints, dataclasses for structured records, and async APIs for network or streaming code. Keep module names lowercase with underscores and configuration centralized in `src/config.py`. Use `uv add <package>` for dependencies. Frontend code uses TypeScript, React function components, PascalCase component files, and camelCase hooks beginning with `use`.

## Testing Guidelines

No committed test suite is present yet. For backend changes, add focused `pytest` tests under a new `tests/` tree, mirroring source modules where practical, such as `tests/monitoring/test_price_tracker.py`. For UI changes, run `cd ui && bun run build` and `cd ui && bun run lint`. For full-system changes, validate with Redis running.

## Commit & Pull Request Guidelines

Recent history uses short, imperative commits, often lowercase, with occasional `feat:` prefixes. Use subjects like `fix disconnected warnings` or `feat: add alert cooldown metric`. Pull requests should describe behavior changes, note config changes, list validation commands, and include screenshots for UI changes.

## Security & Configuration Tips

All `POLYDROP_*` variables are required and should be documented in `.env.example` when added. Never commit `.env`, SQLite files, API credentials, or generated caches. Treat API and WebSocket parsing changes carefully; they affect live monitoring reliability.
