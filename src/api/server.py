"""FastAPI SSE server that reads token state from Redis and streams to browser."""

import asyncio
import hashlib
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import redis
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from ..config import Config
from ..db.database import Database
from .broadcaster import Broadcaster

logger = logging.getLogger(__name__)

config = Config.from_env()
_redis: redis.Redis | None = None
_db: Database | None = None
_broadcaster: Broadcaster = Broadcaster()
_poll_task: asyncio.Task | None = None


async def _poll_loop() -> None:
    """Single background task: poll Redis once per interval, broadcast deltas."""
    interval = config.api.sse_interval
    last_seen: dict[str, str] = {}

    while True:
        await asyncio.sleep(interval)
        if _redis is None:
            continue
        try:
            tokens = await asyncio.to_thread(_get_all_tokens, _redis)
        except redis.RedisError as e:
            logger.warning("SSE poll Redis error: %s", e)
            _broadcaster.broadcast("error", json.dumps({"error": "redis_unavailable"}))
            continue

        if not last_seen:
            # First poll: seed state, don't broadcast (new connections fetch themselves)
            for t in tokens:
                last_seen[t.get("token_id", "")] = t.get("updated_at", "")
            continue

        current_ids: set[str] = set()
        changed: list[dict] = []
        for t in tokens:
            tid = t.get("token_id", "")
            current_ids.add(tid)
            updated = t.get("updated_at", "")
            if last_seen.get(tid) != updated:
                changed.append(t)
                last_seen[tid] = updated

        removed = [tid for tid in last_seen if tid not in current_ids]
        for tid in removed:
            del last_seen[tid]

        if changed or removed:
            payload: dict = {}
            if changed:
                payload["updated"] = changed
            if removed:
                payload["removed"] = removed
            _broadcaster.broadcast("delta", json.dumps(payload))


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _redis, _db, _poll_task
    try:
        _redis = redis.from_url(config.redis.url, decode_responses=True)
        _redis.ping()
        logger.info("API server connected to Redis: %s", config.redis.url)
    except redis.RedisError as e:
        logger.error("Cannot connect to Redis: %s", e)
        _redis = None
    _db = Database(config.db_path)
    _db.connect()

    _poll_task = asyncio.create_task(_poll_loop(), name="sse-poll")

    yield

    _poll_task.cancel()
    try:
        await _poll_task
    except asyncio.CancelledError:
        pass

    if _redis:
        _redis.close()
    if _db:
        _db.close()


app = FastAPI(title="Polydrop", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=500)


@app.middleware("http")
async def track_page_views(request: Request, call_next):
    response = await call_next(request)
    if request.method == "GET" and request.url.path in ("/", "/index.html"):
        ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else "")
        ip_hash = hashlib.sha256(ip.encode()).hexdigest()[:12]
        if _db:
            _db.log_visit(ip_hash, request.url.path)
    return response


def _get_redis() -> redis.Redis:
    if _redis is None:
        raise HTTPException(status_code=503, detail="Redis unavailable")
    return _redis


def _get_all_tokens(r: redis.Redis) -> list[dict]:
    """Read all token hashes from Redis."""
    prefix = config.redis.prefix
    token_ids = r.smembers(f"{prefix}:tokens")
    if not token_ids:
        return []

    pipe = r.pipeline()
    for tid in token_ids:
        pipe.hgetall(f"{prefix}:token:{tid}")
    results = pipe.execute()

    tokens = []
    for data in results:
        if data:
            tokens.append(data)
    return tokens


def _get_single_token(r: redis.Redis, token_id: str) -> dict | None:
    """Read a single token hash from Redis."""
    prefix = config.redis.prefix
    data = r.hgetall(f"{prefix}:token:{token_id}")
    return data if data else None


@app.get("/api/tokens")
async def get_tokens():
    """Get all tracked tokens (initial load)."""
    r = _get_redis()
    tokens = _get_all_tokens(r)
    return JSONResponse(content=tokens)


@app.get("/api/tokens/stream")
async def token_stream():
    """SSE endpoint — streams only changed tokens (delta updates)."""
    if _redis is None:
        async def _unavailable():
            yield {"event": "error", "data": json.dumps({"error": "redis_unavailable"})}
        return EventSourceResponse(_unavailable())

    q = _broadcaster.subscribe()

    async def event_generator():
        try:
            try:
                tokens = await asyncio.to_thread(_get_all_tokens, _redis)
            except redis.RedisError as e:
                logger.warning("SSE initial fetch failed: %s", e)
                yield {"event": "error", "data": json.dumps({"error": "redis_unavailable"})}
                return
            yield {"event": "tokens", "data": json.dumps(tokens)}
            while True:
                message = await q.get()
                yield message
        finally:
            _broadcaster.unsubscribe(q)

    return EventSourceResponse(event_generator())


@app.get("/api/stats")
async def get_stats():
    """Get daily page visit stats for the last 30 days."""
    if _db is None:
        raise HTTPException(status_code=503, detail="DB unavailable")
    return JSONResponse(content=_db.get_daily_stats(30))


@app.get("/api/tokens/{token_id}")
async def get_token(token_id: str):
    """Get a single token's full state."""
    r = _get_redis()
    data = _get_single_token(r, token_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Token not found")
    return JSONResponse(content=data)


# Serve React static build if it exists
ui_dist = Path(__file__).resolve().parent.parent.parent / "ui" / "dist"
if ui_dist.is_dir():
    app.mount("/", StaticFiles(directory=str(ui_dist), html=True), name="ui")


def main():
    """Run the API server."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger.info(f"Starting API server on {config.api.host}:{config.api.port}")
    uvicorn.run(
        "src.api.server:app",
        host=config.api.host,
        port=config.api.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
