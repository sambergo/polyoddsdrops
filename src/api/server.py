"""FastAPI SSE server that reads token state from Redis and streams to browser."""

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import redis
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from ..config import Config

logger = logging.getLogger(__name__)

config = Config.from_env()
_redis: redis.Redis | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _redis
    try:
        _redis = redis.from_url(config.redis.url, decode_responses=True)
        _redis.ping()
        logger.info(f"API server connected to Redis: {config.redis.url}")
    except redis.RedisError as e:
        logger.error(f"Cannot connect to Redis: {e}")
        _redis = None
    yield
    if _redis:
        _redis.close()


app = FastAPI(title="Polydrop", lifespan=lifespan)


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
    """SSE endpoint — streams full token state every N seconds."""
    r = _get_redis()
    interval = config.api.sse_interval

    async def event_generator():
        while True:
            try:
                tokens = _get_all_tokens(r)
                yield {
                    "event": "tokens",
                    "data": json.dumps(tokens),
                }
            except redis.RedisError as e:
                logger.warning(f"SSE Redis read failed: {e}")
                yield {
                    "event": "error",
                    "data": json.dumps({"error": "redis_unavailable"}),
                }
                break
            await asyncio.sleep(interval)

    return EventSourceResponse(event_generator())


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
