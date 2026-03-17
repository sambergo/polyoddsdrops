"""SQLite database operations for Polydrop."""

import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from .models import AlertRow, MarketRow

logger = logging.getLogger(__name__)


SCHEMA = """
-- markets: token metadata (no price history)
CREATE TABLE IF NOT EXISTS markets (
    token_id TEXT PRIMARY KEY,
    condition_id TEXT NOT NULL,
    question TEXT NOT NULL,
    outcome TEXT NOT NULL,
    event_title TEXT,
    sport TEXT,
    league_label TEXT,
    sport_label TEXT,
    market_type TEXT,
    line REAL,
    liquidity REAL,
    spread REAL,
    volume_24h REAL,
    is_subscribed INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    priority INTEGER DEFAULT 0,
    game_start_time TEXT,
    event_slug TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- alerts: notification history (for dedup)
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_id TEXT NOT NULL,
    alert_type TEXT NOT NULL,
    old_price REAL NOT NULL,
    new_price REAL NOT NULL,
    price_change_pct REAL NOT NULL,
    time_window_seconds INTEGER NOT NULL,
    detected_at TEXT NOT NULL
);

-- Index for alert deduplication queries
CREATE INDEX IF NOT EXISTS idx_alerts_token_detected
    ON alerts(token_id, detected_at);

-- page_visits: UI load tracking for usage analytics
CREATE TABLE IF NOT EXISTS page_visits (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    ts       TEXT NOT NULL,
    ip_hash  TEXT NOT NULL,
    path     TEXT NOT NULL DEFAULT '/'
);
CREATE INDEX IF NOT EXISTS idx_pv_ts ON page_visits(ts);
"""


