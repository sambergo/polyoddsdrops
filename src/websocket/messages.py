"""Normalize Polymarket market-channel messages into top-of-book updates."""

import json
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class TopOfBookMessage:
    """Latest best bid and ask for one asset."""

    asset_id: str
    market: str
    timestamp: int
    best_bid: float
    best_ask: float

    @property
    def mid_price(self) -> float:
        return (self.best_bid + self.best_ask) / 2


# Compatibility aliases for callers that imported the old message names.
BookMessage = TopOfBookMessage
PriceChangeMessage = TopOfBookMessage


def _as_float(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _as_timestamp(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _parse_book(item: dict) -> TopOfBookMessage | None:
    asset_id = item.get("asset_id")
    if not isinstance(asset_id, str) or not asset_id:
        return None

    bids = (
        price
        for level in item.get("bids", [])
        if isinstance(level, dict)
        if (price := _as_float(level.get("price"))) is not None
    )
    asks = (
        price
        for level in item.get("asks", [])
        if isinstance(level, dict)
        if (price := _as_float(level.get("price"))) is not None
    )
    best_bid = max(bids, default=None)
    best_ask = min(asks, default=None)
    if best_bid is None or best_ask is None:
        return None

    return TopOfBookMessage(
        asset_id=asset_id,
        market=str(item.get("market", "")),
        timestamp=_as_timestamp(item.get("timestamp")),
        best_bid=best_bid,
        best_ask=best_ask,
    )


def _parse_price_changes(item: dict) -> list[TopOfBookMessage]:
    """Return the last documented top-of-book state for each changed asset."""
    by_asset: dict[str, TopOfBookMessage] = {}
    market = str(item.get("market", ""))
    timestamp = _as_timestamp(item.get("timestamp"))

    for change in item.get("price_changes", []):
        if not isinstance(change, dict):
            continue
        asset_id = change.get("asset_id")
        best_bid = _as_float(change.get("best_bid"))
        best_ask = _as_float(change.get("best_ask"))
        if (
            not isinstance(asset_id, str)
            or not asset_id
            or best_bid is None
            or best_ask is None
        ):
            continue
        by_asset[asset_id] = TopOfBookMessage(
            asset_id=asset_id,
            market=market,
            timestamp=timestamp,
            best_bid=best_bid,
            best_ask=best_ask,
        )

    return list(by_asset.values())


def parse_message(raw: str | bytes) -> list[TopOfBookMessage]:
    """Parse one raw frame, ignoring events without a complete top of book."""
    if raw == "PONG" or raw == b"PONG":
        return []

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError):
        logger.warning("Failed to parse WebSocket message")
        return []

    items = data if isinstance(data, list) else [data]
    messages: list[TopOfBookMessage] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        event_type = item.get("event_type")
        if event_type == "book":
            if message := _parse_book(item):
                messages.append(message)
        elif event_type == "price_change":
            messages.extend(_parse_price_changes(item))

    return messages
