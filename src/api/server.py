"""FastAPI SSE server that reads token state from Redis and streams to browser."""

import asyncio
import hashlib
import json
import logging
import time
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

_RATE_LIMIT_WINDOW_SECONDS = 600
_GLOBAL_RATE_LIMIT = 600
_PAGE_RATE_LIMIT = 30
_TOKENS_RATE_LIMIT = 60
_STATS_RATE_LIMIT = 30
_TOKEN_DETAIL_RATE_LIMIT = 120
_SSE_ATTEMPT_RATE_LIMIT = 10
_STATIC_RATE_LIMIT = 240
_OTHER_RATE_LIMIT = 300
_RATE_LIMIT_LOG_INTERVAL_SECONDS = 60
_SSE_MAX_CONNECTIONS_PER_IP = 2

_rate_limits: dict[tuple[str, str], tuple[float, int]] = {}
_rate_limit_logs: dict[tuple[str, str], float] = {}
_rate_limit_lock = asyncio.Lock()
_rate_limit_last_cleanup = 0.0

_sse_connections: dict[str, int] = {}
_sse_lock = asyncio.Lock()


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


def _client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _path_rate_limit(path: str) -> tuple[str, int]:
    if path in ("/", "/index.html"):
        return ("page", _PAGE_RATE_LIMIT)
    if path == "/api/tokens":
        return ("api_tokens", _TOKENS_RATE_LIMIT)
    if path == "/api/tokens/stream":
        return ("api_tokens_stream", _SSE_ATTEMPT_RATE_LIMIT)
    if path == "/api/stats":
        return ("api_stats", _STATS_RATE_LIMIT)
    if path.startswith("/api/tokens/"):
        return ("api_token_detail", _TOKEN_DETAIL_RATE_LIMIT)
    if path.startswith("/assets/"):
        return ("static", _STATIC_RATE_LIMIT)
    return ("other", _OTHER_RATE_LIMIT)


def _cleanup_rate_limits(now: float) -> None:
    global _rate_limit_last_cleanup
    if now - _rate_limit_last_cleanup < _RATE_LIMIT_WINDOW_SECONDS:
        return

    expired = [
        key
        for key, (window_start, _count) in _rate_limits.items()
        if now - window_start >= _RATE_LIMIT_WINDOW_SECONDS
    ]
    for key in expired:
        del _rate_limits[key]

    old_logs = [
        key
        for key, last_logged in _rate_limit_logs.items()
        if now - last_logged >= _RATE_LIMIT_WINDOW_SECONDS
    ]
    for key in old_logs:
        del _rate_limit_logs[key]

    _rate_limit_last_cleanup = now


async def _consume_rate_limit(ip: str, path: str) -> tuple[str, int] | None:
    now = time.monotonic()
    path_scope, path_limit = _path_rate_limit(path)
    checks = [
        ("global", _GLOBAL_RATE_LIMIT),
        (path_scope, path_limit),
    ]

    async with _rate_limit_lock:
        _cleanup_rate_limits(now)

        current: dict[tuple[str, str], tuple[float, int]] = {}
        retry_after = 0
        blocked_scope = ""

        for scope, limit in checks:
            key = (scope, ip)
            window_start, count = _rate_limits.get(key, (now, 0))
            if now - window_start >= _RATE_LIMIT_WINDOW_SECONDS:
                window_start = now
                count = 0
            if count >= limit:
                retry_after = max(
                    retry_after,
                    int(_RATE_LIMIT_WINDOW_SECONDS - (now - window_start)) + 1,
                )
                blocked_scope = scope
            current[key] = (window_start, count)

        if retry_after:
            log_key = (blocked_scope, ip)
            last_logged = _rate_limit_logs.get(log_key, 0.0)
            if now - last_logged >= _RATE_LIMIT_LOG_INTERVAL_SECONDS:
                logger.warning(
                    "Rate limit exceeded: ip=%s path=%s scope=%s retry_after=%ss",
                    ip,
                    path,
                    blocked_scope,
                    retry_after,
                )
                _rate_limit_logs[log_key] = now
            return blocked_scope, retry_after

        for key, (window_start, count) in current.items():
            _rate_limits[key] = (window_start, count + 1)

    return None


async def _try_open_sse(ip: str) -> bool:
    async with _sse_lock:
        active = _sse_connections.get(ip, 0)
        if active >= _SSE_MAX_CONNECTIONS_PER_IP:
            logger.warning(
                "SSE connection limit exceeded: ip=%s active=%s limit=%s",
                ip,
                active,
                _SSE_MAX_CONNECTIONS_PER_IP,
            )
            return False
        _sse_connections[ip] = active + 1
        return True


async def _close_sse(ip: str) -> None:
    async with _sse_lock:
        active = _sse_connections.get(ip, 0)
        if active <= 1:
            _sse_connections.pop(ip, None)
        else:
            _sse_connections[ip] = active - 1


@app.middleware("http")
async def rate_limit_and_track_page_views(request: Request, call_next):
    ip = _client_ip(request)
    limit_result = await _consume_rate_limit(ip, request.url.path)
    if limit_result:
        _scope, retry_after = limit_result
        return JSONResponse(
            status_code=429,
            content={"detail": "Too many requests"},
            headers={"Retry-After": str(retry_after)},
        )

    response = await call_next(request)
    if request.method == "GET" and request.url.path in ("/", "/index.html"):
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
async def token_stream(request: Request):
    """SSE endpoint — streams only changed tokens (delta updates)."""
    ip = _client_ip(request)
    if not await _try_open_sse(ip):
        return JSONResponse(
            status_code=429,
            content={"detail": "Too many open streams"},
            headers={"Retry-After": "30"},
        )

    if _redis is None:

        async def _unavailable():
            try:
                yield {
                    "event": "error",
                    "data": json.dumps({"error": "redis_unavailable"}),
                }
            finally:
                await _close_sse(ip)

        return EventSourceResponse(_unavailable())

    q = _broadcaster.subscribe()

    async def event_generator():
        try:
            try:
                tokens = await asyncio.to_thread(_get_all_tokens, _redis)
            except redis.RedisError as e:
                logger.warning("SSE initial fetch failed: %s", e)
                yield {
                    "event": "error",
                    "data": json.dumps({"error": "redis_unavailable"}),
                }
                return
            yield {"event": "tokens", "data": json.dumps(tokens)}
            while True:
                message = await q.get()
                yield message
        finally:
            _broadcaster.unsubscribe(q)
            await _close_sse(ip)

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
