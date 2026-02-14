# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Polydrop is a Polymarket odds dropper for sports markets - monitors sharp price movements in prediction markets. Similar to Pinnacle odds dropper services but for Polymarket.

## Commands

```bash
# Run the application
uv run python main.py              # Start monitoring (connects to WebSocket, tracks prices)

# Discovery scripts (Phase 1)
uv run scripts/fetch_markets.py       # Fetch markets from CLOB/Gamma APIs
uv run scripts/find_sports_markets.py # Discover sports markets by tag
uv run scripts/explore_websocket.py   # Explore WebSocket real-time feeds

# Database inspection
sqlite3 data/polydrop.db ".tables"              # List tables
sqlite3 data/polydrop.db "SELECT COUNT(*) FROM markets"  # Count markets

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
├── __init__.py
├── config.py              # Configuration (env vars, defaults)
├── db/
│   ├── __init__.py
│   ├── models.py          # MarketRow, AlertRow dataclasses
│   └── database.py        # SQLite operations
├── websocket/
│   ├── __init__.py
│   ├── messages.py        # Parse book, price_change messages
│   └── client.py          # WebSocket connection manager
├── monitoring/
│   ├── __init__.py
│   ├── rolling_window.py  # In-memory price window
│   ├── price_tracker.py   # Multi-token price tracking
│   └── subscription.py    # Token subscription management
└── gamma/
    ├── __init__.py
    └── client.py          # Gamma API for fetching markets
```

## Architecture

```
Polymarket WS ──▶ Detection Engine ──▶ Redis ──▶ Web UI
(price feeds)     (velocity check)          (SSE)
                        │
                    SQLite
                (markets, alerts)
```

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
- Manual token configuration initially (dynamic subscriptions in Phase 5)
- Components decoupled for future multi-user expansion

