"""Rolling window for price observations."""

import time
from collections import deque
from dataclasses import dataclass


@dataclass
class PriceObservation:
    """A single price observation."""

    price: float
    timestamp: float  # Unix timestamp


@dataclass
class VelocityData:
    """Result of velocity calculation."""

    oldest_price: float
    newest_price: float
    price_change: float
    pct_change: float
    elapsed_seconds: float


class RollingWindow:
    """In-memory rolling window for price observations.

    Maintains a deque of recent price observations within a configurable
    time window. Used for velocity-based price movement detection.
    """

    def __init__(
        self,
        window_seconds: int = 60,
        max_data_points: int = 100,
    ) -> None:
        """Initialize the rolling window.

        Args:
            window_seconds: Duration of the window in seconds.
            max_data_points: Maximum number of observations to keep.
        """
        self.window_seconds = window_seconds
        self.max_data_points = max_data_points
        self._observations: deque[PriceObservation] = deque(maxlen=max_data_points)

    def add(self, price: float, timestamp: float | None = None) -> None:
        """Add a price observation.

        Args:
            price: The observed price.
            timestamp: Unix timestamp. Uses current time if None.
        """
        if timestamp is None:
            timestamp = time.time()

        self._observations.append(PriceObservation(price=price, timestamp=timestamp))
        self.prune()

    def prune(self) -> int:
        """Remove stale entries outside the time window.

        Returns:
            Number of entries removed.
        """
        cutoff = time.time() - self.window_seconds
        removed = 0

        while self._observations and self._observations[0].timestamp < cutoff:
            self._observations.popleft()
            removed += 1

        return removed

    def get_velocity(self) -> VelocityData | None:
        """Calculate price velocity over the window.

        Returns:
            VelocityData with price change metrics, or None if insufficient data.
        """
        self.prune()

        if len(self._observations) < 2:
            return None

        oldest = self._observations[0]
        newest = self._observations[-1]

        price_change = newest.price - oldest.price
        elapsed = newest.timestamp - oldest.timestamp

        if elapsed <= 0 or oldest.price == 0:
            return None

        pct_change = (price_change / oldest.price) * 100

        return VelocityData(
            oldest_price=oldest.price,
            newest_price=newest.price,
            price_change=price_change,
            pct_change=pct_change,
            elapsed_seconds=elapsed,
        )

    @property
    def latest_price(self) -> float | None:
        """Get the most recent price, or None if no observations."""
        if not self._observations:
            return None
        return self._observations[-1].price

    @property
    def observation_count(self) -> int:
        """Get number of observations in the window."""
        return len(self._observations)

    def clear(self) -> None:
        """Clear all observations."""
        self._observations.clear()
