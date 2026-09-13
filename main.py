#!/usr/bin/env python3
"""Polydrop - Polymarket odds dropper for sports markets.

Main entry point that:
1. Loads configuration from environment variables
2. Initializes database and creates tables
3. Fetches sports markets from Gamma API
4. Filters markets by liquidity, spread, volume, and price range
5. Stores filtered markets in database
6. Connects to WebSocket and subscribes to tokens
7. Tracks prices and calculates velocity
8. Logs stats periodically (Phase 3 will add alerting)
"""

import asyncio
import logging
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import uvicorn

from src.clob import ClobClient
from src.config import Config
from src.db import Database
from src.db.models import AlertRow, MarketRow
from src.gamma import GammaClient
from src.monitoring import PriceTracker, SubscriptionManager
from src.redis import RedisPublisher, TokenUpdate
from src.websocket import TopOfBookMessage, WebSocketPool

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("polydrop")


def _build_ui() -> None:
    """Build the React UI if bun is available."""
    ui_dir = Path(__file__).resolve().parent / "ui"
    if not ui_dir.is_dir():
        logger.warning("UI directory not found, skipping build")
        return

    bun = shutil.which("bun")
    if not bun:
        logger.warning("bun not found in PATH, skipping UI build")
        return

    logger.info("Building UI...")
    try:
        result = subprocess.run(
            [bun, "run", "build"],
            cwd=ui_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            logger.warning(
                f"UI build failed (exit {result.returncode}): {result.stderr}"
            )
        else:
            logger.info("UI build complete")
    except subprocess.TimeoutExpired:
        logger.warning("UI build timed out (120s)")
    except Exception as e:
        logger.warning(f"UI build error: {e}")


class Polydrop:
    """Main application class."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.db = Database(config.db_path)
        self.gamma = GammaClient(
            filter_config=config.filter,
            hours_ahead=24,
        )
        self.ws_client = WebSocketPool(
            config=config.websocket,
            on_message=self.on_message,
        )
        self.price_tracker = PriceTracker(config=config.monitoring)
        self.subscription_manager = SubscriptionManager(
            max_tokens=config.websocket.max_tokens_per_connection
        )
        self.redis_publisher = RedisPublisher(config.redis)
        # Cache TTLs: 5 min for upcoming, 1 hour for live (matches don't un-start)
        self.clob = ClobClient(cache_ttl_seconds=300, live_cache_ttl_seconds=3600)
        self._running = False
        self._last_stats_log = 0.0
        self._alert_cooldowns: dict[str, float] = {}
        self._alert_tasks: dict[str, asyncio.Task] = {}
        self._current_tokens: list[str] = []
        self._market_cache: dict[str, MarketRow] = {}
        self._pending_updates: dict[str, TopOfBookMessage] = {}
        self._processed_updates = 0
        self._max_loop_lag = 0.0
        self._last_metric_time = time.monotonic()
        self._last_ws_messages = 0
        self._last_ws_bytes = 0
        self._last_processed_updates = 0
        self._shutdown_event = asyncio.Event()
        self._uvicorn_server: uvicorn.Server | None = None

    async def _is_live_or_near_live(
        self,
        condition_id: str | None,
        stored_start_time: str | None,
    ) -> bool:
        """Check if an event is live or starting soon.

        Checks both the stored Gamma time and CLOB API time. If either
        indicates the event is live or starting soon, returns True.

        Returns True if the event has started or will start within
        the configured cutoff time (no time to react to alerts).
        """
        cutoff = self.config.alert.cutoff_before_start_seconds

        # Check stored time first (always available, from Gamma API)
        if self._start_time_is_past_cutoff(stored_start_time, cutoff):
            return True

        # Also check CLOB API for real-time start time (important for
        # tennis/MMA where matches can start before scheduled time)
        if condition_id:
            clob_time = await self.clob.get_game_start_time(condition_id)
            if clob_time and clob_time != stored_start_time:
                if self._start_time_is_past_cutoff(clob_time, cutoff):
                    return True

        return False

    def _start_time_is_past_cutoff(
        self, start_time: str | None, cutoff_seconds: int
    ) -> bool:
        """Check if a start time is past the cutoff (live or starting soon)."""
        if not start_time:
            return False
        try:
            dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            seconds_until_start = (dt - now).total_seconds()
            return seconds_until_start < cutoff_seconds
        except (ValueError, TypeError):
            return False

    async def on_message(self, msg: TopOfBookMessage) -> None:
        """Keep only the latest update for each token until the next flush."""
        if msg.asset_id and msg.asset_id in self._market_cache:
            self._pending_updates[msg.asset_id] = msg

    async def _process_update_loop(self) -> None:
        interval = self.config.monitoring.process_interval_seconds
        next_flush = time.monotonic() + interval
        while self._running:
            try:
                await asyncio.wait_for(
                    self._shutdown_event.wait(),
                    timeout=max(0.0, next_flush - time.monotonic()),
                )
                break
            except asyncio.TimeoutError:
                pass

            now = time.monotonic()
            self._max_loop_lag = max(self._max_loop_lag, max(0.0, now - next_flush))
            next_flush = now + interval
            await self._flush_pending_updates()

            if (
                now - self._last_stats_log
                >= self.config.monitoring.log_interval_seconds
            ):
                self._last_stats_log = now
                self._log_stats()

        await self._flush_pending_updates()

    async def _flush_pending_updates(self) -> None:
        if not self._pending_updates:
            return
        pending, self._pending_updates = self._pending_updates, {}
        redis_updates: list[TokenUpdate] = []
        for token_id, message in pending.items():
            mid_price = message.mid_price
            live_spread = message.best_ask - message.best_bid
            self.price_tracker.update_price(token_id, mid_price)
            velocity = self.price_tracker.get_velocity(token_id)
            redis_updates.append(
                TokenUpdate(
                    token_id=token_id,
                    market=self._market_cache.get(token_id),
                    mid_price=mid_price,
                    best_bid=message.best_bid,
                    best_ask=message.best_ask,
                    velocity=velocity,
                    live_spread=live_spread,
                )
            )
            self._schedule_alert_check(token_id, live_spread)

        self._processed_updates += len(pending)
        await self.redis_publisher.publish_token_states(redis_updates)

    def _schedule_alert_check(self, token_id: str, live_spread: float) -> None:
        velocity = self.price_tracker.get_velocity(token_id)
        if (
            token_id in self._alert_tasks
            or velocity is None
            or velocity.observation_count < self.config.alert.min_observations
            or abs(velocity.velocity.pct_change) < self.config.alert.threshold_pct
            or live_spread > self.config.filter.max_spread
            or time.time() - self._alert_cooldowns.get(token_id, 0)
            < self.config.alert.cooldown_seconds
        ):
            return
        task = asyncio.create_task(self._check_and_alert(token_id, live_spread))
        self._alert_tasks[token_id] = task

        def finished(done: asyncio.Task) -> None:
            self._alert_tasks.pop(token_id, None)
            if not done.cancelled() and (error := done.exception()):
                logger.error("Alert check failed for %s: %s", token_id[:20], error)

        task.add_done_callback(finished)

    def _log_stats(self) -> None:
        """Log current tracking statistics."""
        tracker_stats = self.price_tracker.get_stats()
        sub_stats = self.subscription_manager.get_stats()
        ws_stats = self.ws_client.get_stats()
        now = time.monotonic()
        elapsed = max(now - self._last_metric_time, 0.001)
        messages_per_second = (
            ws_stats["raw_messages"] - self._last_ws_messages
        ) / elapsed
        megabits_per_second = (
            (ws_stats["raw_bytes"] - self._last_ws_bytes) * 8 / 1_000_000 / elapsed
        )
        processed_per_second = (
            self._processed_updates - self._last_processed_updates
        ) / elapsed

        logger.info(
            f"Stats: "
            f"tracked={tracker_stats['tracked_tokens']} tokens, "
            f"updates={tracker_stats['total_updates']}, "
            f"subscribed={sub_stats['subscribed']}/{sub_stats['available']}, "
            f"feed={messages_per_second:.0f} msg/s {megabits_per_second:.2f} Mb/s, "
            f"processed={processed_per_second:.0f} token/s, "
            f"redis_batch={self.redis_publisher.last_batch_size} "
            f"in {self.redis_publisher.last_batch_duration * 1000:.1f}ms, "
            f"loop_lag_max={self._max_loop_lag * 1000:.1f}ms, "
            f"reconnects={ws_stats['reconnects']}"
        )
        self._last_metric_time = now
        self._last_ws_messages = ws_stats["raw_messages"]
        self._last_ws_bytes = ws_stats["raw_bytes"]
        self._last_processed_updates = self._processed_updates
        self._max_loop_lag = 0.0

        # Log some velocity data for debugging
        velocities = self.price_tracker.get_all_velocities()
        if velocities:
            # Show top 3 by absolute pct change
            top = sorted(
                velocities, key=lambda v: abs(v.velocity.pct_change), reverse=True
            )[:3]
            for v in top:
                logger.info(
                    f"  {v.token_id[:20]}...: "
                    f"{v.velocity.oldest_price:.4f} -> {v.velocity.newest_price:.4f} "
                    f"({v.velocity.pct_change:+.2f}% in {v.velocity.elapsed_seconds:.1f}s)"
                )

    async def _check_and_alert(
        self, token_id: str, live_spread: float | None = None
    ) -> None:
        """Check if a token's price movement triggers an alert.

        Checks velocity threshold, spread, cooldown, and deduplication before
        sending alerts.

        Args:
            token_id: The token to check.
            live_spread: Real-time spread from order book.
        """
        # Get velocity data
        velocity = self.price_tracker.get_velocity(token_id)
        if velocity is None:
            return

        # Check minimum observations
        if velocity.observation_count < self.config.alert.min_observations:
            return

        # Check threshold
        pct_change = velocity.velocity.pct_change
        if abs(pct_change) < self.config.alert.threshold_pct:
            return

        # Check live spread - reject alerts for tokens with wide spreads
        if live_spread is not None and live_spread > self.config.filter.max_spread:
            logger.debug(
                f"Alert for {token_id[:20]}... skipped - "
                f"live spread {live_spread:.4f} > {self.config.filter.max_spread}"
            )
            return

        # Get market metadata (needed for live check and alert context)
        market = self._market_cache.get(token_id)

        # Skip live or near-live events (no time to react)
        # Uses CLOB API for real-time start time (important for tennis/MMA
        # where matches can start before scheduled time)
        if market and await self._is_live_or_near_live(
            market.condition_id, market.game_start_time
        ):
            logger.debug(
                f"Alert for {token_id[:20]}... skipped - event is live/starting soon"
            )
            return

        # Check in-memory cooldown
        now = time.time()
        last_alert = self._alert_cooldowns.get(token_id, 0)
        if now - last_alert < self.config.alert.cooldown_seconds:
            logger.debug(f"Alert for {token_id[:20]}... blocked by cooldown")
            return

        # Check database for recent alerts (dedup across restarts)
        recent_alerts = self.db.get_recent_alerts(
            token_id, self.config.alert.cooldown_seconds
        )
        if recent_alerts:
            logger.debug(f"Alert for {token_id[:20]}... blocked by DB dedup")
            return

        # Create alert record
        alert = AlertRow.create(
            token_id=token_id,
            alert_type="velocity",
            old_price=velocity.velocity.oldest_price,
            new_price=velocity.velocity.newest_price,
            price_change_pct=pct_change,
            time_window_seconds=int(velocity.velocity.elapsed_seconds),
        )

        # Store in database
        self.db.insert_alert(alert)

        # Update in-memory cooldown
        self._alert_cooldowns[token_id] = now

        logger.info(
            f"Alert triggered: {token_id[:20]}... "
            f"{velocity.velocity.oldest_price:.4f} -> {velocity.velocity.newest_price:.4f} "
            f"({pct_change:+.2f}%)"
        )

    async def _run_api_server(self) -> None:
        """Run the FastAPI server inside the event loop."""
        from src.api.server import app as fastapi_app

        config = uvicorn.Config(
            app=fastapi_app,
            host=self.config.api.host,
            port=self.config.api.port,
            log_level=self.config.log_level.lower(),
        )
        server = uvicorn.Server(config)
        server.install_signal_handlers = lambda: None  # main.py handles signals
        self._uvicorn_server = server
        logger.info(
            f"Starting API server on {self.config.api.host}:{self.config.api.port}"
        )
        await server.serve()

    def _fetch_markets(self) -> tuple[list[MarketRow], list[str]]:
        """Fetch and filter markets from Gamma API (thread-safe, no DB access).

        Returns:
            Tuple of (market_rows, token_ids).
        """
        if self.config.monitor_all_sports:
            logger.info("Fetching ALL sports markets")
            markets, rejections = self.gamma.fetch_all_sports_markets()
        else:
            logger.info(f"Fetching markets for sports: {self.config.sports}")
            markets, rejections = self.gamma.fetch_sports_markets(self.config.sports)
        logger.info(f"Fetched {len(markets)} markets after filtering")

        if rejections:
            logger.info(f"Rejection reasons: {rejections}")

        market_rows = self.gamma.to_market_rows(markets)
        token_ids = [m.token_id for m in markets]
        return market_rows, token_ids

    def fetch_and_store_markets(self) -> list[str]:
        """Fetch markets from Gamma API and store in database.

        Returns:
            List of token IDs for filtered markets.
        """
        market_rows, token_ids = self._fetch_markets()
        self.db.upsert_markets(market_rows)
        self._market_cache = {market.token_id: market for market in market_rows}
        logger.info(f"Stored {len(market_rows)} markets in database")
        return token_ids

    async def _market_refresh_loop(self) -> None:
        """Periodically refresh market list."""
        interval = self.config.refresh_interval_seconds
        if interval <= 0:
            logger.info("Market refresh disabled (interval <= 0)")
            return

        logger.info(f"Market refresh loop started (every {interval}s)")
        while self._running:
            try:
                await asyncio.wait_for(self._shutdown_event.wait(), timeout=interval)
                # Event was set → shutting down
                break
            except asyncio.TimeoutError:
                # Normal timeout → time to refresh
                pass

            if not self._running:
                break

            try:
                await self._apply_refresh()
            except Exception:
                logger.exception("Market refresh failed, will retry next cycle")

        logger.info("Market refresh loop stopped")

    async def _apply_refresh(self) -> None:
        """Fetch fresh markets and update subscriptions."""
        logger.info("Starting periodic market refresh...")

        # Run HTTP fetch in a thread (no DB access), then store on main thread
        market_rows, new_token_ids = await asyncio.to_thread(self._fetch_markets)
        self.db.upsert_markets(market_rows)
        logger.info(f"Stored {len(market_rows)} markets in database")

        if not new_token_ids:
            logger.warning("Refresh returned no markets, keeping current subscriptions")
            return

        old_set = set(self._current_tokens)
        new_set = set(new_token_ids)

        added = new_set - old_set
        removed = old_set - new_set
        unchanged = old_set & new_set

        logger.info(
            f"Market refresh diff: +{len(added)} new, -{len(removed)} removed, "
            f"{len(unchanged)} unchanged"
        )

        # Update subscription manager
        self.subscription_manager.set_available_tokens(new_token_ids)
        new_desired = self.subscription_manager.get_tokens_to_subscribe()
        desired_set = set(new_desired)
        for market in market_rows:
            market.is_subscribed = market.token_id in desired_set
        self._market_cache = {market.token_id: market for market in market_rows}

        # Update current tokens (reconnects will pick this up)
        self._current_tokens = new_desired

        # Update DB subscription state
        self.subscription_manager.mark_subscribed(new_desired)
        self.db.set_subscribed(new_desired, subscribed=True)
        await self.redis_publisher.sync_tokens(new_desired)

        # Clean up price tracker for removed tokens
        for tid in old_set - set(new_desired):
            self.price_tracker.remove_token(tid)
            self._pending_updates.pop(tid, None)

        # Restart pool so all clients reconnect with fresh chunks
        # This is more reliable than live sub/unsub which can lose tokens
        # when connection count changes or clients have stale state
        if self.ws_client.is_connected:
            logger.info("Restarting WebSocket pool with updated tokens")
            self.ws_client.restart()
        else:
            logger.info("WebSocket not connected, tokens updated for next reconnect")

        logger.info("Market refresh complete")

    async def run(self) -> None:
        """Run the main application loop."""
        self._running = True

        # Setup signal handlers for graceful shutdown
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._handle_shutdown)

        try:
            # Initialize database
            logger.info(f"Initializing database at {self.config.db_path}")
            self.db.connect()

            # Connect to Redis (non-fatal if unavailable)
            await self.redis_publisher.connect()

            # Fetch and store markets
            token_ids = self.fetch_and_store_markets()

            if not token_ids:
                logger.warning("No markets found to monitor. Exiting.")
                return

            # Setup subscription manager
            self.subscription_manager.set_available_tokens(token_ids)
            tokens_to_subscribe = self.subscription_manager.get_tokens_to_subscribe()

            logger.info(
                f"Will subscribe to {len(tokens_to_subscribe)} tokens "
                f"(of {len(token_ids)} available)"
            )

            # Mark as subscribed in database
            self.db.set_subscribed(tokens_to_subscribe, subscribed=True)
            self.subscription_manager.mark_subscribed(tokens_to_subscribe)
            for token_id in tokens_to_subscribe:
                if market := self._market_cache.get(token_id):
                    market.is_subscribed = True
            await self.redis_publisher.sync_tokens(tokens_to_subscribe)

            # Connect to WebSocket and start listening with auto-reconnect
            logger.info("Starting WebSocket with auto-reconnect (Ctrl+C to stop)")
            self._last_stats_log = time.monotonic()
            self._current_tokens = tokens_to_subscribe
            await asyncio.gather(
                self.ws_client.run_with_reconnect(lambda: self._current_tokens),
                self._market_refresh_loop(),
                self._process_update_loop(),
                self._run_api_server(),
            )

        except Exception as e:
            logger.error(f"Error in main loop: {e}", exc_info=True)
            raise
        finally:
            await self.shutdown()

    def _handle_shutdown(self) -> None:
        """Handle shutdown signal."""
        logger.info("Shutdown signal received")
        self._running = False
        self._shutdown_event.set()
        self.ws_client.stop()  # Use public method
        if self._uvicorn_server:
            self._uvicorn_server.should_exit = True

    async def shutdown(self) -> None:
        """Clean up resources."""
        logger.info("Shutting down...")

        try:
            await asyncio.wait_for(self.ws_client.disconnect(), timeout=5.0)
        except asyncio.TimeoutError:
            logger.warning("WebSocket disconnect timed out")

        for task in self._alert_tasks.values():
            task.cancel()
        if self._alert_tasks:
            await asyncio.gather(*self._alert_tasks.values(), return_exceptions=True)
        self._alert_tasks.clear()
        await self.redis_publisher.close()
        await self.clob.close()
        self.db.close()

        logger.info("Shutdown complete")


def main() -> None:
    """Main entry point."""
    print(f"[{datetime.now().isoformat()}] Polydrop starting...")

    # Load configuration
    config = Config.from_env()

    # Set log level from config
    logging.getLogger().setLevel(getattr(logging, config.log_level.upper()))

    logger.info("Config loaded:")
    logger.info(f"  Database: {config.db_path}")
    if config.monitor_all_sports:
        logger.info("  Sports: ALL (dynamic discovery)")
    else:
        logger.info(f"  Sports: {config.sports}")
    logger.info(f"  Min liquidity: ${config.filter.min_liquidity:,.0f}")
    logger.info(f"  Max spread: {config.filter.max_spread:.2f}")
    logger.info(f"  Window: {config.monitoring.window_seconds}s")
    logger.info(
        f"  Processing interval: {config.monitoring.process_interval_seconds:.3f}s"
    )
    logger.info(f"  Alert threshold: {config.alert.threshold_pct}%")
    logger.info(f"  Alert cooldown: {config.alert.cooldown_seconds}s")
    if config.refresh_interval_seconds > 0:
        logger.info(f"  Market refresh: every {config.refresh_interval_seconds}s")
    else:
        logger.info("  Market refresh: disabled")

    # Build UI before importing API server (so static mount finds dist/)
    _build_ui()

    # Create and run application
    app = Polydrop(config)

    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
