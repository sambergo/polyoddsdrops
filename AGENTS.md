# Repository Guidelines

## Project Structure & Module Organization
- `src/`: Python package for market discovery, WebSocket monitoring, Redis publishing, and the FastAPI server (`src/api/server.py`).
- `main.py`: Primary entry point that initializes the database, fetches markets, runs monitoring, and can build/serve the UI.
- `ui/`: React + TypeScript Vite app (components, hooks, styles) served by the API when built.
- `scripts/`: One-off discovery/analysis scripts (Gamma/CLOB exploration, filters, sampling).
- `docs/`: API/data model notes, roadmap, and JSON samples.
- `data/`: SQLite database (`data/polydrop.db`) and runtime artifacts.

## Build, Test, and Development Commands
Python (uses `uv`):
- `uv run python main.py`: Run the full monitor + API server.
- `uv run python -m src.api.server`: Run only the FastAPI server.
- `uv run scripts/fetch_markets.py`: Example discovery script.
- `uv add <package>`: Add dependencies (do not edit `pyproject.toml` manually).

UI (from `ui/`):
- `bun run dev` or `npm run dev`: Start Vite dev server.
- `bun run build` or `npm run build`: Type-check and build.
- `bun run lint` or `npm run lint`: ESLint.

## Coding Style & Naming Conventions
- Python: 4-space indent, type hints used throughout. Keep functions small and prefer explicit names (`price_tracker`, `subscription_manager`).
- TypeScript/React: 2-space indent, single quotes, no semicolons. Components in `PascalCase`, hooks in `useCamelCase`.
- Configuration: environment variables via `.env` (see `src/config.py` defaults). Example: `POLYDROP_DB_PATH=data/polydrop.db`.

## Testing Guidelines
- No test suite is currently checked in. If you add tests, use `pytest` and place them under `tests/` (e.g., `tests/test_monitoring.py`). Document new commands here.

## Commit & Pull Request Guidelines
- Commit history is short and informal (e.g., `feat: notifications`, `fix filters`, `clean`). Keep messages concise and action-oriented; optional `feat:`/`fix:` prefixes are welcome.
- PRs should include: a clear description, how you tested (commands), and screenshots for UI changes. Link related issues if applicable.

## Security & Configuration Tips
- Do not commit `.env`, API tokens, or Redis credentials. Prefer local `.env` files and document new settings in `src/config.py` and this guide.
