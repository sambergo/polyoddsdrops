#!/usr/bin/env python3
"""Discover sports markets and their filtering criteria in Polymarket.

This script:
1. Fetches all sports from /sports endpoint
2. Builds sport code → tag ID mapping
3. Queries events for each major sport
4. Saves sample events for NFL/NBA
"""

import json
from pathlib import Path

import httpx

GAMMA_HOST = "https://gamma-api.polymarket.com"
EXAMPLES_DIR = Path(__file__).parent.parent / "docs" / "examples"

# Major US sports to focus on
MAJOR_SPORTS = ["nfl", "nba", "nhl", "mlb", "ncaab"]


def parse_tags_string(tags_str: str) -> list[int]:
    """Parse comma-separated tags string into list of tag IDs."""
    if not tags_str:
        return []
    try:
        return [int(t.strip()) for t in tags_str.split(",") if t.strip().isdigit()]
    except ValueError:
        return []


def fetch_sports() -> list[dict]:
    """Fetch all sports from Gamma API."""
    with httpx.Client() as client:
        resp = client.get(f"{GAMMA_HOST}/sports")
        resp.raise_for_status()
        return resp.json()


def build_sport_tag_mapping(sports: list[dict]) -> dict[str, dict]:
    """Build mapping of sport code to metadata including tag IDs."""
    mapping = {}
    for sport in sports:
        code = sport.get("sport", "").lower()
        tags = parse_tags_string(sport.get("tags", ""))

        # Find the sport-specific tag (not the generic "Sports" tag 1 or common tags)
        # Common tags to exclude: 1 (Sports), 100639 (likely "active" or similar)
        sport_tags = [t for t in tags if t not in (1, 100639)]

        mapping[code] = {
            "id": sport.get("id"),
            "tags": tags,
            "sport_tag": sport_tags[0] if sport_tags else None,
            "all_tags": tags,
            "resolution": sport.get("resolution", ""),
        }
    return mapping


def fetch_events_by_tag(tag_id: int | str, limit: int = 50) -> list[dict]:
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


def count_events_by_tag(tag_id: int | str) -> int:
    """Count active events for a tag (fetch minimal data)."""
    with httpx.Client() as client:
        params = {
            "active": "true",
            "closed": "false",
            "tag_id": str(tag_id),
            "limit": 1000,  # Get count up to 1000
        }
        resp = client.get(f"{GAMMA_HOST}/events", params=params)
        resp.raise_for_status()
        events = resp.json()
        return len(events) if isinstance(events, list) else 0


def collect_unique_tags(events: list[dict]) -> set[str]:
    """Collect all unique tags from a list of events."""
    tags = set()
    for event in events:
        event_tags = event.get("tags", [])
        if isinstance(event_tags, list):
            for tag in event_tags:
                if isinstance(tag, dict):
                    tags.add(tag.get("label", str(tag.get("id", ""))))
                else:
                    tags.add(str(tag))
    return tags


def main():
    """Main entry point."""
    print("=" * 60)
    print("Polymarket Sports Market Discovery")
    print("=" * 60)

    EXAMPLES_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Fetch all sports
    print("\n1. Fetching sports configuration...")
    sports = fetch_sports()
    print(f"   Found {len(sports)} sports configured")

    # 2. Build sport → tag mapping
    print("\n2. Building sport code → tag ID mapping...")
    sport_mapping = build_sport_tag_mapping(sports)

    # Print major sports tags
    print("\n   Major Sports Tag IDs:")
    print("   " + "-" * 40)
    for code in MAJOR_SPORTS:
        if code in sport_mapping:
            info = sport_mapping[code]
            print(f"   {code.upper():8} → tag {info['sport_tag']}")

    # 3. Query events for each major sport
    print("\n3. Querying active events per sport...")
    print("   " + "-" * 40)

    sport_counts = {}
    sport_events = {}

    for code in MAJOR_SPORTS:
        if code not in sport_mapping:
            print(f"   {code.upper():8}: Not configured")
            continue

        tag_id = sport_mapping[code]["sport_tag"]
        if not tag_id:
            print(f"   {code.upper():8}: No sport-specific tag found")
            continue

        # Fetch events
        events = fetch_events_by_tag(tag_id, limit=100)
        count = len(events)
        sport_counts[code] = count
        sport_events[code] = events

        # Count markets
        total_markets = sum(len(e.get("markets", [])) for e in events)

        print(
            f"   {code.upper():8}: {count:3} events, {total_markets:4} markets (tag={tag_id})"
        )

    # 4. Also check "Sports" parent tag
    print("\n4. Checking parent 'Sports' tag (id=1)...")
    sports_tag_events = fetch_events_by_tag(1, limit=100)
    print(f"   Total Sports events (via tag=1): {len(sports_tag_events)}")

    # Collect unique tags from sports events
    all_sports_tags = collect_unique_tags(sports_tag_events)
    print(f"   Unique tags found: {len(all_sports_tags)}")

    # 5. Save NFL events sample
    print("\n5. Saving sample events...")

    if "nfl" in sport_events and sport_events["nfl"]:
        nfl_sample = sport_events["nfl"][:5]  # First 5 events
        with open(EXAMPLES_DIR / "nfl_events_sample.json", "w") as f:
            json.dump(nfl_sample, f, indent=2, default=str)
        print(f"   Saved {len(nfl_sample)} NFL events to nfl_events_sample.json")

    if "nba" in sport_events and sport_events["nba"]:
        nba_sample = sport_events["nba"][:5]  # First 5 events
        with open(EXAMPLES_DIR / "nba_events_sample.json", "w") as f:
            json.dump(nba_sample, f, indent=2, default=str)
        print(f"   Saved {len(nba_sample)} NBA events to nba_events_sample.json")

    # 6. Print summary table
    print("\n" + "=" * 60)
    print("SUMMARY: Sport Filtering Reference")
    print("=" * 60)
    print("\n| Sport | Code | Tag ID | Filter Query |")
    print("|-------|------|--------|--------------|")
    for code in MAJOR_SPORTS:
        if code in sport_mapping:
            tag_id = sport_mapping[code]["sport_tag"]
            if tag_id:
                print(
                    f"| {code.upper():5} | `{code}` | `{tag_id}` | `?tag_id={tag_id}` |"
                )

    print("\n| All Sports | `?tag_id=1` |")

    # 7. Print example events
    print("\n" + "=" * 60)
    print("SAMPLE EVENTS")
    print("=" * 60)

    for code in ["nfl", "nba"]:
        if code in sport_events and sport_events[code]:
            print(f"\n{code.upper()} Events (first 3):")
            print("-" * 40)
            for event in sport_events[code][:3]:
                title = event.get("title", "No title")[:50]
                num_markets = len(event.get("markets", []))
                volume = float(event.get("volume", 0))
                print(f"  • {title}...")
                print(f"    Markets: {num_markets}, Volume: ${volume:,.0f}")

    print("\n" + "=" * 60)
    print("DONE")
    print("=" * 60)


if __name__ == "__main__":
    main()
