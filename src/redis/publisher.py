"""Redis publisher for broadcasting token state to the web UI."""

import logging
import time

import redis

from ..config import RedisConfig
from ..db.models import MarketRow
from ..monitoring.price_tracker import VelocityResult

logger = logging.getLogger(__name__)


class RedisPublisher:
    """Publishes token state to Redis for the SSE API server to read.

    Writes a hash per token with market metadata + live pricing.
    Maintains a set of active token IDs for enumeration.
    Gracefully degrades if Redis is unavailable.
    """

    def __init__(self, config: RedisConfig) -> None:
        self._config = config
        self._prefix = config.prefix
        self._ttl = config.token_ttl
        self._client: redis.Redis | None = None
        self._available = False

    def connect(self) -> None:
        """Connect to Redis. Logs warning if unavailable."""
        try:
            self._client = redis.from_url(
                self._config.url,
                decode_responses=True,
            )
            self._client.ping()
            self._available = True
            logger.info(f"Redis connected: {self._config.url}")
        except redis.RedisError as e:
            logger.warning(f"Redis unavailable, UI data will not be published: {e}")
            self._available = False

    def _key(self, suffix: str) -> str:
        return f"{self._prefix}:{suffix}"

    def publish_token_state(
        self,
        token_id: str,
        market: MarketRow | None,
        mid_price: float | None = None,
        best_bid: float | None = None,
        best_ask: float | None = None,
        velocity: VelocityResult | None = None,
        live_spread: float | None = None,
    ) -> None:
        """Write current token state to Redis hash.

        Args:
            token_id: Token identifier.
            market: Market metadata from DB (may be None for unknown tokens).
            mid_price: Current mid price.
            best_bid: Current best bid.
            best_ask: Current best ask.
            velocity: Current velocity data from price tracker.
            live_spread: Real-time spread from order book (best_ask - best_bid).
        """
        if not self._available or not self._client:
            return

        try:
            token_key = self._key(f"token:{token_id}")
            existing_first_seen = self._client.hget(token_key, "first_seen")

            data: dict[str, str] = {
                "token_id": token_id,
                "first_seen": existing_first_seen or str(time.time()),
                "updated_at": str(time.time()),
            }

            if mid_price is not None:
                data["mid_price"] = str(mid_price)
            if best_bid is not None:
                data["best_bid"] = str(best_bid)
            if best_ask is not None:
                data["best_ask"] = str(best_ask)

            if market:
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
                        "spread": str(live_spread)
                        if live_spread is not None
                        else (str(market.spread) if market.spread is not None else ""),
                        "volume_24h": str(market.volume_24h)
                        if market.volume_24h is not None
                        else "",
                        "game_start_time": market.game_start_time or "",
                        "is_subscribed": "1" if market.is_subscribed else "0",
                        "is_active": "1" if market.is_active else "0",
                        "priority": str(market.priority),
                    }
                )

            if velocity:
                v = velocity.velocity
                data.update(
                    {
                        "oldest_price": str(v.oldest_price),
                        "newest_price": str(v.newest_price),
                        "price_change": str(v.price_change),
                        "pct_change": str(v.pct_change),
                        "elapsed_seconds": str(v.elapsed_seconds),
                        "observation_count": str(velocity.observation_count),
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

            pipe = self._client.pipeline()
            pipe.hset(token_key, mapping=data)
            pipe.expire(token_key, self._ttl)
            pipe.sadd(self._key("tokens"), token_id)
            pipe.execute()

        except redis.RedisError as e:
            logger.warning(f"Redis publish failed: {e}")
            self._available = False

    def remove_token(self, token_id: str) -> None:
        """Remove a token from Redis."""
        if not self._available or not self._client:
            return

        try:
            pipe = self._client.pipeline()
            pipe.delete(self._key(f"token:{token_id}"))
            pipe.srem(self._key("tokens"), token_id)
            pipe.execute()
        except redis.RedisError as e:
            logger.warning(f"Redis remove failed: {e}")

    def close(self) -> None:
        """Close Redis connection."""
        if self._client:
            self._client.close()
            self._client = None
            self._available = False
