# Polydrop

Polymarket odds dropper for sports markets. Monitors real-time price movements on Polymarket prediction markets and alerts on sharp line moves — similar to Pinnacle odds dropper services but for crypto prediction markets.

## How it works

```
Polymarket WS ──> Detection Engine ──> Redis ──> Web UI
(price feeds)     (velocity check)          (SSE)
                        │
                    SQLite
                (markets, alerts)
```

1. Fetches active sports markets from Polymarket's Gamma API
2. Filters by liquidity, spread, volume, and price range
3. Subscribes to real-time WebSocket price feeds
4. Tracks price velocity using an in-memory rolling window
5. Fires alerts when price movement exceeds configured thresholds
6. Publishes state to Redis for the web dashboard (SSE)

## Quickstart

Requires Python 3.13+ and [uv](https://docs.astral.sh/uv/).

```bash
# Install dependencies
uv sync

# Start monitoring
uv run python main.py
```

The web UI is served at `http://localhost:8000` (built automatically on startup if [bun](https://bun.sh) is installed).

## Configuration

All settings use sensible defaults. Override via environment variables or a `.env` file:

| Variable | Default | Description |
|---|---|---|
| `POLYDROP_DB_PATH` | `data/polydrop.db` | SQLite database path |
| `POLYDROP_SPORTS` | `nfl,nba,nhl` | Sports to monitor (comma-separated) |
| `POLYDROP_MIN_LIQUIDITY` | `10000` | Minimum market liquidity (USD) |
| `POLYDROP_MAX_SPREAD` | `0.10` | Maximum bid-ask spread |
| `POLYDROP_WINDOW_SECONDS` | `60` | Rolling window for velocity calculation |
| `POLYDROP_LOG_LEVEL` | `INFO` | Logging level |

## Project structure

```
src/
├── config.py              # Configuration (env vars, defaults)
├── api/server.py          # FastAPI server + SSE
├── db/
│   ├── models.py          # MarketRow, AlertRow dataclasses
│   └── database.py        # SQLite operations
├── websocket/
│   ├── messages.py        # Parse book/price_change messages
│   └── client.py          # WebSocket connection pool
├── monitoring/
│   ├── rolling_window.py  # In-memory price window
│   ├── price_tracker.py   # Multi-token price tracking
│   └── subscription.py    # Token subscription management
├── gamma/client.py        # Gamma API (market discovery)
├── clob/                  # CLOB API (game start times)
└── redis/                 # Redis publisher for web UI
ui/                        # React + Vite dashboard
scripts/                   # Discovery & exploration scripts
```

## Tech stack

- **Backend:** Python 3.13, FastAPI, websockets, httpx, SQLite
- **Frontend:** React 19, Vite, TanStack Table
- **Infra:** Redis (pub/sub for SSE), uv (package management)
