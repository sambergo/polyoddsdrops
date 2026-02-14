#!/usr/bin/env python3
"""Filter Polymarket sports events to upcoming games only.

Filters out:
- Futures markets (championship, MVP, etc.)
- Past or ongoing games
- Games more than 48 hours away
- Ineffective markets (low liquidity, high spread, stale, extreme odds)
"""

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
import httpx

GAMMA_HOST = "https://gamma-api.polymarket.com"
EXAMPLES_DIR = Path(__file__).parent.parent / "docs" / "examples"

# Sport tag IDs from Phase 1 findings
SPORT_TAGS = {
    "nfl": 450,
    "nba": 745,
    "nhl": 899,
    "mlb": 100381,
    "ncaab": 100149,
}


@dataclass
class MarketFilter:
    """Thresholds for filtering effective markets."""

    min_liquidity: float = 10_000  # USD
    max_spread: float = 0.10  # 10 cents
    min_volume_24h: float = 100  # USD
    min_price: float = 0.05  # Exclude extreme odds < 5%
    max_price: float = 0.95  # Exclude extreme odds > 95%
    exclude_extreme_odds: bool = True


# Default filter settings
DEFAULT_FILTER = MarketFilter()


def fetch_events_by_tag(tag_id: int, limit: int = 200) -> list[dict]:
    """Fetch active events filtered by tag_id."""
    with httpx.Client() as client:
        params = {
            "active": "true",
            "closed": "false",
            "tag_id": str(tag_id),
            "limit": limit,
        }
        resp = client.get(f"{GAMMA_HOST}/events", params=params)
        resp.raise_for_status()
        return resp.json()


def parse_datetime(dt_str: str) -> datetime:
    """Parse ISO-8601 datetime string to timezone-aware datetime."""
    # Handle 'Z' suffix (UTC)
    if dt_str.endswith("Z"):
        dt_str = dt_str[:-1] + "+00:00"
    return datetime.fromisoformat(dt_str)


def is_upcoming_game(event: dict, hours_ahead: int = 48) -> bool:
    """Check if event is an upcoming game within the specified time window.

    Returns True if:
    - Event has gameId (is an actual game, not futures)
    - Event has startTime
    - startTime is in the future
    - startTime is within hours_ahead from now
    """
    # Must have gameId - this is the key differentiator
    if "gameId" not in event:
        return False

    # Must have startTime
    start_time_str = event.get("startTime")
    if not start_time_str:
        return False

    try:
        start_time = parse_datetime(start_time_str)
    except (ValueError, TypeError):
        return False

    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(hours=hours_ahead)

    # Must be in the future and within time window
    return now < start_time <= cutoff


def filter_upcoming_games(events: list[dict], hours_ahead: int = 48) -> list[dict]:
    """Filter events to only upcoming games within time window."""
    return [e for e in events if is_upcoming_game(e, hours_ahead)]


def get_outcome_prices(market: dict) -> list[float]:
    """Parse outcome prices from market data."""
    prices_raw = market.get("outcomePrices", "[]")
    if isinstance(prices_raw, str):
        try:
            prices = json.loads(prices_raw)
        except json.JSONDecodeError:
            return []
    else:
        prices = prices_raw

    result = []
    for p in prices:
        try:
            result.append(float(p))
        except (ValueError, TypeError):
            pass
    return result


def check_market_rejection_reason(market: dict, f: MarketFilter) -> str | None:
    """Return rejection reason if market fails filters, None if it passes.

    Returns the first failing criterion for debugging purposes.
    """
    # Must be active and open
    if not market.get("active", False):
        return "inactive"
    if market.get("closed", False):
        return "closed"
    if not market.get("acceptingOrders", False):
        return "not_accepting_orders"

    # Liquidity check
    liquidity = market.get("liquidityNum", 0)
    if liquidity < f.min_liquidity:
        return f"low_liquidity ({liquidity:.0f} < {f.min_liquidity:.0f})"

    # Spread check
    spread = market.get("spread")
    if spread is None:
        return "no_spread_data"
    if spread > f.max_spread:
        return f"high_spread ({spread:.2f} > {f.max_spread:.2f})"

    # 24h volume check
    volume_24h = market.get("volume24hr", 0)
    if volume_24h < f.min_volume_24h:
        return f"low_volume_24h ({volume_24h:.0f} < {f.min_volume_24h:.0f})"

    # Extreme odds check (optional)
    if f.exclude_extreme_odds:
        prices = get_outcome_prices(market)
        if prices:
            # Check if primary outcome price is in acceptable range
            primary_price = prices[0]
            if primary_price < f.min_price or primary_price > f.max_price:
                return f"extreme_odds ({primary_price:.3f})"

    return None  # Market passes all filters


def is_effective_market(market: dict, f: MarketFilter = DEFAULT_FILTER) -> bool:
    """Check if market passes all effectiveness filters."""
    return check_market_rejection_reason(market, f) is None


