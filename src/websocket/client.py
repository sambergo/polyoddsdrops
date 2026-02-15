"""WebSocket client for Polymarket CLOB API."""

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed

from ..config import WebSocketConfig
from .messages import BookMessage, PriceChangeMessage, parse_message

logger = logging.getLogger(__name__)

# Type alias for message handlers
MessageHandler = Callable[[BookMessage | PriceChangeMessage], Awaitable[None]]


class WebSocketClient:
    """WebSocket client for Polymarket market data."""

    def __init__(
        self,
        config: WebSocketConfig,
        on_message: MessageHandler | None = None,
    ) -> None:
        """Initialize the WebSocket client.

        Args:
            config: WebSocket configuration.
            on_message: Async callback for received messages.
        """
        self.config = config
        self.on_message = on_message
        self._ws: ClientConnection | None = None
        self._heartbeat_task: asyncio.Task | None = None
        self._subscribed_tokens: set[str] = set()
        self._running = False

    @property
    def is_connected(self) -> bool:
        """Check if WebSocket is connected."""
        return self._ws is not None

    async def connect(self) -> None:
        """Connect to the WebSocket endpoint."""
        logger.info(f"Connecting to {self.config.endpoint}")
        self._ws = await connect(self.config.endpoint)
        self._running = True
        logger.info(f"[{datetime.now().isoformat()}] Connected!")

        # Start heartbeat
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def disconnect(self) -> None:
        """Disconnect from the WebSocket."""
        self._running = False

        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None

        if self._ws:
            await self._ws.close()
            self._ws = None

        self._subscribed_tokens.clear()
        logger.info("Disconnected from WebSocket")

    async def subscribe(self, token_ids: list[str]) -> None:
        """Subscribe to market updates for given tokens.

        Args:
            token_ids: List of token IDs to subscribe to.
                       Max 500 per connection.
        """
        if not self._ws:
            raise RuntimeError("WebSocket not connected")

        if len(token_ids) > self.config.max_tokens_per_connection:
            raise ValueError(
                f"Cannot subscribe to more than "
                f"{self.config.max_tokens_per_connection} tokens per connection"
            )

        msg = {"assets_ids": token_ids, "type": "market"}
        await self._ws.send(json.dumps(msg))

        self._subscribed_tokens.update(token_ids)
        logger.info(f"Subscribed to {len(token_ids)} tokens")

    async def unsubscribe(self, token_ids: list[str]) -> None:
        """Unsubscribe from market updates for given tokens."""
        if not self._ws:
            raise RuntimeError("WebSocket not connected")

        # Polymarket uses same message format but with "unsubscribe" type
        msg = {"assets_ids": token_ids, "type": "unsubscribe"}
        await self._ws.send(json.dumps(msg))

        self._subscribed_tokens.difference_update(token_ids)
        logger.info(f"Unsubscribed from {len(token_ids)} tokens")

    @property
    def subscribed_tokens(self) -> set[str]:
        """Get currently subscribed token IDs."""
        return self._subscribed_tokens.copy()

    async def listen(self) -> None:
        """Listen for messages and dispatch to handler.

        Runs until disconnect() is called or connection is lost.
        """
        if not self._ws:
            raise RuntimeError("WebSocket not connected")

        logger.info("Starting message listener")

        while self._running:
            try:
                raw = await asyncio.wait_for(self._ws.recv(), timeout=1.0)

                # Handle PONG
                if raw == "PONG":
                    logger.debug(f"[{datetime.now().isoformat()}] PONG received")
                    continue

                # Parse and dispatch messages
                messages = parse_message(raw)
                for msg in messages:
                    if self.on_message:
                        try:
                            await self.on_message(msg)
                        except Exception as e:
                            logger.error(f"Error in message handler: {e}")

            except asyncio.TimeoutError:
                # No message received, continue loop
                continue
            except ConnectionClosed as e:
                logger.warning(f"WebSocket connection closed: {e}")
                break  # Exit listen loop, run_with_reconnect will handle reconnection
            except Exception as e:
                logger.error(f"Error receiving message: {e}")
                continue

        logger.info("Message listener stopped")

    async def _heartbeat_loop(self) -> None:
        """Send periodic PING to keep connection alive."""
        while self._running and self._ws:
            await asyncio.sleep(self.config.heartbeat_interval)
            try:
                await self._ws.send("PING")
                logger.debug(f"[{datetime.now().isoformat()}] PING sent")
            except ConnectionClosed:
                logger.warning("Connection closed during heartbeat")
                break  # Exit heartbeat, run_with_reconnect will handle reconnection
            except Exception as e:
                logger.error(f"Error sending heartbeat: {e}")
                break  # Exit heartbeat, run_with_reconnect will handle reconnection

    async def _cleanup_connection(self) -> None:
        """Clean up connection state for reconnection."""
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

    def stop(self) -> None:
        """Signal the client to stop reconnection loop."""
        self._running = False

    async def run_with_reconnect(
        self, token_ids: list[str] | Callable[[], list[str]]
    ) -> None:
        """Run the WebSocket client with automatic reconnection.

        Args:
            token_ids: List of token IDs, or a callable that returns the
                       current list (re-evaluated on each reconnect).
        """
        self._running = True  # Set before loop, not inside connect()
        retry_count = 0
        max_delay = 60

        while self._running:
            try:
                # Resolve tokens fresh on each reconnect
                ids = token_ids() if callable(token_ids) else token_ids
                await self.connect()
                await self.subscribe(ids)
                retry_count = 0  # Reset on successful connection
                await self.listen()
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
            finally:
                # Clean up for next reconnect attempt
                await self._cleanup_connection()

            if self._running:
                delay = min(self.config.reconnect_delay * (2**retry_count), max_delay)
                retry_count += 1
                logger.info(f"Reconnecting in {delay}s (attempt {retry_count})...")
                await asyncio.sleep(delay)
