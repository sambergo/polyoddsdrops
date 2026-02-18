# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Polydrop is a Polymarket odds dropper for sports markets - monitors sharp price movements in prediction markets. Similar to Pinnacle odds dropper services but for Polymarket.

## Commands

```bash
# Run the application
uv run python main.py              # Start monitoring (WS + API server + UI)

# Web UI (React/TypeScript/Vite, requires bun)
cd ui && bun install                  # Install frontend deps
cd ui && bun run build                # Build to ui/dist/ (served by FastAPI)
cd ui && bun run dev                  # Dev server with hot reload

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

Create a `.env` file (optional - defaults are sensible):

```bash
POLYDROP_DB_PATH=data/polydrop.db        # SQLite database path
POLYDROP_SPORTS=nfl,nba,nhl              # Sports to monitor (comma-separated)
POLYDROP_MIN_LIQUIDITY=10000             # Min liquidity filter (USD)
POLYDROP_MAX_SPREAD=0.10                 # Max bid-ask spread
POLYDROP_WINDOW_SECONDS=60               # Rolling window for velocity
POLYDROP_LOG_LEVEL=INFO                  # Logging level
```

## Source Structure

```
src/
├── config.py              # Configuration (env vars, defaults)
├── api/
│   └── server.py          # FastAPI: /api/tokens, /api/tokens/stream (SSE), static UI
├── redis/
│   └── publisher.py       # Publishes live token state to Redis hashes
├── db/
│   ├── models.py          # MarketRow, AlertRow dataclasses
│   └── database.py        # SQLite operations
├── websocket/
│   ├── messages.py        # Parse book, price_change messages
│   └── client.py          # WebSocket connection manager
├── monitoring/
│   ├── rolling_window.py  # In-memory price window
│   ├── price_tracker.py   # Multi-token price tracking
│   └── subscription.py    # Token subscription management
└── gamma/
    └── client.py          # Gamma API for fetching markets

ui/                        # React 19 + TypeScript + Vite dashboard
├── src/
│   ├── components/        # TokenTable, Filters, PriceChart, NotificationBell
│   └── hooks/             # useTokenStream (SSE), useNotifications, usePriceHistory
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
1. WebSocket pool with auto-reconnect (subscribes to token price feeds)
2. Market refresh loop (periodic re-fetch from Gamma API)
3. FastAPI/Uvicorn server (serves API + static UI)

**API endpoints** (`src/api/server.py`):
- `GET /api/tokens` - Full token list from Redis
- `GET /api/tokens/stream` - SSE with delta-only updates
- `GET /api/tokens/{token_id}` - Single token details
- `GET /` - Serves React build from `ui/dist/`

**Two Polymarket APIs:**
- **Gamma API** (`gamma-api.polymarket.com`) - Discovery & metadata (events, sports tags)
- **CLOB API** (`clob.polymarket.com`) - Trading data & real-time WebSocket

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
- Query: `GET /events?active=true&closed=false&tag_id=450`

**WebSocket:**
- Endpoint: `wss://ws-subscriptions-clob.polymarket.com/ws/market`
- Max 500 tokens per connection (use multiple connections if needed)
- Heartbeat: Send `"PING"` every 10 seconds
- Subscribe: `{"assets_ids": ["<token_id>"], "type": "market"}`
- Message types: `book` (full order book), `price_change` (incremental updates)
- Messages may arrive as single objects or arrays

## Key Files

- `main.py` - Application entry point
- `docs/plans/PLAN.md` - 5-phase development roadmap with task status
- `docs/polymarket-data-model.md` - Complete API reference and data structures
- `docs/examples/` - Sample JSON responses from all APIs
- `scripts/` - Data discovery scripts (fetch, analyze, explore)

## Design Decisions

- In-memory rolling window for velocity detection (no price snapshots in DB)
- SQLite for market metadata and alert history only
- Redis for live token state (hashes per token, TTL-based expiry); app degrades gracefully without it
- SSE with delta-only updates (client receives only changed tokens, not full snapshots)
- UI auto-builds on startup if `bun` is available
- Docker Compose for deployment: app + Redis + Caddy reverse proxy
- No test framework currently configured

