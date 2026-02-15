"""Multi-token price tracking."""

import logging
from dataclasses import dataclass

from ..config import MonitoringConfig
from .rolling_window import RollingWindow, VelocityData

logger = logging.getLogger(__name__)


@dataclass
class VelocityResult:
    """Result of velocity check for a token."""

    token_id: str
    velocity: VelocityData
    observation_count: int


class PriceTracker:
    """Tracks prices for multiple tokens using rolling windows.

    Maintains one RollingWindow per token and provides methods to
    update prices and check velocity across all tokens.
    """

    def __init__(self, config: MonitoringConfig) -> None:
        """Initialize the price tracker.

        Args:
            config: Monitoring configuration.
        """
        self.config = config
        self._windows: dict[str, RollingWindow] = {}
        self._update_count = 0

    def update_price(self, token_id: str, price: float) -> None:
        """Update the price for a token.

        Creates a new rolling window if this is the first observation
        for the token.

        Args:
            token_id: The token identifier.
            price: The current price.
        """
        if token_id not in self._windows:
            self._windows[token_id] = RollingWindow(
                window_seconds=self.config.window_seconds,
                max_data_points=self.config.max_data_points,
            )

        self._windows[token_id].add(price)
        self._update_count += 1

    def get_velocity(self, token_id: str) -> VelocityResult | None:
        """Get velocity data for a specific token.

        Args:
            token_id: The token identifier.

        Returns:
            VelocityResult if sufficient data, None otherwise.
        """
        window = self._windows.get(token_id)
        if window is None:
            return None

        velocity = window.get_velocity()
        if velocity is None:
            return None

        return VelocityResult(
            token_id=token_id,
            velocity=velocity,
            observation_count=window.observation_count,
        )

    def get_all_velocities(self) -> list[VelocityResult]:
        """Get velocity data for all tracked tokens.

        Only returns tokens with sufficient data for velocity calculation.

        Returns:
            List of VelocityResult for all tokens with velocity data.
        """
        results = []
        for token_id in self._windows:
            result = self.get_velocity(token_id)
            if result:
                results.append(result)
        return results

    def get_latest_price(self, token_id: str) -> float | None:
        """Get the latest price for a token.

        Args:
            token_id: The token identifier.

        Returns:
            The latest price or None if not tracked.
        """
        window = self._windows.get(token_id)
        if window is None:
            return None
        return window.latest_price

    def remove_token(self, token_id: str) -> bool:
        """Remove a token from tracking.

        Args:
            token_id: The token identifier.

        Returns:
            True if the token was removed, False if not found.
        """
        if token_id in self._windows:
            del self._windows[token_id]
            return True
        return False

    def clear(self) -> None:
        """Clear all tracked tokens."""
        self._windows.clear()
        self._update_count = 0

    @property
    def tracked_token_count(self) -> int:
        """Get the number of tokens being tracked."""
        return len(self._windows)

    @property
    def total_update_count(self) -> int:
        """Get total number of price updates processed."""
        return self._update_count

    def get_stats(self) -> dict:
        """Get summary statistics for the tracker.

        Returns:
            Dict with tracking statistics.
        """
        total_observations = sum(w.observation_count for w in self._windows.values())

        return {
            "tracked_tokens": self.tracked_token_count,
            "total_updates": self._update_count,
            "total_observations": total_observations,
            "window_seconds": self.config.window_seconds,
        }
