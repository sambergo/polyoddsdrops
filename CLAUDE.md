# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Polydrop is a Polymarket odds dropper for sports markets - monitors sharp price movements in prediction markets. Similar to Pinnacle odds dropper services but for Polymarket.

## Commands

```bash
# Run the application
uv run python main.py              # Start monitoring (WS + API server + UI)
uv run python -m src.api.server   # Run only the FastAPI server

# Linting
uv run ruff check .                # Python lint
uv run ruff format .               # Python format

# Web UI (React/TypeScript/Vite, requires bun)
cd ui && bun install                  # Install frontend deps
cd ui && bun run build                # Build to ui/dist/ (served by FastAPI)
cd ui && bun run dev                  # Dev server with hot reload
cd ui && bun run lint                 # ESLint

# Deployment
./deploy.sh <host>                    # rsync + docker compose up (or set DEPLOY_HOST)
docker compose up -d --build          # Local Docker (app + Redis + Caddy)

# Discovery scripts
uv run scripts/fetch_markets.py       # Fetch markets from CLOB/Gamma APIs
uv run scripts/find_sports_markets.py # Discover sports markets by tag
uv run scripts/explore_websocket.py   # Explore WebSocket real-time feeds

# Database inspection
sqlite3 data/polydrop.db ".tables"
sqlite3 data/polydrop.db "SELECT COUNT(*) FROM markets"

# Add dependencies (never edit pyproject.toml directly)
uv add <package>
```

## Environment Variables

All variables are **required** (loaded via `src/config.py` using `_require()`). Use `.env.example` as a reference. Key variables:

```bash
POLYDROP_SPORTS=nfl,nba,nhl          # Sports to monitor, or "all" for dynamic discovery
POLYDROP_DB_PATH=data/polydrop.db
POLYDROP_MIN_LIQUIDITY=10000
POLYDROP_MAX_SPREAD=0.10
POLYDROP_MIN_VOLUME_24H=5000
POLYDROP_MIN_PRICE=0.05
POLYDROP_MAX_PRICE=0.95
POLYDROP_WINDOW_SECONDS=60
POLYDROP_ALERT_THRESHOLD_PCT=5.0
POLYDROP_REDIS_URL=redis://localhost:6379
POLYDROP_REDIS_PREFIX=polydrop
POLYDROP_API_HOST=0.0.0.0
POLYDROP_API_PORT=8000
POLYDROP_LOG_LEVEL=INFO
```

## Source Structure

```
src/
├── config.py              # Configuration (all env vars required, no fallbacks)
├── api/
│   ├── server.py          # FastAPI: /api/tokens, /api/tokens/stream (SSE), /api/stats
│   └── broadcaster.py     # Single-poller SSE fan-out: one Redis poll → N client queues
├── clob/
│   └── client.py          # CLOB API client (game start times, with TTL cache)
├── redis/
│   └── publisher.py       # Publishes live token state to Redis hashes
├── db/
│   ├── models.py          # MarketRow, AlertRow dataclasses
│   └── database.py        # SQLite operations
├── websocket/
│   ├── messages.py        # Parse book, price_change messages
│   ├── client.py          # WebSocket connection with auto-reconnect
│   └── pool.py            # Pool of clients for >500 tokens (chunks of 500)
├── monitoring/
│   ├── rolling_window.py  # In-memory price window
│   ├── price_tracker.py   # Multi-token price tracking
│   └── subscription.py    # Token subscription management
└── gamma/
    └── client.py          # Gamma API for fetching and filtering markets

ui/                        # React 19 + TypeScript + Vite dashboard
├── src/
│   ├── components/        # TokenTable, Filters, PriceChart, NotificationBell, TokenDetail
│   ├── hooks/             # useTokenStream (SSE), useNotifications, usePriceHistory
│   └── types.ts           # Shared TypeScript types
└── dist/                  # Built output, served by FastAPI at /
```

## Architecture

