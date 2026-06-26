"""Gamma API client for fetching Polymarket sports markets."""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx

from ..config import GAMMA_HOST, SPORT_TAGS, MarketFilterConfig
from ..db.models import MarketRow

# Parent tag for ALL sports on Polymarket
SPORTS_PARENT_TAG = 1

# Gamma currently caps /events pages at 100 items even if a larger limit is
# requested. Keep our request aligned with that cap so pagination does not stop
# after the first page.
EVENTS_PAGE_LIMIT = 100

logger = logging.getLogger(__name__)


@dataclass
class FetchedMarket:
    """Intermediate representation of a market from Gamma API."""

    token_id: str
    condition_id: str
    question: str
    outcome: str
    event_title: str
    sport: str
    league_label: str | None
    sport_label: str | None
    market_type: str | None
    line: float | None
    liquidity: float
    spread: float | None
    volume_24h: float
    price: float
    game_start_time: str | None
    event_slug: str | None


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


def get_outcomes(market: dict) -> list[str]:
    """Parse outcomes from market data."""
    outcomes_raw = market.get("outcomes", "[]")
    if isinstance(outcomes_raw, str):
        try:
            outcomes = json.loads(outcomes_raw)
        except json.JSONDecodeError:
            return []
    else:
        outcomes = outcomes_raw
    return outcomes


def get_clob_token_ids(market: dict) -> list[str]:
    """Parse CLOB token IDs from market data."""
    tokens_raw = market.get("clobTokenIds", "[]")
    if isinstance(tokens_raw, str):
        try:
            tokens = json.loads(tokens_raw)
        except json.JSONDecodeError:
            return []
    else:
        tokens = tokens_raw
    return tokens


def extract_labels_from_tags(tags: list[dict]) -> tuple[str | None, str | None]:
    """Extract league and sport labels from event tags.

    Returns:
        Tuple of (league_label, sport_label)
        - league_label: specific league like "NBA", "EPL", "La Liga"
        - sport_label: sport category like "Basketball", "Soccer"
    """
    league_label = None
    sport_label = None

    # Known sport category labels (these are the general sport types)
    sport_categories = {
        "basketball",
        "soccer",
        "football",
        "baseball",
        "hockey",
        "tennis",
        "golf",
        "mma",
        "boxing",
        "cricket",
        "rugby",
        "esports",
        "motorsport",
        "racing",
    }

    # Skip these generic/meta tags
    skip_labels = {"sports", "hide from new"}

    for tag in tags:
        label = tag.get("label", "")
        label_lower = label.lower()

        if label_lower in skip_labels:
            continue

        # Check if it's a sport category
        if label_lower in sport_categories:
            sport_label = label
        # Otherwise it might be a league (NBA, EPL, etc.) - take first non-category
        elif league_label is None and label:
            league_label = label

    return league_label, sport_label


def check_market_rejection_reason(market: dict, f: MarketFilterConfig) -> str | None:
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

    prices = get_outcome_prices(market)
    if prices:
        primary_price = prices[0]
        if primary_price < f.min_price or primary_price > f.max_price:
            return "extreme_odds"

    return None


