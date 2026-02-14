"""Configuration management for Polydrop."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


# Load .env file if present
load_dotenv()


@dataclass
class MarketFilterConfig:
    """Thresholds for filtering effective markets."""

    min_liquidity: float = 10_000  # USD
    max_spread: float = 0.10  # 10 cents
    min_volume_24h: float = 100  # USD
    min_price: float = 0.05  # Exclude extreme odds < 5%
    max_price: float = 0.95  # Exclude extreme odds > 95%


@dataclass
class WebSocketConfig:
    """WebSocket connection settings."""

    endpoint: str = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
    heartbeat_interval: int = 10  # seconds
    max_tokens_per_connection: int = 500
    reconnect_delay: int = 5  # seconds


@dataclass
class MonitoringConfig:
    """Price monitoring settings."""

    window_seconds: int = 60  # Rolling window duration
    max_data_points: int = 100  # Max observations per window
    log_interval_seconds: int = 30  # How often to log stats


@dataclass
class AlertConfig:
    """Alert detection settings."""

    threshold_pct: float = 5.0  # % change to trigger alert
    cooldown_seconds: int = 300  # 5 min between alerts per token
    min_observations: int = 3  # Min data points before alerting
    cutoff_before_start_seconds: int = 180  # Skip events starting within 3 min


@dataclass
class RedisConfig:
    """Redis connection settings for web UI data bridge."""

    url: str = "redis://localhost:6379/0"
    prefix: str = "polydrop"
    token_ttl: int = 1800  # 30 min default


@dataclass
class ApiConfig:
    """FastAPI SSE server settings."""

    host: str = "0.0.0.0"
    port: int = 3565
    sse_interval: float = 1.0  # seconds between SSE pushes


@dataclass
class Config:
    """Main application configuration."""

    # Database
    db_path: Path = field(default_factory=lambda: Path("data/polydrop.db"))

    # Sports to monitor (comma-separated in env, or "all" for all sports)
    sports: list[str] = field(default_factory=lambda: ["nfl", "nba", "nhl"])
    monitor_all_sports: bool = False

    # Filter settings
    filter: MarketFilterConfig = field(default_factory=MarketFilterConfig)

    # WebSocket settings
    websocket: WebSocketConfig = field(default_factory=WebSocketConfig)

    # Monitoring settings
    monitoring: MonitoringConfig = field(default_factory=MonitoringConfig)

    # Alert settings
    alert: AlertConfig = field(default_factory=AlertConfig)

    # Redis settings
    redis: RedisConfig = field(default_factory=RedisConfig)

    # API server settings
    api: ApiConfig = field(default_factory=ApiConfig)

    # Market refresh interval (seconds, 0 to disable)
    refresh_interval_seconds: int = 7200  # 2 hours

    # Logging
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables."""
        # Parse sports list - "all" means monitor all sports (default)
        sports_str = os.getenv("POLYDROP_SPORTS", "all")
        monitor_all_sports = sports_str.strip().lower() == "all"
        if monitor_all_sports:
            sports = []  # Empty when using all sports mode
        else:
            sports = [s.strip().lower() for s in sports_str.split(",") if s.strip()]

        # Parse filter settings
        filter_config = MarketFilterConfig(
            min_liquidity=float(os.getenv("POLYDROP_MIN_LIQUIDITY", "10000")),
            max_spread=float(os.getenv("POLYDROP_MAX_SPREAD", "0.10")),
            min_volume_24h=float(os.getenv("POLYDROP_MIN_VOLUME_24H", "100")),
            min_price=float(os.getenv("POLYDROP_MIN_PRICE", "0.20")),
            max_price=float(os.getenv("POLYDROP_MAX_PRICE", "0.90")),
        )

        # Parse monitoring settings
        monitoring_config = MonitoringConfig(
            window_seconds=int(os.getenv("POLYDROP_WINDOW_SECONDS", "60")),
            max_data_points=int(os.getenv("POLYDROP_MAX_DATA_POINTS", "100")),
            log_interval_seconds=int(os.getenv("POLYDROP_LOG_INTERVAL_SECONDS", "30")),
        )

        # Parse alert settings
        alert_config = AlertConfig(
            threshold_pct=float(os.getenv("POLYDROP_ALERT_THRESHOLD_PCT", "7.0")),
            cooldown_seconds=int(os.getenv("POLYDROP_ALERT_COOLDOWN_SECONDS", "300")),
            min_observations=int(os.getenv("POLYDROP_ALERT_MIN_OBSERVATIONS", "3")),
            cutoff_before_start_seconds=int(
                os.getenv("POLYDROP_ALERT_CUTOFF_BEFORE_START", "180")
            ),
        )

        # Parse Redis settings
        redis_config = RedisConfig(
            url=os.getenv("POLYDROP_REDIS_URL", "redis://localhost:6379/0"),
            prefix=os.getenv("POLYDROP_REDIS_PREFIX", "polydrop"),
            token_ttl=int(os.getenv("POLYDROP_REDIS_TOKEN_TTL", "1800")),
        )

        # Parse API settings
        api_config = ApiConfig(
            host=os.getenv("POLYDROP_API_HOST", "0.0.0.0"),
            port=int(os.getenv("POLYDROP_API_PORT", "3565")),
            sse_interval=float(os.getenv("POLYDROP_SSE_INTERVAL", "1.0")),
        )

        return cls(
            db_path=Path(os.getenv("POLYDROP_DB_PATH", "data/polydrop.db")),
            sports=sports,
            monitor_all_sports=monitor_all_sports,
            filter=filter_config,
            websocket=WebSocketConfig(),  # Use defaults for now
            monitoring=monitoring_config,
            alert=alert_config,
            redis=redis_config,
            api=api_config,
            refresh_interval_seconds=int(
                os.getenv("POLYDROP_REFRESH_INTERVAL_SECONDS", "7200")
            ),
            log_level=os.getenv("POLYDROP_LOG_LEVEL", "INFO"),
        )


# Sport tag IDs for Gamma API
SPORT_TAGS: dict[str, int] = {
    "nfl": 450,
    "nba": 745,
    "nhl": 899,
    "mlb": 100381,
    "ncaab": 100149,
}

# Gamma API base URL
GAMMA_HOST = "https://gamma-api.polymarket.com"
