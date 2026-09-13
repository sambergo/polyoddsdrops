import asyncio
import json

from src.config import RedisConfig
from src.db.models import MarketRow
from src.redis.publisher import RedisPublisher, TokenUpdate


class FakePipeline:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def hset(self, key, mapping):
        self.calls.append(("hset", key, mapping))
        return self

    def hget(self, key, field):
        self.calls.append(("hget", key, field))
        return self

    def publish(self, channel, payload):
        self.calls.append(("publish", channel, payload))
        return self

    def persist(self, key):
        self.calls.append(("persist", key))
        return self

    def sadd(self, key, *values):
        self.calls.append(("sadd", key, values))
        return self

    def srem(self, key, *values):
        self.calls.append(("srem", key, values))
        return self

    def delete(self, key):
        self.calls.append(("delete", key))
        return self

    async def execute(self):
        return []


class FakeRedis:
    def __init__(self) -> None:
        self.pipelines: list[FakePipeline] = []

    def pipeline(self, transaction=False):
        pipeline = FakePipeline()
        self.pipelines.append(pipeline)
        return pipeline

    async def smembers(self, key):
        return {"stale-token"}


def make_update(token_id: str) -> TokenUpdate:
    return TokenUpdate(
        token_id=token_id,
        market=MarketRow(token_id, "condition", "Question?", "Yes"),
        mid_price=0.5,
        best_bid=0.49,
        best_ask=0.51,
        velocity=None,
        live_spread=0.02,
    )


def test_batches_hash_writes_and_publishes_compact_deltas() -> None:
    async def scenario() -> None:
        publisher = RedisPublisher(RedisConfig("redis://test", "poly", 1800))
        client = FakeRedis()
        publisher._client = client  # type: ignore[assignment]
        publisher._available = True

        await publisher.publish_token_states([make_update("a"), make_update("b")])
        first_calls = client.pipelines[0].calls
        assert [call[0] for call in first_calls] == [
            "hset",
            "persist",
            "hset",
            "persist",
            "publish",
        ]
        first_payload = json.loads(first_calls[-1][2])
        assert first_payload["updated"][0]["question"] == "Question?"

        await publisher.publish_token_states([make_update("a")])
        second_payload = json.loads(client.pipelines[1].calls[-1][2])
        assert "question" not in second_payload["updated"][0]
        assert second_payload["updated"][0]["mid_price"] == "0.5"

        await publisher.sync_tokens(["a", "b"])
        sync_calls = client.pipelines[2].calls
        assert ("delete", "poly:token:stale-token") in sync_calls
        assert any(call[0] == "sadd" for call in sync_calls)

    asyncio.run(scenario())
