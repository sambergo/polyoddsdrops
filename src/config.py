"""Configuration management for Polydrop."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


# Load .env file if present
load_dotenv()


def _require(name: str) -> str:
    """Get a required environment variable or raise."""
    value = os.getenv(name)
    if value is None:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


@dataclass
class MarketFilterConfig:
    """Thresholds for filtering effective markets."""

    min_liquidity: float
    max_spread: float
    min_volume_24h: float
    min_price: float
    max_price: float


@dataclass
class WebSocketConfig:
    """WebSocket connection settings."""

    endpoint: str
    heartbeat_interval: int
    max_tokens_per_connection: int
    reconnect_delay: int


@dataclass
class MonitoringConfig:
    """Price monitoring settings."""

    window_seconds: int
    max_data_points: int
    log_interval_seconds: int


@dataclass
class AlertConfig:
    """Alert detection settings."""

    threshold_pct: float
    cooldown_seconds: int
    min_observations: int
    cutoff_before_start_seconds: int


@dataclass
class RedisConfig:
    """Redis connection settings for web UI data bridge."""

    url: str
    prefix: str
    token_ttl: int


@dataclass
class ApiConfig:
    """FastAPI SSE server settings."""

    host: str
    port: int
    sse_interval: float


@dataclass
class Config:
    """Main application configuration."""

    db_path: Path
    sports: list[str]
    monitor_all_sports: bool
    filter: MarketFilterConfig
    websocket: WebSocketConfig
    monitoring: MonitoringConfig
    alert: AlertConfig
    redis: RedisConfig
    api: ApiConfig
    refresh_interval_seconds: int
    log_level: str

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables."""
        sports_str = _require("POLYDROP_SPORTS")
        monitor_all_sports = sports_str.strip().lower() == "all"
        if monitor_all_sports:
            sports = []
        else:
            sports = [s.strip().lower() for s in sports_str.split(",") if s.strip()]

        filter_config = MarketFilterConfig(
            min_liquidity=float(_require("POLYDROP_MIN_LIQUIDITY")),
            max_spread=float(_require("POLYDROP_MAX_SPREAD")),
            min_volume_24h=float(_require("POLYDROP_MIN_VOLUME_24H")),
            min_price=float(_require("POLYDROP_MIN_PRICE")),
            max_price=float(_require("POLYDROP_MAX_PRICE")),
        )

        websocket_config = WebSocketConfig(
            endpoint=_require("POLYDROP_WS_ENDPOINT"),
            heartbeat_interval=int(_require("POLYDROP_WS_HEARTBEAT_INTERVAL")),
            max_tokens_per_connection=int(_require("POLYDROP_WS_MAX_TOKENS_PER_CONNECTION")),
            reconnect_delay=int(_require("POLYDROP_WS_RECONNECT_DELAY")),
        )

        monitoring_config = MonitoringConfig(
            window_seconds=int(_require("POLYDROP_WINDOW_SECONDS")),
            max_data_points=int(_require("POLYDROP_MAX_DATA_POINTS")),
            log_interval_seconds=int(_require("POLYDROP_LOG_INTERVAL_SECONDS")),
        )

        alert_config = AlertConfig(
            threshold_pct=float(_require("POLYDROP_ALERT_THRESHOLD_PCT")),
            cooldown_seconds=int(_require("POLYDROP_ALERT_COOLDOWN_SECONDS")),
            min_observations=int(_require("POLYDROP_ALERT_MIN_OBSERVATIONS")),
            cutoff_before_start_seconds=int(_require("POLYDROP_ALERT_CUTOFF_BEFORE_START")),
        )

        redis_config = RedisConfig(
            url=_require("POLYDROP_REDIS_URL"),
            prefix=_require("POLYDROP_REDIS_PREFIX"),
            token_ttl=int(_require("POLYDROP_REDIS_TOKEN_TTL")),
        )

        api_config = ApiConfig(
            host=_require("POLYDROP_API_HOST"),
            port=int(_require("POLYDROP_API_PORT")),
            sse_interval=float(_require("POLYDROP_SSE_INTERVAL")),
        )

        return cls(
            db_path=Path(_require("POLYDROP_DB_PATH")),
            sports=sports,
            monitor_all_sports=monitor_all_sports,
            filter=filter_config,
            websocket=websocket_config,
            monitoring=monitoring_config,
            alert=alert_config,
            redis=redis_config,
            api=api_config,
            refresh_interval_seconds=int(_require("POLYDROP_REFRESH_INTERVAL_SECONDS")),
            log_level=_require("POLYDROP_LOG_LEVEL"),
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
