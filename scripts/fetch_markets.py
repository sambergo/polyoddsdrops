#!/usr/bin/env python3
"""Fetch and explore Polymarket data structures.

This script fetches markets from the Polymarket CLOB API and Gamma API
to understand the data structure for building our arbitrage system.
"""

import json
from pathlib import Path

import httpx
from py_clob_client.client import ClobClient

CLOB_HOST = "https://clob.polymarket.com"
GAMMA_HOST = "https://gamma-api.polymarket.com"
EXAMPLES_DIR = Path(__file__).parent.parent / "docs" / "examples"


def fetch_clob_markets():
    """Fetch markets from the CLOB API."""
    print("=" * 60)
    print("CLOB API - Markets")
    print("=" * 60)

    client = ClobClient(CLOB_HOST)

    # Fetch full markets
    print("\nFetching markets (full detail)...")
    markets_response = client.get_markets()
    print(f"Response type: {type(markets_response)}")

    if isinstance(markets_response, dict):
        print(f"Response keys: {list(markets_response.keys())}")
        markets = markets_response.get("data", markets_response)
    else:
        markets = markets_response

    if isinstance(markets, list) and len(markets) > 0:
        print(f"Total markets: {len(markets)}")
        sample = markets[0]
        print(f"\nSample market keys: {list(sample.keys())}")

        # Save sample
        EXAMPLES_DIR.mkdir(parents=True, exist_ok=True)
        with open(EXAMPLES_DIR / "market_sample.json", "w") as f:
            json.dump(sample, f, indent=2, default=str)
        print(f"Saved sample to {EXAMPLES_DIR / 'market_sample.json'}")

    # Fetch simplified markets
    print("\n" + "-" * 40)
    print("Fetching simplified markets...")
    simplified_response = client.get_simplified_markets()
    print(f"Response type: {type(simplified_response)}")

    if isinstance(simplified_response, dict):
        print(f"Response keys: {list(simplified_response.keys())}")
        simplified = simplified_response.get("data", simplified_response)
    else:
        simplified = simplified_response

    if isinstance(simplified, list) and len(simplified) > 0:
        print(f"Total simplified markets: {len(simplified)}")
        sample = simplified[0]
        print(f"\nSimplified market keys: {list(sample.keys())}")

        with open(EXAMPLES_DIR / "simplified_market_sample.json", "w") as f:
            json.dump(sample, f, indent=2, default=str)
        print(f"Saved sample to {EXAMPLES_DIR / 'simplified_market_sample.json'}")

    # Save summary
    summary = {
        "full_markets_count": len(markets) if isinstance(markets, list) else 0,
        "simplified_markets_count": len(simplified)
        if isinstance(simplified, list)
        else 0,
        "full_market_fields": list(markets[0].keys())
        if isinstance(markets, list) and markets
        else [],
        "simplified_market_fields": list(simplified[0].keys())
        if isinstance(simplified, list) and simplified
        else [],
    }
    with open(EXAMPLES_DIR / "markets_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nSaved summary to {EXAMPLES_DIR / 'markets_summary.json'}")

    return markets, simplified


def fetch_gamma_data():
    """Fetch data from the Gamma API (sports, tags, events)."""
    print("\n" + "=" * 60)
    print("GAMMA API - Categories & Sports")
    print("=" * 60)

    with httpx.Client() as client:
        # Fetch sports
        print("\nFetching sports...")
        try:
            resp = client.get(f"{GAMMA_HOST}/sports")
            resp.raise_for_status()
            sports = resp.json()
            print(f"Sports response type: {type(sports)}")
            if isinstance(sports, list):
                print(f"Total sports: {len(sports)}")
                if sports:
                    print(
                        f"Sample sport keys: {list(sports[0].keys()) if isinstance(sports[0], dict) else 'N/A'}"
                    )
            with open(EXAMPLES_DIR / "sports.json", "w") as f:
                json.dump(sports, f, indent=2, default=str)
            print(f"Saved to {EXAMPLES_DIR / 'sports.json'}")
        except Exception as e:
            print(f"Error fetching sports: {e}")

        # Fetch tags
        print("\n" + "-" * 40)
        print("Fetching tags...")
        try:
            resp = client.get(f"{GAMMA_HOST}/tags", params={"limit": 100})
            resp.raise_for_status()
            tags = resp.json()
            print(f"Tags response type: {type(tags)}")
            if isinstance(tags, list):
                print(f"Total tags: {len(tags)}")
                if tags:
                    print(f"Sample tag: {tags[0]}")
            with open(EXAMPLES_DIR / "tags.json", "w") as f:
                json.dump(tags, f, indent=2, default=str)
            print(f"Saved to {EXAMPLES_DIR / 'tags.json'}")
        except Exception as e:
            print(f"Error fetching tags: {e}")

        # Fetch active events
        print("\n" + "-" * 40)
        print("Fetching active events...")
        try:
            resp = client.get(
                f"{GAMMA_HOST}/events",
                params={"active": "true", "closed": "false", "limit": 10},
            )
            resp.raise_for_status()
            events = resp.json()
            print(f"Events response type: {type(events)}")
            if isinstance(events, list):
                print(f"Events fetched (limit 10): {len(events)}")
                if events:
                    print(
                        f"Sample event keys: {list(events[0].keys()) if isinstance(events[0], dict) else 'N/A'}"
                    )
            with open(EXAMPLES_DIR / "events_sample.json", "w") as f:
                json.dump(events, f, indent=2, default=str)
            print(f"Saved to {EXAMPLES_DIR / 'events_sample.json'}")
        except Exception as e:
            print(f"Error fetching events: {e}")


def main():
    """Main entry point."""
    print("Polymarket Data Explorer")
    print("========================\n")

    EXAMPLES_DIR.mkdir(parents=True, exist_ok=True)

    markets, simplified = fetch_clob_markets()
    fetch_gamma_data()

    print("\n" + "=" * 60)
    print("DONE - Check docs/examples/ for saved JSON samples")
    print("=" * 60)


if __name__ == "__main__":
    main()
