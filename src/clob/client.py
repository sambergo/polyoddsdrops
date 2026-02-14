"""CLOB API client for fetching real-time market data."""

import logging
import time
from dataclasses import dataclass

import httpx

CLOB_HOST = "https://clob.polymarket.com"

logger = logging.getLogger(__name__)


@dataclass
class CachedStartTime:
    """Cached game start time from CLOB API."""

    game_start_time: str | None
    is_live: bool  # True if match has already started
    fetched_at: float


class ClobClient:
    """Client for Polymarket CLOB API.

    Used to fetch real-time market data, particularly the actual
    game_start_time which may differ from the scheduled time in Gamma API.
    """

    def __init__(
        self,
        cache_ttl_seconds: int = 300,
        live_cache_ttl_seconds: int = 3600,
    ) -> None:
        """Initialize the CLOB API client.

        Args:
            cache_ttl_seconds: How long to cache start times for upcoming matches.
            live_cache_ttl_seconds: How long to cache "is live" status (matches
                don't un-start, so this can be long).
        """
        self.cache_ttl = cache_ttl_seconds
        self.live_cache_ttl = live_cache_ttl_seconds
        self._start_time_cache: dict[str, CachedStartTime] = {}

    def _is_start_time_in_past(self, start_time: str | None) -> bool:
        """Check if a start time is in the past (match has started)."""
        if not start_time:
            return False
        try:
            from datetime import datetime, timezone

            dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            return dt < datetime.now(timezone.utc)
        except (ValueError, TypeError):
            return False

    def get_game_start_time(self, condition_id: str) -> str | None:
        """Get the real-time game start time for a market.

        This fetches from CLOB API which has the actual start time,
        not the scheduled time. Results are cached to avoid excessive API calls.

        Caching strategy:
        - Live matches (already started): cached for 1 hour (matches don't un-start)
        - Upcoming matches: cached for 5 minutes (to catch early starts)

        Args:
            condition_id: The market's condition ID (hex string).

        Returns:
            ISO-8601 datetime string or None if unavailable.
        """
        now = time.time()

        # Check cache with appropriate TTL
        cached = self._start_time_cache.get(condition_id)
        if cached:
            ttl = self.live_cache_ttl if cached.is_live else self.cache_ttl
            if (now - cached.fetched_at) < ttl:
                return cached.game_start_time

        # Fetch from API
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(f"{CLOB_HOST}/markets/{condition_id}")
                if resp.status_code == 200:
                    data = resp.json()
                    start_time = data.get("game_start_time")
                    is_live = self._is_start_time_in_past(start_time)

                    # Cache the result
                    self._start_time_cache[condition_id] = CachedStartTime(
                        game_start_time=start_time,
                        is_live=is_live,
                        fetched_at=now,
                    )
                    logger.debug(
                        f"CLOB game_start_time for {condition_id[:20]}...: "
                        f"{start_time} (live={is_live})"
                    )
                    return start_time
                else:
                    logger.warning(
                        f"CLOB API returned {resp.status_code} for {condition_id[:20]}..."
                    )
        except httpx.RequestError as e:
            logger.warning(f"CLOB API request failed for {condition_id[:20]}...: {e}")

        # On failure, return cached value if available (even if stale)
        if cached:
            return cached.game_start_time

        return None

    def clear_cache(self) -> None:
        """Clear the start time cache."""
        self._start_time_cache.clear()

    def get_cache_stats(self) -> dict:
        """Get cache statistics."""
        return {
            "cached_markets": len(self._start_time_cache),
        }
