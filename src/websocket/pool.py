"""WebSocket connection pool for subscribing to more than 500 tokens."""

import asyncio
import logging
from collections.abc import Callable

from ..config import WebSocketConfig
from .client import MessageHandler, WebSocketClient

logger = logging.getLogger(__name__)


class WebSocketPool:
    """Manages multiple WebSocket connections to handle >500 tokens.

    Each connection subscribes to up to max_tokens_per_connection tokens.
    All connections share the same message handler.
    """

    def __init__(
        self,
        config: WebSocketConfig | None = None,
        on_message: MessageHandler | None = None,
    ) -> None:
        self._config = config or WebSocketConfig()
        self._on_message = on_message
        self._clients: list[WebSocketClient] = []
        self._running = False

    @property
    def is_connected(self) -> bool:
        """True if any client is connected."""
        return any(c.is_connected for c in self._clients)

    def stop(self) -> None:
        """Signal all clients to stop."""
        self._running = False
        for client in self._clients:
            client.stop()

    async def disconnect(self) -> None:
        """Disconnect all clients."""
        self._running = False
        await asyncio.gather(
            *(c.disconnect() for c in self._clients),
            return_exceptions=True,
        )
        self._clients.clear()

    async def subscribe(self, token_ids: list[str]) -> None:
        """Subscribe to tokens across connected clients (for live updates)."""
        limit = self._config.max_tokens_per_connection
        for client in self._clients:
            # Find tokens this client can accept
            current = len(client.subscribed_tokens)
            capacity = limit - current
            if capacity <= 0:
                continue
            batch = token_ids[:capacity]
            token_ids = token_ids[capacity:]
            if batch:
                await client.subscribe(batch)
            if not token_ids:
                break

    async def unsubscribe(self, token_ids: list[str]) -> None:
        """Unsubscribe tokens from whichever client holds them."""
        token_set = set(token_ids)
        for client in self._clients:
            overlap = token_set & client.subscribed_tokens
            if overlap:
                await client.unsubscribe(list(overlap))
                token_set -= overlap
            if not token_set:
                break

    async def run_with_reconnect(
        self, token_ids: list[str] | Callable[[], list[str]]
    ) -> None:
        """Run multiple WebSocket connections, each handling a chunk of tokens.

        Args:
            token_ids: List of token IDs, or a callable that returns the
                       current list (re-evaluated on each reconnect).
        """
        self._running = True
        limit = self._config.max_tokens_per_connection

        def make_chunk_getter(index: int) -> Callable[[], list[str]]:
            """Create a callable that returns the chunk for connection `index`."""
            def get_chunk() -> list[str]:
                ids = token_ids() if callable(token_ids) else token_ids
                start = index * limit
                return ids[start : start + limit]
            return get_chunk

        while self._running:
            ids = token_ids() if callable(token_ids) else token_ids
            num_connections = max(1, (len(ids) + limit - 1) // limit)

            logger.info(
                f"Starting {num_connections} WebSocket connection(s) "
                f"for {len(ids)} tokens"
            )

            self._clients = [
                WebSocketClient(config=self._config, on_message=self._on_message)
                for _ in range(num_connections)
            ]

            tasks = [
                asyncio.create_task(
                    client.run_with_reconnect(make_chunk_getter(i))
                )
                for i, client in enumerate(self._clients)
            ]

            # Wait until any connection task finishes (shouldn't happen unless
            # stop() is called, since each client has its own reconnect loop)
            done, pending = await asyncio.wait(
                tasks, return_when=asyncio.FIRST_COMPLETED
            )

            # If we're shutting down, cancel remaining
            if not self._running:
                for t in pending:
                    t.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
                break

            # If a connection died unexpectedly while others are running,
            # stop everything and restart the whole pool
            for t in pending:
                t.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            self._clients.clear()

            if self._running:
                logger.info("Pool restarting all connections...")
                await asyncio.sleep(self._config.reconnect_delay)
