#!/usr/bin/env python3
"""List all sports available on Polymarket.

A verification script to discover all sports and their tag IDs,
helping identify which sports to add to the main app configuration.

Usage:
    uv run scripts/list_all_sports.py                  # Quick list
    uv run scripts/list_all_sports.py --fetch-counts   # With event counts
    uv run scripts/list_all_sports.py --fetch-counts --save  # Save to JSON
"""

import argparse
import json
import sys
from pathlib import Path

import httpx

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import GAMMA_HOST, SPORT_TAGS

EXAMPLES_DIR = Path(__file__).parent.parent / "docs" / "examples"

# Sport categories for organized display
SPORT_CATEGORIES: dict[str, list[str]] = {
    "US Major Sports": ["nfl", "nba", "nhl", "mlb", "ncaab", "cfb", "wnba", "mls"],
    "Soccer - European": [
        "epl",
        "lal",
        "bun",
        "sra",
        "lig",
        "ucl",
        "uel",
        "uec",
        "efl",
        "fac",
        "efc",
        "usc",
    ],
    "Soccer - International": [
        "fifa",
        "euq",
        "eur",
        "acn",
        "conm",
        "conq",
        "copa",
        "gold",
        "wcq",
        "wc",
        "cwc",
    ],
    "Soccer - Other Leagues": [
        "bra",
        "arg",
        "mex",
        "sau",
        "aus",
        "jpn",
        "kor",
        "chn",
        "ind",
        "tur",
        "ned",
        "por",
        "bel",
        "sco",
        "gre",
        "rus",
    ],
    "Cricket": ["ipl", "bbl", "psl", "wpl", "cpl", "bpl", "lpl", "ilt", "ict", "cwc"],
    "Tennis": ["atp", "wta", "ao", "fo", "wim", "uso", "dc", "bc", "utr"],
    "Golf": ["pga", "lpga", "dp", "liv", "mc", "ryd"],
    "Combat Sports": ["ufc", "pfl", "box", "wwe", "one"],
    "Motorsport": ["f1", "nas", "ind", "mog", "fia", "wrc"],
    "Esports": [
        "cs",
        "dota",
        "lol",
        "val",
        "ow",
        "cod",
        "rl",
        "fifa",
        "pub",
        "apex",
        "tft",
    ],
    "Other Sports": [],  # Catch-all for uncategorized
}


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
    with httpx.Client(timeout=30) as client:
        resp = client.get(f"{GAMMA_HOST}/sports")
        resp.raise_for_status()
        return resp.json()


def fetch_event_count(tag_id: int) -> int:
    """Fetch active event count for a sport tag."""
    with httpx.Client(timeout=30) as client:
        params = {
            "active": "true",
            "closed": "false",
            "tag_id": str(tag_id),
            "limit": 1000,
        }
        resp = client.get(f"{GAMMA_HOST}/events", params=params)
        resp.raise_for_status()
        events = resp.json()
        return len(events) if isinstance(events, list) else 0


def extract_sport_tag(tags: list[int]) -> int | None:
    """Extract the sport-specific tag ID from tag list.

    Excludes common tags:
    - 1 = "Sports" (parent category)
    - 100639 = likely "active" or common marker
    """
    sport_tags = [t for t in tags if t not in (1, 100639)]
    return sport_tags[0] if sport_tags else None


def get_category_for_sport(code: str) -> str:
    """Get the category for a sport code."""
    code_lower = code.lower()
    for category, sports in SPORT_CATEGORIES.items():
        if code_lower in sports:
            return category
    return "Other Sports"


def is_monitored(code: str) -> bool:
    """Check if a sport is currently monitored."""
    return code.lower() in SPORT_TAGS


def print_header(title: str, width: int = 70):
    """Print a section header."""
    print("=" * width)
    print(title)
    print("=" * width)


def print_table_row(columns: list[str], widths: list[int]):
    """Print a table row with specified column widths."""
    row = "|"
    for col, width in zip(columns, widths):
        row += f" {col:<{width}} |"
    print(row)


def print_table_separator(widths: list[int]):
    """Print a table separator line."""
    sep = "|"
    for width in widths:
        sep += "-" * (width + 2) + "|"
    print(sep)


