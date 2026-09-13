"""Batched asynchronous Redis publishing for the dashboard."""

import json
import logging
import time
from dataclasses import dataclass

import redis.asyncio as redis

from ..config import RedisConfig
from ..db.models import MarketRow
from ..monitoring.price_tracker import VelocityResult

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class TokenUpdate:
    token_id: str
    market: MarketRow | None
    mid_price: float
    best_bid: float
    best_ask: float
    velocity: VelocityResult | None
    live_spread: float


class RedisPublisher:
    """Store token snapshots and publish delta batches without blocking asyncio."""

    def __init__(self, config: RedisConfig) -> None:
        self._config = config
        self._prefix = config.prefix
        self._client: redis.Redis | None = None
        self._available = False
        self._first_seen: dict[str, str] = {}
        self._published_tokens: set[str] = set()
        self.last_batch_size = 0
        self.last_batch_duration = 0.0

    @property
    def channel(self) -> str:
        return f"{self._prefix}:updates"

    async def connect(self) -> None:
        try:
            self._client = redis.from_url(self._config.url, decode_responses=True)
            await self._client.ping()
            self._available = True
            logger.info("Redis connected: %s", self._config.url)
        except redis.RedisError as exc:
            logger.warning("Redis unavailable, UI data will not be published: %s", exc)
            self._available = False

    def _key(self, suffix: str) -> str:
        return f"{self._prefix}:{suffix}"

    def _serialize(self, update: TokenUpdate, now: float) -> dict[str, str]:
        token_id = update.token_id
        data = {
            "token_id": token_id,
            "updated_at": str(now),
            "mid_price": str(update.mid_price),
            "best_bid": str(update.best_bid),
            "best_ask": str(update.best_ask),
        }
        market = update.market
        if token_id not in self._published_tokens:
            data["first_seen"] = self._first_seen.setdefault(token_id, str(now))
        if market and token_id not in self._published_tokens:
            data.update(
                {
                    "condition_id": market.condition_id or "",
                    "question": market.question or "",
                    "outcome": market.outcome or "",
                    "event_title": market.event_title or "",
                    "event_slug": market.event_slug or "",
                    "sport": market.sport or "",
                    "league_label": market.league_label or "",
                    "sport_label": market.sport_label or "",
                    "market_type": market.market_type or "",
                    "line": str(market.line) if market.line is not None else "",
                    "liquidity": str(market.liquidity)
                    if market.liquidity is not None
                    else "",
                    "spread": str(update.live_spread),
                    "volume_24h": str(market.volume_24h)
                    if market.volume_24h is not None
                    else "",
                    "game_start_time": market.game_start_time or "",
                    "is_subscribed": "1" if market.is_subscribed else "0",
                    "is_active": "1" if market.is_active else "0",
                    "priority": str(market.priority),
                }
            )
        self._published_tokens.add(token_id)

        if update.velocity:
            velocity = update.velocity.velocity
            data.update(
                {
                    "oldest_price": str(velocity.oldest_price),
                    "newest_price": str(velocity.newest_price),
                    "price_change": str(velocity.price_change),
                    "pct_change": str(velocity.pct_change),
                    "elapsed_seconds": str(velocity.elapsed_seconds),
                    "observation_count": str(update.velocity.observation_count),
                }
            )
        else:
            data.update(
                {
                    "oldest_price": "",
                    "newest_price": "",
                    "price_change": "0",
                    "pct_change": "0",
                    "elapsed_seconds": "0",
                    "observation_count": "0",
                }
            )
        return data

    async def publish_token_states(self, updates: list[TokenUpdate]) -> None:
        if not updates or not self._available or not self._client:
            return

        started = time.monotonic()
        now = time.time()
        serialized = [self._serialize(update, now) for update in updates]
        try:
            pipe = self._client.pipeline(transaction=False)
            for data in serialized:
                pipe.hset(self._key(f"token:{data['token_id']}"), mapping=data)
                if "first_seen" in data:
                    # Remove TTLs left by versions that refreshed expiry per tick.
                    pipe.persist(self._key(f"token:{data['token_id']}"))
            pipe.publish(self.channel, json.dumps({"updated": serialized}))
            await pipe.execute()
            self.last_batch_size = len(serialized)
            self.last_batch_duration = time.monotonic() - started
        except redis.RedisError as exc:
            logger.warning("Redis batch publish failed: %s", exc)
            self._available = False

    async def sync_tokens(self, token_ids: list[str]) -> None:
        """Update enumeration membership and explicitly remove stale snapshots."""
        if not self._available or not self._client:
            return
        desired = set(token_ids)
        # The next update refreshes static metadata after market discovery.
        self._published_tokens.difference_update(desired)
        try:
            current = await self._client.smembers(self._key("tokens"))
            unknown_first_seen = desired - self._first_seen.keys()
            if unknown_first_seen:
                lookup = self._client.pipeline(transaction=False)
                ordered_unknown = list(unknown_first_seen)
                for token_id in ordered_unknown:
                    lookup.hget(self._key(f"token:{token_id}"), "first_seen")
                existing_values = await lookup.execute()
                for token_id, first_seen in zip(
                    ordered_unknown, existing_values, strict=True
                ):
                    if first_seen:
                        self._first_seen[token_id] = first_seen
            removed = current - desired
            pipe = self._client.pipeline(transaction=False)
            if removed:
                pipe.srem(self._key("tokens"), *removed)
                for token_id in removed:
                    pipe.delete(self._key(f"token:{token_id}"))
                    self._first_seen.pop(token_id, None)
                    self._published_tokens.discard(token_id)
            if desired:
                pipe.sadd(self._key("tokens"), *desired)
            payload = {"removed": list(removed)} if removed else {}
            if payload:
                pipe.publish(self.channel, json.dumps(payload))
            await pipe.execute()
        except redis.RedisError as exc:
            logger.warning("Redis token sync failed: %s", exc)
            self._available = False

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
        self._available = False
