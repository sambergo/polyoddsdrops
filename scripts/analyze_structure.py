#!/usr/bin/env python3
"""Analyze Polymarket data structure: Events → Markets → Tokens.

This script fetches markets from both APIs and documents:
- Binary markets (Yes/No)
- Sports markets (Team A/Team B)
- Multi-outcome markets (multiple options)
- Token pricing verification (sum to 1.0)
"""

import json
from pathlib import Path

import httpx

CLOB_HOST = "https://clob.polymarket.com"
GAMMA_HOST = "https://gamma-api.polymarket.com"
EXAMPLES_DIR = Path(__file__).parent.parent / "docs" / "examples"


def fetch_market_types():
    """Fetch examples of different market types."""
    print("=" * 60)
    print("Fetching Market Type Examples")
    print("=" * 60)

    with httpx.Client() as client:
        # Fetch active events to find different market types
        print("\nFetching active events from Gamma API...")
        resp = client.get(
            f"{GAMMA_HOST}/events",
            params={"active": "true", "closed": "false", "limit": 100},
        )
        resp.raise_for_status()
        events = resp.json()
        print(f"Fetched {len(events)} events")

        binary_example = None
        sports_example = None
        multi_market_example = None  # Event with multiple related markets

        for event in events:
            markets = event.get("markets", [])
            if not markets:
                continue

            # Check first market in event
            market = markets[0]
            outcomes_str = market.get("outcomes", "[]")
            if isinstance(outcomes_str, str):
                outcomes = json.loads(outcomes_str)
            else:
                outcomes = outcomes_str

            # Classify market type
            is_sports = any(
                tag in event.get("title", "").lower()
                for tag in ["nba", "nfl", "mlb", "nhl", "ncaa", "vs", "match"]
            )

            # Simple binary Yes/No
            if len(outcomes) == 2 and outcomes == ["Yes", "No"] and not binary_example:
                if len(markets) == 1:  # Single market event
                    binary_example = event
                    print(f"  Found binary market: {event.get('title', '')[:50]}")

            # Sports market
            if is_sports and not sports_example:
                sports_example = event
                print(f"  Found sports market: {event.get('title', '')[:50]}")

            # Multi-market event (Polymarket's way of handling multi-outcome)
            # These have multiple related binary markets under one event
            if len(markets) > 5 and not multi_market_example:
                multi_market_example = event
                print(
                    f"  Found multi-market event ({len(markets)} markets): {event.get('title', '')[:50]}"
                )

        # If no sports found, look in sports-specific endpoint
        if not sports_example:
            print("\n  Searching sports-specific events...")
            try:
                resp = client.get(
                    f"{GAMMA_HOST}/events",
                    params={"tag": "Sports", "active": "true", "limit": 20},
                )
                resp.raise_for_status()
                sports_events = resp.json()
                for event in sports_events:
                    markets = event.get("markets", [])
                    if markets:
                        sports_example = event
                        print(f"  Found sports market: {event.get('title', '')[:50]}")
                        break
            except Exception as e:
                print(f"  Sports search failed: {e}")

        return binary_example, sports_example, multi_market_example


def analyze_market_structure(market: dict, market_type: str):
    """Analyze and print market structure details."""
    print(f"\n{'=' * 60}")
    print(f"{market_type} Market Analysis")
    print("=" * 60)

    print(f"\nEvent Title: {market.get('title', 'N/A')}")
    print(f"Event ID: {market.get('id', 'N/A')}")

    markets = market.get("markets", [])
    print(f"\nNumber of Markets in Event: {len(markets)}")

    for i, m in enumerate(markets[:3]):  # Show first 3 markets
        print(f"\n  --- Market {i + 1} ---")
        print(f"  Question: {m.get('question', 'N/A')[:80]}")
        print(f"  Condition ID: {m.get('conditionId', 'N/A')}")
        print(f"  Question ID: {m.get('questionID', 'N/A')}")

        # Parse outcomes and prices
        outcomes_str = m.get("outcomes", "[]")
        prices_str = m.get("outcomePrices", "[]")

        if isinstance(outcomes_str, str):
            outcomes = json.loads(outcomes_str)
        else:
            outcomes = outcomes_str

        if isinstance(prices_str, str):
            prices = json.loads(prices_str)
        else:
            prices = prices_str

        # Parse token IDs
        token_ids_str = m.get("clobTokenIds", "[]")
        if isinstance(token_ids_str, str):
            token_ids = json.loads(token_ids_str)
        else:
            token_ids = token_ids_str

        print("\n  Outcomes and Tokens:")
        total_price = 0.0
        for j, outcome in enumerate(outcomes):
            price = float(prices[j]) if j < len(prices) else 0
            token_id = token_ids[j] if j < len(token_ids) else "N/A"
            total_price += price
            print(f"    {outcome}: ${price:.4f} (token_id: {token_id[:20]}...)")

        print(f"\n  Price Sum: {total_price:.4f} (should be ~1.0)")
        print(f"  Active: {m.get('active')}")
        print(f"  Closed: {m.get('closed')}")
        print(f"  Accepting Orders: {m.get('acceptingOrders')}")


