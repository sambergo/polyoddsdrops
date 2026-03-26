"""In-process SSE broadcaster — one background poller, N queue subscribers."""

import asyncio
import logging

logger = logging.getLogger(__name__)
_QUEUE_MAX = 32


class Broadcaster:
    def __init__(self) -> None:
        self._queues: set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=_QUEUE_MAX)
        self._queues.add(q)
        logger.debug("SSE client subscribed (total=%d)", len(self._queues))
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._queues.discard(q)
        logger.debug("SSE client unsubscribed (total=%d)", len(self._queues))

    def broadcast(self, event: str, data: str) -> None:
        """put_nowait to all queues; drop event for full/stalled queues."""
        message = {"event": event, "data": data}
        dead: list[asyncio.Queue] = []
        for q in self._queues:
            try:
                q.put_nowait(message)
            except asyncio.QueueFull:
                logger.debug("SSE queue full, dropping event for one client")
            except Exception:
                dead.append(q)
        for q in dead:
            self._queues.discard(q)

    @property
    def subscriber_count(self) -> int:
        return len(self._queues)
