"""Database models for Polydrop."""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class MarketRow:
    """Represents a market token in the database."""

    token_id: str
    condition_id: str
    question: str
    outcome: str
    event_title: str | None = None
    sport: str | None = None
    league_label: str | None = None
    sport_label: str | None = None
    market_type: str | None = None
    line: float | None = None
    liquidity: float | None = None
    spread: float | None = None
    volume_24h: float | None = None
    is_subscribed: bool = False
    is_active: bool = True
    priority: int = 0
    game_start_time: str | None = None
    event_slug: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


@dataclass
class AlertRow:
    """Represents an alert in the database."""

    id: int | None
    token_id: str
    alert_type: str
    old_price: float
    new_price: float
    price_change_pct: float
    time_window_seconds: int
    detected_at: str

    @classmethod
    def create(
        cls,
        token_id: str,
        alert_type: str,
        old_price: float,
        new_price: float,
        price_change_pct: float,
        time_window_seconds: int,
    ) -> "AlertRow":
        """Create a new alert with current timestamp."""
        return cls(
            id=None,
            token_id=token_id,
            alert_type=alert_type,
            old_price=old_price,
            new_price=new_price,
            price_change_pct=price_change_pct,
            time_window_seconds=time_window_seconds,
            detected_at=datetime.utcnow().isoformat(),
        )
