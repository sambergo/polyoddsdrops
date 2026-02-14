"""Dump all sports markets from Gamma API to JSON for the filter explorer tool.

Fetches ALL markets (before filtering) so you can explore filter thresholds
interactively in filter-explorer.html.

Usage:
    uv run scripts/dump_markets.py
"""

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.gamma.client import (
    SPORTS_PARENT_TAG,
    GammaClient,
    extract_labels_from_tags,
    get_clob_token_ids,
    get_outcome_prices,
    get_outcomes,
    is_upcoming_game,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

OUTPUT_PATH = Path(__file__).resolve().parent / "tools" / "markets.js"


def main() -> None:
    client = GammaClient(hours_ahead=48)

    logger.info(f"Fetching ALL sports events (tag_id={SPORTS_PARENT_TAG})")
    events = client.fetch_events_by_tag(SPORTS_PARENT_TAG)
    logger.info(f"Found {len(events)} total events")

    upcoming = [e for e in events if is_upcoming_game(e, client.hours_ahead)]
    logger.info(f"Found {len(upcoming)} upcoming games (next {client.hours_ahead}h)")

    markets: list[dict] = []
    sport_counts: dict[str, int] = {}

    for event in upcoming:
        event_title = event.get("title", "Unknown")
        start_time = event.get("startTime")
        tags = event.get("tags", [])
        sport = client._extract_sport_from_event(event)
        league_label, sport_label = extract_labels_from_tags(tags)

        for market in event.get("markets", []):
            token_ids = get_clob_token_ids(market)
            outcomes = get_outcomes(market)
            prices = get_outcome_prices(market)
            question = market.get("question", market.get("groupItemTitle", "Unknown"))
            condition_id = market.get("conditionId", "")
            liquidity = market.get("liquidityNum", 0)
            spread = market.get("spread")
            volume_24h = market.get("volume24hr", 0)
            market_type = market.get("sportsMarketType")
            line = market.get("line")
            active = market.get("active", False)
            closed = market.get("closed", False)
            accepting_orders = market.get("acceptingOrders", False)

            for i, token_id in enumerate(token_ids):
                outcome = outcomes[i] if i < len(outcomes) else f"Outcome {i}"
                price = prices[i] if i < len(prices) else 0.0

                markets.append(
                    {
                        "token_id": token_id,
                        "condition_id": condition_id,
                        "question": question,
                        "outcome": outcome,
                        "event_title": event_title,
                        "sport": sport,
                        "league_label": league_label,
                        "sport_label": sport_label,
                        "market_type": market_type,
                        "line": line,
                        "liquidity": liquidity,
                        "spread": spread,
                        "volume_24h": volume_24h,
                        "price": price,
                        "game_start_time": start_time,
                        "active": active,
                        "closed": closed,
                        "accepting_orders": accepting_orders,
                    }
                )

                sport_counts[sport] = sport_counts.get(sport, 0) + 1

    output = {
        "metadata": {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "total_events": len(events),
            "upcoming_events": len(upcoming),
            "total_markets": len(markets),
            "sport_breakdown": sport_counts,
        },
        "markets": markets,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text("const MARKETS_DATA = " + json.dumps(output) + ";\n")
    logger.info(f"Wrote {len(markets)} markets to {OUTPUT_PATH}")
    logger.info(f"Sport breakdown: {sport_counts}")


if __name__ == "__main__":
    main()
