"""Token subscription management."""

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class SubscriptionManager:
    """Manages token subscriptions across WebSocket connections.

    Handles the 500 token per connection limit by tracking which
    tokens are subscribed and supporting prioritization for when
    we have more tokens than we can subscribe to.
    """

    max_tokens: int = 500
    _subscribed: set[str] = field(default_factory=set)
    _available: set[str] = field(default_factory=set)
    _priorities: dict[str, int] = field(default_factory=dict)

    def set_available_tokens(
        self, token_ids: list[str], priorities: dict[str, int] | None = None
    ) -> None:
        """Set the list of available tokens.

        Args:
            token_ids: List of token IDs that could be subscribed.
            priorities: Optional dict mapping token_id to priority (higher = more important).
        """
        self._available = set(token_ids)
        self._priorities = priorities or {}

        # Remove subscriptions that are no longer available
        removed = self._subscribed - self._available
        if removed:
            logger.info(f"Removing {len(removed)} tokens no longer available")
            self._subscribed -= removed

    def get_tokens_to_subscribe(self) -> list[str]:
        """Get the list of tokens that should be subscribed.

        Returns all available tokens, prioritized by the priority dict
        (highest priority first). The WebSocket pool handles splitting
        across multiple connections.

        Returns:
            List of token IDs to subscribe to.
        """
        # Sort by priority (descending), then by token_id for determinism
        sorted_tokens = sorted(
            self._available,
            key=lambda t: (-self._priorities.get(t, 0), t),
        )

        return sorted_tokens

    def mark_subscribed(self, token_ids: list[str]) -> None:
        """Mark tokens as subscribed.

        Args:
            token_ids: Token IDs that were successfully subscribed.
        """
        self._subscribed.update(token_ids)

    def mark_unsubscribed(self, token_ids: list[str]) -> None:
        """Mark tokens as unsubscribed.

        Args:
            token_ids: Token IDs that were unsubscribed.
        """
        self._subscribed.difference_update(token_ids)

    def is_subscribed(self, token_id: str) -> bool:
        """Check if a token is currently subscribed."""
        return token_id in self._subscribed

    @property
    def subscribed_count(self) -> int:
        """Get number of currently subscribed tokens."""
        return len(self._subscribed)

    @property
    def available_count(self) -> int:
        """Get number of available tokens."""
        return len(self._available)

    @property
    def subscribed_tokens(self) -> set[str]:
        """Get set of currently subscribed tokens."""
        return self._subscribed.copy()

    def get_stats(self) -> dict:
        """Get subscription statistics.

        Returns:
            Dict with subscription stats.
        """
        return {
            "subscribed": self.subscribed_count,
            "available": self.available_count,
            "max_tokens": self.max_tokens,
            "at_capacity": self.subscribed_count >= self.max_tokens,
        }
