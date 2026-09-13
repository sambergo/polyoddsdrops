import asyncio
from pathlib import Path

from main import Polydrop
from src.config import (
    AlertConfig,
    ApiConfig,
    Config,
    MarketFilterConfig,
    MonitoringConfig,
    RedisConfig,
    WebSocketConfig,
)
from src.db.models import MarketRow
from src.websocket.messages import TopOfBookMessage


class RecordingPublisher:
    def __init__(self) -> None:
        self.batches = []

    async def publish_token_states(self, updates) -> None:
        self.batches.append(updates)


def make_config(db_path: Path) -> Config:
    return Config(
        db_path=db_path,
        sports=[],
        monitor_all_sports=True,
        filter=MarketFilterConfig(0, 0.10, 0, 0, 1),
        websocket=WebSocketConfig("wss://example.test", 10, 500, 5),
        monitoring=MonitoringConfig(600, 100, 60, 0.5),
        alert=AlertConfig(7, 300, 99, 180),
        redis=RedisConfig("redis://example.test", "test", 1800),
        api=ApiConfig("127.0.0.1", 3565, 2.0),
        refresh_interval_seconds=0,
        log_level="INFO",
    )


def test_batch_keeps_latest_update_for_each_token(tmp_path: Path) -> None:
    async def scenario() -> None:
        app = Polydrop(make_config(tmp_path / "test.db"))
        publisher = RecordingPublisher()
        app.redis_publisher = publisher  # type: ignore[assignment]
        app._market_cache = {
            "a": MarketRow("a", "c-a", "A?", "Yes"),
            "b": MarketRow("b", "c-b", "B?", "Yes"),
        }

        await app.on_message(TopOfBookMessage("a", "m", 1, 0.40, 0.50))
        await app.on_message(TopOfBookMessage("a", "m", 2, 0.50, 0.60))
        await app.on_message(TopOfBookMessage("b", "m", 2, 0.20, 0.30))
        await app._flush_pending_updates()

        assert len(publisher.batches) == 1
        updates = {update.token_id: update for update in publisher.batches[0]}
        assert set(updates) == {"a", "b"}
        assert updates["a"].mid_price == 0.55
        assert app.price_tracker.total_update_count == 2
        assert app._pending_updates == {}
        await app.clob.close()

    asyncio.run(scenario())