def filter_effective_markets(
    markets: list[dict], f: MarketFilter = DEFAULT_FILTER
) -> tuple[list[dict], dict[str, int]]:
    """Filter markets to only effective ones.

    Returns:
        Tuple of (effective_markets, rejection_counts)
    """
    effective = []
    rejection_counts: dict[str, int] = {}

    for market in markets:
        reason = check_market_rejection_reason(market, f)
        if reason is None:
            effective.append(market)
        else:
            # Extract reason category (first word before parenthesis)
            category = reason.split(" ")[0]
            rejection_counts[category] = rejection_counts.get(category, 0) + 1

    return effective, rejection_counts


def main():
    """Main entry point."""
    print("=" * 60)
    print("Polymarket Upcoming Games Filter")
    print("=" * 60)

    now = datetime.now(timezone.utc)
    print(f"\nCurrent time (UTC): {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print("Looking for games in next 48 hours")
    print("\nMarket filter settings:")
    print(f"  Min liquidity: ${DEFAULT_FILTER.min_liquidity:,.0f}")
    print(f"  Max spread: {DEFAULT_FILTER.max_spread:.0%}")
    print(f"  Min 24h volume: ${DEFAULT_FILTER.min_volume_24h:,.0f}")
    print(
        f"  Odds range: {DEFAULT_FILTER.min_price:.0%} - {DEFAULT_FILTER.max_price:.0%}"
    )

    all_upcoming: dict[str, list[dict]] = {}
    total_markets = 0
    total_effective = 0

    for sport, tag_id in SPORT_TAGS.items():
        print(f"\n{'=' * 60}")
        print(f"{sport.upper()} (tag={tag_id})")
        print("=" * 60)

        events = fetch_events_by_tag(tag_id)
        print(f"Total events fetched: {len(events)}")

        # Count events with gameId vs without
        with_game_id = [e for e in events if "gameId" in e]
        without_game_id = [e for e in events if "gameId" not in e]
        print(f"  With gameId (games): {len(with_game_id)}")
        print(f"  Without gameId (futures): {len(without_game_id)}")

        upcoming = filter_upcoming_games(events)
        print(f"Upcoming games (next 48h): {len(upcoming)}")

        # Process each game and filter its markets
        filtered_events = []
        for game in sorted(upcoming, key=lambda x: x.get("startTime", "")):
            title = game.get("title", "Unknown")
            start_time = parse_datetime(game["startTime"])
            time_until = start_time - now
            hours = time_until.total_seconds() / 3600

            markets = game.get("markets", [])
            effective_markets, rejections = filter_effective_markets(markets)

            total_markets += len(markets)
            total_effective += len(effective_markets)

            print(f"\n  {title}")
            print(
                f"    Start: {start_time.strftime('%Y-%m-%d %H:%M')} UTC ({hours:.1f}h)"
            )
            print(f"    Markets: {len(effective_markets)}/{len(markets)} effective")

            if rejections:
                rejection_summary = ", ".join(
                    f"{k}:{v}" for k, v in sorted(rejections.items())
                )
                print(f"    Filtered out: {rejection_summary}")

            # Show effective markets
            for m in effective_markets:
                question = m.get("question", m.get("groupItemTitle", "Unknown"))
                liquidity = m.get("liquidityNum", 0)
                spread = m.get("spread", 0)
                volume_24h = m.get("volume24hr", 0)
                prices = get_outcome_prices(m)
                price_str = f"{prices[0]:.2f}" if prices else "?"

                print(f"      - {question}")
                print(
                    f"        liq=${liquidity:,.0f} spread={spread:.2f} vol24h=${volume_24h:,.0f} price={price_str}"
                )

            # Store event with only effective markets
            if effective_markets:
                filtered_game = game.copy()
                filtered_game["markets"] = effective_markets
                filtered_events.append(filtered_game)

        all_upcoming[sport] = filtered_events

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    total_games = sum(len(games) for games in all_upcoming.values())
    print(f"\nGames with effective markets: {total_games}")
    print(f"Total markets analyzed: {total_markets}")
    print(
        f"Effective markets: {total_effective} ({100 * total_effective / total_markets:.1f}%)"
        if total_markets
        else "No markets"
    )

    for sport, games in all_upcoming.items():
        if games:
            market_count = sum(len(g.get("markets", [])) for g in games)
            print(f"  {sport.upper()}: {len(games)} games, {market_count} markets")

    # Save sample output
    EXAMPLES_DIR.mkdir(parents=True, exist_ok=True)

    # Flatten all upcoming games for output
    all_games_flat: list[dict] = []
    for sport, games in all_upcoming.items():
        for game in games:
            game["_sport"] = sport  # Add sport tag for reference
            all_games_flat.append(game)

    if all_games_flat:
        output_file = EXAMPLES_DIR / "upcoming_games_filtered.json"
        with open(output_file, "w") as f:
            json.dump(all_games_flat[:10], f, indent=2, default=str)
        print(f"\nSaved sample to {output_file}")


if __name__ == "__main__":
    main()