def verify_token_prices(events: list):
    """Verify token prices sum to ~1.0 across multiple markets."""
    print("\n" + "=" * 60)
    print("Token Price Verification (from Gamma API)")
    print("=" * 60)

    verified = 0
    all_valid = True

    for event in events[:20]:  # Check first 20 events
        markets = event.get("markets", [])
        for m in markets[:3]:  # Check up to 3 markets per event
            prices_str = m.get("outcomePrices", "[]")
            if isinstance(prices_str, str):
                prices = json.loads(prices_str)
            else:
                prices = prices_str

            if not prices:
                continue

            total = sum(float(p) for p in prices)
            question = m.get("question", "N/A")[:45]
            status = "✓" if 0.95 <= total <= 1.05 else "✗"

            if status == "✗":
                all_valid = False

            print(f"  {status} {question}... (sum: {total:.4f})")
            verified += 1

            if verified >= 10:
                break
        if verified >= 10:
            break

    print(f"\n  Verified {verified} markets, all prices sum to ~1.0: {all_valid}")
    return all_valid


def save_examples(binary, sports, multi):
    """Save market type examples to JSON files."""
    print("\n" + "=" * 60)
    print("Saving Examples")
    print("=" * 60)

    EXAMPLES_DIR.mkdir(parents=True, exist_ok=True)

    if binary:
        path = EXAMPLES_DIR / "binary_market_example.json"
        with open(path, "w") as f:
            json.dump(binary, f, indent=2, default=str)
        print(f"  Saved binary market to {path}")

    if sports:
        path = EXAMPLES_DIR / "sports_market_example.json"
        with open(path, "w") as f:
            json.dump(sports, f, indent=2, default=str)
        print(f"  Saved sports market to {path}")

    if multi:
        path = EXAMPLES_DIR / "multi_outcome_example.json"
        with open(path, "w") as f:
            json.dump(multi, f, indent=2, default=str)
        print(f"  Saved multi-outcome market to {path}")


def print_id_summary():
    """Print summary of ID types and their purposes."""
    print("\n" + "=" * 60)
    print("ID Field Summary")
    print("=" * 60)

    print(
        """
┌─────────────────┬────────────────────────────────────────────────────────┐
│ Field           │ Purpose                                                │
├─────────────────┼────────────────────────────────────────────────────────┤
│ event.id        │ Gamma API event identifier (numeric string)            │
│ market.id       │ Gamma API market identifier (numeric string)           │
│ condition_id    │ Unique market identifier for CLOB (hex, 0x-prefixed)   │
│ question_id     │ Market question reference (hex, 0x-prefixed)           │
│ token_id        │ Outcome token for trading (large decimal number)       │
└─────────────────┴────────────────────────────────────────────────────────┘

Hierarchy:
  Event (Gamma)
    └── Markets[] (condition_id links to CLOB)
          └── Tokens[] (token_id used for order placement)

Token Pricing:
  - Each market has 2+ tokens (one per outcome)
  - Prices represent probability (0.0 to 1.0)
  - Prices should sum to ~1.0 (may vary slightly due to spread)
  - winner=true set after market resolution
"""
    )


def main():
    """Main entry point."""
    print("Polymarket Data Structure Analysis")
    print("===================================\n")

    # Fetch examples of different market types
    binary, sports, multi = fetch_market_types()

    # Analyze each market type
    if binary:
        analyze_market_structure(binary, "Binary (Yes/No)")
    if sports:
        analyze_market_structure(sports, "Sports (Team vs Team)")
    if multi:
        analyze_market_structure(multi, "Multi-Market Event")

    # Verify token prices using fetched events
    with httpx.Client() as client:
        resp = client.get(
            f"{GAMMA_HOST}/events",
            params={"active": "true", "closed": "false", "limit": 30},
        )
        all_events = resp.json()
        verify_token_prices(all_events)

    # Save examples
    save_examples(binary, sports, multi)

    # Print ID summary
    print_id_summary()

    print("\n" + "=" * 60)
    print("DONE - Structure analysis complete")
    print("=" * 60)


if __name__ == "__main__":
    main()
