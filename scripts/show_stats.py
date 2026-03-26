#!/usr/bin/env python3
"""Show Polydrop page visit stats from SQLite.

Usage:
    uv run scripts/show_stats.py
    uv run scripts/show_stats.py --days 7
    uv run scripts/show_stats.py --db /path/to/polydrop.db
"""

import argparse
import sqlite3
from pathlib import Path


def get_stats(db_path: Path, days: int) -> list[dict]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        f"""
        SELECT substr(ts, 1, 10) AS date,
               COUNT(*) AS hits,
               COUNT(DISTINCT ip_hash) AS unique_visitors
        FROM page_visits
        WHERE ts >= datetime('now', '-{days} days')
        GROUP BY date ORDER BY date DESC
        """
    ).fetchall()
    conn.close()
    return [
        {"date": r["date"], "hits": r["hits"], "unique_visitors": r["unique_visitors"]}
        for r in rows
    ]


def get_alltime(db_path: Path) -> dict:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT COUNT(*) AS hits, COUNT(DISTINCT ip_hash) AS unique_visitors FROM page_visits"
    ).fetchone()
    conn.close()
    return {"hits": row["hits"], "unique_visitors": row["unique_visitors"]}


def main():
    parser = argparse.ArgumentParser(description="Show Polydrop usage stats")
    parser.add_argument(
        "--days", type=int, default=30, help="Number of days to show (default: 30)"
    )
    parser.add_argument(
        "--db", type=Path, default=Path("data/polydrop.db"), help="Path to SQLite DB"
    )
    args = parser.parse_args()

    if not args.db.exists():
        print(f"DB not found: {args.db}")
        return

    rows = get_stats(args.db, args.days)
    alltime = get_alltime(args.db)

    print(f"\nPolydrop Usage Stats (last {args.days} days)")
    print(f"DB: {args.db}\n")

    col1, col2, col3 = 11, 6, 16
    print(f"{'Date':<{col1}}  {'Hits':>{col2}}  {'Unique Visitors':>{col3}}")
    print(f"{'-' * col1}  {'-' * col2}  {'-' * col3}")

    for r in rows:
        print(
            f"{r['date']:<{col1}}  {r['hits']:>{col2}}  {r['unique_visitors']:>{col3}}"
        )

    print(f"{'-' * col1}  {'-' * col2}  {'-' * col3}")
    print(
        f"{'All-time':<{col1}}  {alltime['hits']:>{col2}}  {alltime['unique_visitors']:>{col3}}"
    )
    print()


if __name__ == "__main__":
    main()
