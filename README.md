# Polyoddsdrops — [polyoddsdrops.com](https://polyoddsdrops.com)

Polymarket odds dropper for sports markets. Monitors sharp price movements on prediction markets and alerts on significant line moves — like a Pinnacle odds dropper, but for Polymarket.

## How it works

```
Polymarket WS ──> Detection Engine ──> Redis ──> FastAPI (SSE) ──> React UI
(price feeds)     (velocity check)                /api/tokens/stream
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

Requires:
- [Python 3.13+](https://www.python.org/) and [uv](https://docs.astral.sh/uv/)
- [Redis](https://redis.io/) running locally (or via Docker: `docker run -d -p 6379:6379 redis`)
- [bun](https://bun.sh) for the web UI (auto-built on startup if present)

```bash
# Install dependencies
uv sync

# Copy config and adjust as needed
cp .env.example .env

# Start monitoring
uv run python main.py
```

**Web UI:** [https://polyoddsdrops.com](https://polyoddsdrops.com) (or `http://localhost:3565` when running locally)

The dashboard is built automatically on startup if bun is installed.

## Configuration

Copy `.env.example` to `.env` — all variables are required. Key settings:

| Variable                       | Default                 | Description                                    |
| ------------------------------ | ----------------------- | ---------------------------------------------- |
| `POLYDROP_SPORTS`              | `all`                   | Sports to monitor (`nfl,nba,nhl,mlb` or `all`) |
| `POLYDROP_DB_PATH`             | `data/polydrop.db`      | SQLite database path                           |
| `POLYDROP_MIN_LIQUIDITY`       | `10000`                 | Minimum market liquidity (USD)                 |
| `POLYDROP_MAX_SPREAD`          | `0.10`                  | Maximum bid-ask spread                         |
| `POLYDROP_WINDOW_SECONDS`      | `600`                   | Rolling window for velocity calculation        |
| `POLYDROP_ALERT_THRESHOLD_PCT` | `7.0`                   | % price change to trigger an alert             |
| `POLYDROP_REDIS_URL`           | `redis://localhost:6379/0` | Redis connection URL                        |
| `POLYDROP_API_PORT`            | `3565`                  | API server port                                |
| `POLYDROP_LOG_LEVEL`           | `INFO`                  | Logging level                                  |

See `.env.example` for the full list of variables.

## Project structure

```
src/
├── config.py              # Configuration (env vars, defaults)
├── api/
│   ├── server.py          # FastAPI server + SSE endpoints
│   └── broadcaster.py     # SSE broadcaster (delta-only updates)
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
├── clob/client.py         # CLOB API (game start times)
├── push/client.py         # Push notifications
└── redis/publisher.py     # Redis publisher for web UI
ui/                        # React 19 + TypeScript + Vite dashboard
├── src/
│   ├── components/        # TokenTable, Filters, PriceChart, TokenDetail, NotificationBell
│   └── hooks/             # useTokenStream (SSE), useNotifications, usePriceHistory
scripts/                   # Discovery & exploration scripts
```

## Deployment

```bash
./deploy.sh <host>           # rsync + docker compose up (or set DEPLOY_HOST)
docker compose up -d --build # Local Docker (app + Redis + Caddy)
```

## Tech stack

- **Backend:** Python 3.13, FastAPI, websockets, httpx, SQLite
- **Frontend:** React 19, TypeScript, Vite, TanStack Table
- **Infra:** Redis (pub/sub for SSE), uv (package management), Docker Compose, Caddy
