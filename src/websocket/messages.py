"""WebSocket message parsing for Polymarket CLOB API."""

import json
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class OrderBookLevel:
    """Single level in an order book."""

    price: float
    size: float


@dataclass
class BookMessage:
    """Full order book snapshot message."""

    event_type: str  # "book"
    asset_id: str
    market: str
    timestamp: int
    bids: list[OrderBookLevel]
    asks: list[OrderBookLevel]
    best_bid: float | None = None
    best_ask: float | None = None
    mid_price: float | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "BookMessage":
        """Parse a book message from WebSocket data."""
        bids = [
            OrderBookLevel(price=float(b["price"]), size=float(b["size"]))
            for b in data.get("bids", [])
        ]
        asks = [
            OrderBookLevel(price=float(a["price"]), size=float(a["size"]))
            for a in data.get("asks", [])
        ]

        best_bid = max((b.price for b in bids), default=None)
        best_ask = min((a.price for a in asks), default=None)
        mid_price = None
        if best_bid is not None and best_ask is not None:
            mid_price = (best_bid + best_ask) / 2

        return cls(
            event_type=data.get("event_type", "book"),
            asset_id=data.get("asset_id", ""),
            market=data.get("market", ""),
            timestamp=data.get("timestamp", 0),
            bids=bids,
            asks=asks,
            best_bid=best_bid,
            best_ask=best_ask,
            mid_price=mid_price,
        )


@dataclass
class PriceChange:
    """Individual price change within a price_change message."""

    price: float
    side: str  # "BUY" or "SELL"
    size: float


@dataclass
class PriceChangeMessage:
    """Incremental price change message."""

    event_type: str  # "price_change"
    asset_id: str
    market: str
    timestamp: int
    changes: list[PriceChange]

    @classmethod
    def from_dict(cls, data: dict) -> "PriceChangeMessage":
        """Parse a price_change message from WebSocket data."""
        changes = []
        for change in data.get("price_changes", []):
            changes.append(
                PriceChange(
                    price=float(change.get("price", 0)),
                    side=change.get("side", ""),
                    size=float(change.get("size", 0)),
                )
            )

        return cls(
            event_type=data.get("event_type", "price_change"),
            asset_id=data.get("asset_id", ""),
            market=data.get("market", ""),
            timestamp=data.get("timestamp", 0),
            changes=changes,
        )


def parse_message(raw: str) -> list[BookMessage | PriceChangeMessage]:
    """Parse a raw WebSocket message into typed message objects.

    Returns a list because messages may arrive as arrays (batched).
    """
    if raw == "PONG":
        return []

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning(f"Failed to parse WebSocket message: {raw[:100]}")
        return []

    # Handle both single objects and arrays
    items = data if isinstance(data, list) else [data]

    messages: list[BookMessage | PriceChangeMessage] = []
    for item in items:
        if not isinstance(item, dict):
            continue

        event_type = item.get("event_type")
        if event_type == "book":
            messages.append(BookMessage.from_dict(item))
        elif event_type == "price_change":
            messages.append(PriceChangeMessage.from_dict(item))
        else:
            logger.debug(f"Unknown message type: {event_type}")

    return messages