def main():
    parser = argparse.ArgumentParser(
        description="List all sports available on Polymarket"
    )
    parser.add_argument(
        "--fetch-counts",
        action="store_true",
        help="Fetch active event counts per sport (slower)",
    )
    parser.add_argument(
        "--save", action="store_true", help="Save data to docs/examples/all_sports.json"
    )
    args = parser.parse_args()

    # Fetch all sports
    print("\nFetching sports from Polymarket...")
    sports_data = fetch_sports()
    print(f"Found {len(sports_data)} sports\n")

    # Process sports data
    sports_list: list[dict] = []
    for sport in sports_data:
        code = sport.get("sport", "").lower()
        tags = parse_tags_string(sport.get("tags", ""))
        sport_tag = extract_sport_tag(tags)

        entry = {
            "code": code,
            "tag_id": sport_tag,
            "category": get_category_for_sport(code),
            "monitored": is_monitored(code),
            "resolution": sport.get("resolution", ""),
            "all_tags": tags,
            "events": None,  # Will be populated if --fetch-counts
        }
        sports_list.append(entry)

    # Fetch event counts if requested
    if args.fetch_counts:
        print("Fetching event counts (this may take a moment)...")
        for i, sport in enumerate(sports_list):
            tag_id = sport["tag_id"]
            if tag_id:
                sport["events"] = fetch_event_count(tag_id)
                # Progress indicator
                if (i + 1) % 10 == 0:
                    print(f"  Processed {i + 1}/{len(sports_list)} sports...")
        print()

    # Sort by category then code
    sports_list.sort(key=lambda x: (x["category"], x["code"]))

    # Print summary
    print_header("Polymarket Sports Catalog")
    print()
    print(f"Total Sports: {len(sports_list)}")
    monitored_count = sum(1 for s in sports_list if s["monitored"])
    print(f"Currently Monitored: {monitored_count}")
    print()

    # Print monitored sports first
    print_header("CURRENTLY MONITORED SPORTS")
    print()

    monitored = [s for s in sports_list if s["monitored"]]
    col_widths = [10, 10, 8] if not args.fetch_counts else [10, 10, 8]
    headers = ["Code", "Tag ID", "Events"] if args.fetch_counts else ["Code", "Tag ID"]
    col_widths = [10, 10, 8] if args.fetch_counts else [10, 10]

    print_table_row(headers, col_widths)
    print_table_separator(col_widths)

    for sport in monitored:
        tag_str = str(sport["tag_id"]) if sport["tag_id"] else "N/A"
        if args.fetch_counts:
            events_str = str(sport["events"]) if sport["events"] is not None else "N/A"
            print_table_row([sport["code"].upper(), tag_str, events_str], col_widths)
        else:
            print_table_row([sport["code"].upper(), tag_str], col_widths)
    print()

    # Print by category
    categories_with_sports: dict[str, list[dict]] = {}
    for sport in sports_list:
        cat = sport["category"]
        if cat not in categories_with_sports:
            categories_with_sports[cat] = []
        categories_with_sports[cat].append(sport)

    # Print categories in order, with "Other Sports" last
    category_order = [c for c in SPORT_CATEGORIES if c != "Other Sports"]
    category_order.append("Other Sports")

    for category in category_order:
        if category not in categories_with_sports:
            continue

        cat_sports = categories_with_sports[category]
        print_header(f"{category} ({len(cat_sports)} sports)")
        print()

        if args.fetch_counts:
            col_widths = [12, 10, 8, 12]
            headers = ["Code", "Tag ID", "Events", "Status"]
        else:
            col_widths = [12, 10, 12]
            headers = ["Code", "Tag ID", "Status"]

        print_table_row(headers, col_widths)
        print_table_separator(col_widths)

        for sport in cat_sports:
            tag_str = str(sport["tag_id"]) if sport["tag_id"] else "N/A"
            status = "[MONITORED]" if sport["monitored"] else ""

            if args.fetch_counts:
                events_str = (
                    str(sport["events"]) if sport["events"] is not None else "N/A"
                )
                print_table_row(
                    [sport["code"], tag_str, events_str, status], col_widths
                )
            else:
                print_table_row([sport["code"], tag_str, status], col_widths)
        print()

    # Save to JSON if requested
    if args.save:
        EXAMPLES_DIR.mkdir(parents=True, exist_ok=True)
        output_path = EXAMPLES_DIR / "all_sports.json"
        with open(output_path, "w") as f:
            json.dump(sports_list, f, indent=2)
        print(f"Saved to {output_path}")
        print()

    # Print usage hint
    print_header("USAGE")
    print()
    print("To add a sport to monitoring, update src/config.py SPORT_TAGS:")
    print()
    print("  SPORT_TAGS: dict[str, int] = {")
    print('      "nfl": 450,')
    print('      "nba": 745,')
    print("      # Add new sports here:")
    print('      # "epl": 82,  # English Premier League')
    print("  }")
    print()
    print("Then set POLYDROP_SPORTS env var or update config defaults.")
    print()


if __name__ == "__main__":
    main()