class GammaClient:
    """Client for Polymarket Gamma API."""

    def __init__(
        self,
        filter_config: MarketFilterConfig,
        hours_ahead: int = 48,
    ) -> None:
        """Initialize the Gamma API client.

        Args:
            filter_config: Market filter configuration.
            hours_ahead: How far ahead to look for upcoming games (default 48h).
        """
        self.filter = filter_config
        self.hours_ahead = hours_ahead

    def fetch_events_by_tag(
        self, tag_id: int, limit: int = EVENTS_PAGE_LIMIT
    ) -> list[dict]:
        """Fetch all active events filtered by tag_id, with pagination."""
        all_events: list[dict] = []
        page_limit = min(limit, EVENTS_PAGE_LIMIT)

        with httpx.Client() as client:
            while True:
                params = {
                    "active": "true",
                    "closed": "false",
                    "tag_id": str(tag_id),
                    "limit": page_limit,
                    "offset": str(len(all_events)),
                }
                resp = client.get(f"{GAMMA_HOST}/events", params=params)
                if resp.status_code == 422 and all_events:
                    logger.warning(
                        "Gamma events pagination stopped at offset %s with 422; "
                        "using %s events fetched so far",
                        len(all_events),
                        len(all_events),
                    )
                    break
                resp.raise_for_status()
                events = resp.json()

                if not events:
                    break

                all_events.extend(events)
                logger.debug(f"Fetched {len(events)} events (total: {len(all_events)})")

                # Stop when we get fewer than limit (last page)
                if len(events) < page_limit:
                    break

        return all_events

    def fetch_sports_markets(
        self, sports: list[str]
    ) -> tuple[list[FetchedMarket], dict[str, int]]:
        """Fetch and filter markets for specified sports.

        Args:
            sports: List of sport names (e.g., ["nfl", "nba", "nhl"])

        Returns:
            Tuple of (filtered_markets, rejection_counts)
        """
        all_markets: list[FetchedMarket] = []
        total_rejections: dict[str, int] = {}

        for sport in sports:
            tag_id = SPORT_TAGS.get(sport.lower())
            if tag_id is None:
                logger.warning(f"Unknown sport: {sport}")
                continue

            logger.info(f"Fetching {sport.upper()} events (tag_id={tag_id})")
            events = self.fetch_events_by_tag(tag_id)
            logger.info(f"Found {len(events)} total events")

            # Filter to upcoming games
            upcoming = [e for e in events if is_upcoming_game(e, self.hours_ahead)]
            logger.info(
                f"Found {len(upcoming)} upcoming games (next {self.hours_ahead}h)"
            )

            for event in upcoming:
                event_title = event.get("title", "Unknown")
                start_time = event.get("startTime")
                event_slug = event.get("slug")
                markets = event.get("markets", [])
                tags = event.get("tags", [])

                # Extract league and sport labels from tags
                league_label, sport_label = extract_labels_from_tags(tags)

                for market in markets:
                    # Check filter criteria
                    rejection = check_market_rejection_reason(market, self.filter)
                    if rejection:
                        total_rejections[rejection] = (
                            total_rejections.get(rejection, 0) + 1
                        )
                        continue

                    # Extract market data
                    token_ids = get_clob_token_ids(market)
                    outcomes = get_outcomes(market)
                    prices = get_outcome_prices(market)
                    question = market.get(
                        "question", market.get("groupItemTitle", "Unknown")
                    )
                    condition_id = market.get("conditionId", "")
                    liquidity = market.get("liquidityNum", 0)
                    spread = market.get("spread")
                    volume_24h = market.get("volume24hr", 0)

                    # Extract market type and line
                    market_type = market.get("sportsMarketType")
                    line = market.get("line")

                    # Create a FetchedMarket for each token
                    # Skip "No" tokens in binary markets - they're redundant
                    # and cause inverted odds display
                    for i, token_id in enumerate(token_ids):
                        outcome = outcomes[i] if i < len(outcomes) else f"Outcome {i}"
                        if outcome.lower() == "no":
                            continue
                        price = prices[i] if i < len(prices) else 0.0

                        all_markets.append(
                            FetchedMarket(
                                token_id=token_id,
                                condition_id=condition_id,
                                question=question,
                                outcome=outcome,
                                event_title=event_title,
                                sport=sport.lower(),
                                league_label=league_label,
                                sport_label=sport_label,
                                market_type=market_type,
                                line=line,
                                liquidity=liquidity,
                                spread=spread,
                                volume_24h=volume_24h,
                                price=price,
                                game_start_time=start_time,
                                event_slug=event_slug,
                            )
                        )

        logger.info(
            f"Total filtered markets: {len(all_markets)}, "
            f"Rejections: {sum(total_rejections.values())}"
        )
        if total_rejections:
            logger.debug(f"Rejection breakdown: {total_rejections}")

        return all_markets, total_rejections

    def fetch_all_sports_markets(
        self,
    ) -> tuple[list[FetchedMarket], dict[str, int]]:
        """Fetch ALL sports markets using the parent Sports tag (tag_id=1).

        This fetches all sports events in a single API call, then applies
        the same filtering as fetch_sports_markets().

        Returns:
            Tuple of (filtered_markets, rejection_counts)
        """
        logger.info(f"Fetching ALL sports events (tag_id={SPORTS_PARENT_TAG})")
        events = self.fetch_events_by_tag(SPORTS_PARENT_TAG)
        logger.info(f"Found {len(events)} total events")

        # Filter to upcoming games
        upcoming = [e for e in events if is_upcoming_game(e, self.hours_ahead)]
        logger.info(f"Found {len(upcoming)} upcoming games (next {self.hours_ahead}h)")

        all_markets: list[FetchedMarket] = []
        total_rejections: dict[str, int] = {}

        for event in upcoming:
            event_title = event.get("title", "Unknown")
            start_time = event.get("startTime")
            event_slug = event.get("slug")
            markets = event.get("markets", [])
            tags = event.get("tags", [])

            # Extract sport from event tags for labeling
            sport = self._extract_sport_from_event(event)

            # Extract league and sport labels from tags
            league_label, sport_label = extract_labels_from_tags(tags)

            for market in markets:
                # Check filter criteria
                rejection = check_market_rejection_reason(market, self.filter)
                if rejection:
                    total_rejections[rejection] = total_rejections.get(rejection, 0) + 1
                    continue

                # Extract market data
                token_ids = get_clob_token_ids(market)
                outcomes = get_outcomes(market)
                prices = get_outcome_prices(market)
                question = market.get(
                    "question", market.get("groupItemTitle", "Unknown")
                )
                condition_id = market.get("conditionId", "")
                liquidity = market.get("liquidityNum", 0)
                spread = market.get("spread")
                volume_24h = market.get("volume24hr", 0)

                # Extract market type and line
                market_type = market.get("sportsMarketType")
                line = market.get("line")

                # Create a FetchedMarket for each token
                # Skip "No" tokens in binary markets - they're redundant
                # and cause inverted odds display
                for i, token_id in enumerate(token_ids):
                    outcome = outcomes[i] if i < len(outcomes) else f"Outcome {i}"
                    if outcome.lower() == "no":
                        continue
                    price = prices[i] if i < len(prices) else 0.0

                    all_markets.append(
                        FetchedMarket(
                            token_id=token_id,
                            condition_id=condition_id,
                            question=question,
                            outcome=outcome,
                            event_title=event_title,
                            sport=sport,
                            league_label=league_label,
                            sport_label=sport_label,
                            market_type=market_type,
                            line=line,
                            liquidity=liquidity,
                            spread=spread,
                            volume_24h=volume_24h,
                            price=price,
                            game_start_time=start_time,
                            event_slug=event_slug,
                        )
                    )

        logger.info(
            f"Total filtered markets: {len(all_markets)}, "
            f"Rejections: {sum(total_rejections.values())}"
        )
        if total_rejections:
            logger.debug(f"Rejection breakdown: {total_rejections}")

        return all_markets, total_rejections

    def _extract_sport_from_event(self, event: dict) -> str:
        """Extract sport name from event tags.

        Looks for common sport tags and returns the first match.
        Falls back to "sports" if no specific sport found.
        """
        tags = event.get("tags", [])

        # Known sport tag names (lowercase for matching)
        sport_keywords = {
            "nfl",
            "nba",
            "nhl",
            "mlb",
            "ncaab",
            "ncaaf",
            "soccer",
            "football",
            "tennis",
            "golf",
            "mma",
            "ufc",
            "boxing",
            "cricket",
            "rugby",
            "f1",
            "nascar",
            "esports",
            "dota",
            "csgo",
            "league of legends",
        }

        for tag in tags:
            tag_label = tag.get("label", "").lower()
            tag_slug = tag.get("slug", "").lower()

            # Check if tag matches a known sport
            for sport in sport_keywords:
                if sport in tag_label or sport in tag_slug:
                    return sport

        return "sports"

    def to_market_rows(self, markets: list[FetchedMarket]) -> list[MarketRow]:
        """Convert FetchedMarkets to MarketRows for database storage."""
        return [
            MarketRow(
                token_id=m.token_id,
                condition_id=m.condition_id,
                question=m.question,
                outcome=m.outcome,
                event_title=m.event_title,
                sport=m.sport,
                league_label=m.league_label,
                sport_label=m.sport_label,
                market_type=m.market_type,
                line=m.line,
                liquidity=m.liquidity,
                spread=m.spread,
                volume_24h=m.volume_24h,
                is_subscribed=False,
                is_active=True,
                priority=0,
                game_start_time=m.game_start_time,
                event_slug=m.event_slug,
            )
            for m in markets
        ]
