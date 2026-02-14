#!/usr/bin/env python3
"""Debug script to inspect market filtering decisions.

Shows all markets for upcoming games (next 48h) with their filter criteria data,
grouped by whether they're included or excluded by current filters.
"""

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import json
import httpx

GAMMA_HOST = "https://gamma-api.polymarket.com"

# Sport tag IDs
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
    if dt_str.endswith("Z"):
        dt_str = dt_str[:-1] + "+00:00"
    return datetime.fromisoformat(dt_str)


def is_upcoming_game(event: dict, hours_ahead: int = 48) -> bool:
    """Check if event is an upcoming game within the specified time window."""
    if "gameId" not in event:
        return False

    start_time_str = event.get("startTime")
    if not start_time_str:
        return False

    try:
        start_time = parse_datetime(start_time_str)
    except (ValueError, TypeError):
        return False

    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(hours=hours_ahead)

    return now < start_time <= cutoff


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
    """Return rejection reason if market fails filters, None if it passes."""
    if not market.get("active", False):
        return "inactive"
    if market.get("closed", False):
        return "closed"
    if not market.get("acceptingOrders", False):
        return "not_accepting_orders"

    liquidity = market.get("liquidityNum", 0)
    if liquidity < f.min_liquidity:
        return "low_liquidity"

    spread = market.get("spread")
    if spread is None:
        return "no_spread_data"
    if spread > f.max_spread:
        return "high_spread"

    volume_24h = market.get("volume24hr", 0)
    if volume_24h < f.min_volume_24h:
        return "low_volume_24h"

    if f.exclude_extreme_odds:
        prices = get_outcome_prices(market)
        if prices:
            primary_price = prices[0]
            if primary_price < f.min_price or primary_price > f.max_price:
                return "extreme_odds"

    return None


def format_market_line(market: dict, rejection_reason: str | None = None) -> str:
    """Format a single market's data as a readable line."""
    question = market.get("question", market.get("groupItemTitle", "Unknown"))
    market_type = market.get("sportsMarketType", "unknown")

    # Get filter criteria values
    liquidity = market.get("liquidityNum", 0)
    spread = market.get("spread")
    volume_24h = market.get("volume24hr", 0)
    competitive = market.get("competitive", 0)
    active = market.get("active", False)
    closed = market.get("closed", False)
    accepting = market.get("acceptingOrders", False)

    prices = get_outcome_prices(market)
    price_str = f"{prices[0]:.3f}" if prices else "?"

    # Format spread safely
    spread_str = f"{spread:.2f}" if spread is not None else "N/A"

    # Build the line
    status_flags = []
    if not active:
        status_flags.append("!active")
    if closed:
        status_flags.append("closed")
    if not accepting:
        status_flags.append("!accepting")
    status_str = f" [{', '.join(status_flags)}]" if status_flags else ""

    line = (
        f"    {question[:60]:<60} | "
        f"liq=${liquidity:>10,.0f} | "
        f"spread={spread_str:>5} | "
        f"vol24h=${volume_24h:>10,.0f} | "
        f"price={price_str:>5} | "
        f"comp={competitive:.3f} | "
        f"type={market_type:<12}"
        f"{status_str}"
    )

    if rejection_reason:
        line += f" >> REASON: {rejection_reason}"

    return line


def main():
    """Main entry point."""
    print("=" * 140)
    print("MARKET FILTER DEBUG - All Markets for Upcoming Games")
    print("=" * 140)

    now = datetime.now(timezone.utc)
    print(f"\nCurrent time (UTC): {now.strftime('%Y-%m-%d %H:%M:%S')}")

    print(f"\n{'CURRENT FILTER THRESHOLDS':=^140}")
    print(f"  min_liquidity:      ${DEFAULT_FILTER.min_liquidity:,.0f}")
    print(
        f"  max_spread:         {DEFAULT_FILTER.max_spread:.2f} ({DEFAULT_FILTER.max_spread:.0%})"
    )
    print(f"  min_volume_24h:     ${DEFAULT_FILTER.min_volume_24h:,.0f}")
    print(
        f"  price_range:        {DEFAULT_FILTER.min_price:.2f} - {DEFAULT_FILTER.max_price:.2f}"
    )
    print(f"  exclude_extreme:    {DEFAULT_FILTER.exclude_extreme_odds}")

    print(f"\n{'COLUMN LEGEND':=^140}")
    print("  liq       = liquidityNum (total liquidity in USD)")
    print("  spread    = bid-ask spread (lower is better, <0.10 passes)")
    print("  vol24h    = volume24hr (24h trading volume in USD)")
    print("  price     = primary outcome price (odds)")
    print("  comp      = competitive score (higher is better, 1.0 = perfect)")
    print("  type      = sportsMarketType (moneyline, spread, totals, etc.)")

    total_included = 0
    total_excluded = 0

    for sport, tag_id in SPORT_TAGS.items():
        events = fetch_events_by_tag(tag_id)
        upcoming = [e for e in events if is_upcoming_game(e)]

        if not upcoming:
            continue

        print(f"\n{'=' * 140}")
        print(f" {sport.upper()} - {len(upcoming)} upcoming games")
        print("=" * 140)

        for game in sorted(upcoming, key=lambda x: x.get("startTime", "")):
            title = game.get("title", "Unknown")
            start_time = parse_datetime(game["startTime"])
            time_until = start_time - now
            hours = time_until.total_seconds() / 3600

            markets = game.get("markets", [])

            # Separate included vs excluded
            included = []
            excluded = []

            for m in markets:
                reason = check_market_rejection_reason(m, DEFAULT_FILTER)
                if reason is None:
                    included.append(m)
                else:
                    excluded.append((m, reason))

            total_included += len(included)
            total_excluded += len(excluded)

            print(f"\n{'-' * 140}")
            print(f"  {title}")
            print(
                f"  Start: {start_time.strftime('%Y-%m-%d %H:%M')} UTC ({hours:.1f}h away)"
            )
            print(
                f"  Markets: {len(included)} included, {len(excluded)} excluded, {len(markets)} total"
            )
            print(f"{'-' * 140}")

            # Print INCLUDED markets
            if included:
                print(f"\n  [INCLUDED] ({len(included)} markets)")
                for m in sorted(
                    included, key=lambda x: x.get("liquidityNum", 0), reverse=True
                ):
                    print(format_market_line(m))

            # Print EXCLUDED markets
            if excluded:
                print(f"\n  [EXCLUDED] ({len(excluded)} markets)")
                # Group by rejection reason
                by_reason: dict[str, list[dict]] = {}
                for m, reason in excluded:
                    by_reason.setdefault(reason, []).append(m)

                for reason in sorted(by_reason.keys()):
                    print(f"\n    -- {reason} ({len(by_reason[reason])}) --")
                    for m in sorted(
                        by_reason[reason],
                        key=lambda x: x.get("liquidityNum", 0),
                        reverse=True,
                    ):
                        print(format_market_line(m, reason))

    # Final summary
    print(f"\n{'=' * 140}")
    print(f"{'SUMMARY':=^140}")
    print("=" * 140)
    print(f"  Total INCLUDED markets: {total_included}")
    print(f"  Total EXCLUDED markets: {total_excluded}")
    print(
        f"  Inclusion rate: {100 * total_included / (total_included + total_excluded):.1f}%"
    )


if __name__ == "__main__":
    main()