class Database:
    """SQLite database manager for Polydrop."""

    def __init__(self, db_path: Path) -> None:
        """Initialize database connection."""
        self.db_path = db_path
        self._conn: sqlite3.Connection | None = None

    def connect(self) -> None:
        """Connect to the database and initialize schema."""
        # Ensure parent directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def close(self) -> None:
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def _init_schema(self) -> None:
        """Initialize database schema."""
        if not self._conn:
            raise RuntimeError("Database not connected")
        self._conn.executescript(SCHEMA)

        # Migrate: add new columns if they don't exist
        cursor = self._conn.execute("PRAGMA table_info(markets)")
        existing_columns = {row[1] for row in cursor.fetchall()}

        migrations = [
            ("league_label", "TEXT"),
            ("sport_label", "TEXT"),
            ("market_type", "TEXT"),
            ("line", "REAL"),
            ("event_slug", "TEXT"),
        ]

        for col_name, col_type in migrations:
            if col_name not in existing_columns:
                self._conn.execute(
                    f"ALTER TABLE markets ADD COLUMN {col_name} {col_type}"
                )
                logger.info(f"Added column {col_name} to markets table")

        self._conn.commit()
        self.prune_old_visits()

    @property
    def conn(self) -> sqlite3.Connection:
        """Get active connection, raising if not connected."""
        if not self._conn:
            raise RuntimeError("Database not connected")
        return self._conn

    # Market operations

    def upsert_market(self, market: MarketRow) -> None:
        """Insert or update a market."""
        self.conn.execute(
            """
            INSERT INTO markets (
                token_id, condition_id, question, outcome, event_title,
                sport, league_label, sport_label, market_type, line,
                liquidity, spread, volume_24h, is_subscribed,
                is_active, priority, game_start_time, event_slug, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(token_id) DO UPDATE SET
                condition_id = excluded.condition_id,
                question = excluded.question,
                outcome = excluded.outcome,
                event_title = excluded.event_title,
                sport = excluded.sport,
                league_label = excluded.league_label,
                sport_label = excluded.sport_label,
                market_type = excluded.market_type,
                line = excluded.line,
                liquidity = excluded.liquidity,
                spread = excluded.spread,
                volume_24h = excluded.volume_24h,
                is_subscribed = excluded.is_subscribed,
                is_active = excluded.is_active,
                priority = excluded.priority,
                game_start_time = excluded.game_start_time,
                event_slug = excluded.event_slug,
                updated_at = datetime('now')
            """,
            (
                market.token_id,
                market.condition_id,
                market.question,
                market.outcome,
                market.event_title,
                market.sport,
                market.league_label,
                market.sport_label,
                market.market_type,
                market.line,
                market.liquidity,
                market.spread,
                market.volume_24h,
                1 if market.is_subscribed else 0,
                1 if market.is_active else 0,
                market.priority,
                market.game_start_time,
                market.event_slug,
            ),
        )
        self.conn.commit()

    def upsert_markets(self, markets: list[MarketRow]) -> None:
        """Bulk insert or update markets."""
        for market in markets:
            self.upsert_market(market)

    def get_market(self, token_id: str) -> MarketRow | None:
        """Get a market by token ID."""
        row = self.conn.execute(
            "SELECT * FROM markets WHERE token_id = ?", (token_id,)
        ).fetchone()
        if not row:
            return None
        return self._row_to_market(row)

    def get_subscribed_markets(self) -> list[MarketRow]:
        """Get all markets marked as subscribed."""
        rows = self.conn.execute(
            "SELECT * FROM markets WHERE is_subscribed = 1 AND is_active = 1"
        ).fetchall()
        return [self._row_to_market(row) for row in rows]

    def get_active_markets(self) -> list[MarketRow]:
        """Get all active markets."""
        rows = self.conn.execute("SELECT * FROM markets WHERE is_active = 1").fetchall()
        return [self._row_to_market(row) for row in rows]

    def set_subscribed(self, token_ids: list[str], subscribed: bool = True) -> None:
        """Mark tokens as subscribed/unsubscribed."""
        if not token_ids:
            return
        placeholders = ",".join("?" * len(token_ids))
        self.conn.execute(
            f"UPDATE markets SET is_subscribed = ? WHERE token_id IN ({placeholders})",
            [1 if subscribed else 0, *token_ids],
        )
        self.conn.commit()

    def get_market_count(self) -> int:
        """Get total number of markets."""
        row = self.conn.execute("SELECT COUNT(*) FROM markets").fetchone()
        return row[0] if row else 0

    def _row_to_market(self, row: sqlite3.Row) -> MarketRow:
        """Convert database row to MarketRow."""
        return MarketRow(
            token_id=row["token_id"],
            condition_id=row["condition_id"],
            question=row["question"],
            outcome=row["outcome"],
            event_title=row["event_title"],
            sport=row["sport"],
            league_label=row["league_label"],
            sport_label=row["sport_label"],
            market_type=row["market_type"],
            line=row["line"],
            liquidity=row["liquidity"],
            spread=row["spread"],
            volume_24h=row["volume_24h"],
            is_subscribed=bool(row["is_subscribed"]),
            is_active=bool(row["is_active"]),
            priority=row["priority"],
            game_start_time=row["game_start_time"],
            event_slug=row["event_slug"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    # Alert operations

    def insert_alert(self, alert: AlertRow) -> int:
        """Insert an alert and return its ID."""
        logger.debug(f"Inserting alert for token {alert.token_id[:20]}...")
        cursor = self.conn.execute(
            """
            INSERT INTO alerts (
                token_id, alert_type, old_price, new_price,
                price_change_pct, time_window_seconds, detected_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                alert.token_id,
                alert.alert_type,
                alert.old_price,
                alert.new_price,
                alert.price_change_pct,
                alert.time_window_seconds,
                alert.detected_at,
            ),
        )
        self.conn.commit()
        result = cursor.lastrowid or 0
        logger.debug(f"Alert inserted with id={result}")
        return result

    def get_recent_alerts(self, token_id: str, seconds: int = 300) -> list[AlertRow]:
        """Get recent alerts for a token within the specified time window."""
        cutoff = (datetime.utcnow() - timedelta(seconds=seconds)).isoformat()
        rows = self.conn.execute(
            """
            SELECT id, token_id, alert_type, old_price, new_price,
                   price_change_pct, time_window_seconds, detected_at
            FROM alerts
            WHERE token_id = ? AND detected_at > ?
            ORDER BY detected_at DESC
            """,
            (token_id, cutoff),
        ).fetchall()
        return [self._row_to_alert(row) for row in rows]

    def _row_to_alert(self, row: sqlite3.Row) -> AlertRow:
        """Convert database row to AlertRow."""
        return AlertRow(
            id=row["id"],
            token_id=row["token_id"],
            alert_type=row["alert_type"],
            old_price=row["old_price"],
            new_price=row["new_price"],
            price_change_pct=row["price_change_pct"],
            time_window_seconds=row["time_window_seconds"],
            detected_at=row["detected_at"],
        )

    # Analytics operations

    def log_visit(self, ip_hash: str, path: str) -> None:
        """Record a page visit."""
        self.conn.execute(
            "INSERT INTO page_visits (ts, ip_hash, path) VALUES (datetime('now'), ?, ?)",
            (ip_hash, path),
        )
        self.conn.commit()

    def get_daily_stats(self, days: int = 30) -> list[dict]:
        """Return daily hit counts and unique visitor counts."""
        rows = self.conn.execute(
            f"""
            SELECT substr(ts, 1, 10) AS date,
                   COUNT(*) AS hits,
                   COUNT(DISTINCT ip_hash) AS unique_visitors
            FROM page_visits
            WHERE ts >= datetime('now', '-{days} days')
            GROUP BY date ORDER BY date DESC
            """
        ).fetchall()
        return [{"date": r["date"], "hits": r["hits"], "unique_visitors": r["unique_visitors"]} for r in rows]

    def prune_old_visits(self, days: int = 90) -> None:
        """Delete page visit records older than N days."""
        self.conn.execute(
            f"DELETE FROM page_visits WHERE ts < datetime('now', '-{days} days')"
        )
        self.conn.commit()