```
Polymarket WS ──▶ Detection Engine ──▶ Redis ──▶ FastAPI (SSE) ──▶ React UI
(price feeds)     (velocity check)                /api/tokens/stream
                        │
                    SQLite
                (markets, alerts)
```

**main.py orchestrates three concurrent asyncio tasks:**
1. `WebSocketPool.run_with_reconnect()` — one pool of WS connections (chunked per 500 tokens), auto-reconnects
2. `_market_refresh_loop()` — periodic re-fetch from Gamma API, restarts WS pool with new token set
3. `_run_api_server()` — FastAPI/Uvicorn in-loop (signals delegated back to main)

**Alert detection pipeline** (in `_check_and_alert`):
velocity threshold → live spread check → live/near-live game check (Gamma + CLOB times) → in-memory cooldown → DB dedup → store alert

**SSE fan-out via Broadcaster** (`src/api/broadcaster.py`):
One background poll loop reads Redis on `sse_interval`; broadcasts delta events to all connected SSE clients via per-client `asyncio.Queue`. New clients receive a full snapshot on connect, then only deltas. Full queues silently drop events.

**API endpoints** (`src/api/server.py`):
- `GET /api/tokens` - Full token list from Redis
- `GET /api/tokens/stream` - SSE with delta-only updates
- `GET /api/tokens/{token_id}` - Single token details
- `GET /api/stats` - Daily page visit stats (last 30 days)
- `GET /` - Serves React build from `ui/dist/`

**Two Polymarket APIs:**
- **Gamma API** (`gamma-api.polymarket.com`) - Discovery & metadata (events, sports tags)
- **CLOB API** (`clob.polymarket.com`) - Trading data, real-time WebSocket, and game start times

**Data Hierarchy:**
```
Event (Gamma) → Markets[] → Tokens (clobTokenIds)
                    │
              conditionId ← Links Gamma ↔ CLOB APIs
```

## Key Concepts

**ID Types:**
- `event.id` / `market.id` - Gamma API identifiers (numeric strings)
- `conditionId` - Hex string linking Gamma ↔ CLOB APIs
- `clobTokenIds` - Large decimal strings for trading/WebSocket subscriptions

**Sports Filtering:** Use `tag_id` parameter on Gamma `/events` endpoint
- NFL=450, NBA=745, NHL=899, MLB=100381, NCAAB=100149
- `POLYDROP_SPORTS=all` enables dynamic discovery across all sports

**WebSocket:**
- Endpoint: `wss://ws-subscriptions-clob.polymarket.com/ws/market`
- Max 500 tokens per connection — `WebSocketPool` manages multiple connections automatically
- Heartbeat: Send `"PING"` every 10 seconds
- Subscribe: `{"assets_ids": ["<token_id>"], "type": "market"}`
- Message types: `book` (full order book), `price_change` (incremental updates)
- Messages may arrive as single objects or arrays

**Redis key schema:**
- `{prefix}:tokens` — Set of all active token IDs
- `{prefix}:token:{token_id}` — Hash of token state (price, velocity, market metadata)

## Key Files

- `main.py` - Application entry point and `Polydrop` orchestration class
- `.env.example` - All required environment variables with defaults
- `docs/plans/PLAN.md` - 5-phase development roadmap with task status
- `docs/polymarket-data-model.md` - Complete API reference and data structures
- `docs/examples/` - Sample JSON responses from all APIs

## Design Decisions

- In-memory rolling window for velocity detection (no price snapshots in DB)
- SQLite for market metadata and alert history only
- Redis for live token state (hashes per token, TTL-based expiry); app degrades gracefully without it
- SSE with delta-only updates (client receives only changed tokens, not full snapshots)
- Single Redis poll loop fans out to all SSE clients via Broadcaster (avoids N Redis reads per N clients)
- WebSocket pool restarts entirely on market refresh (more reliable than live sub/unsub)
- UI auto-builds on startup if `bun` is available
- Docker Compose for deployment: app + Redis + Caddy reverse proxy
- No test framework currently configured
