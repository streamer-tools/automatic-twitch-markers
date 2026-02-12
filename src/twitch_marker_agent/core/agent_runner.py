"""
Async EventSub agent orchestrator for Twitch Marker Agent.

Provides a DI-friendly async runner that:
1. Connects to EventSub WebSocket
2. Ensures stream.offline subscription on session_welcome
3. Dispatches notifications to the offline handler pipeline

This module is framework-agnostic and must not import UI/tray code.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable, Awaitable

if TYPE_CHECKING:
    import requests
    from twitch_marker_agent.core.config import AppConfig
    from twitch_marker_agent.core.state_store import StateStore
    from twitch_marker_agent.core.twitch_oauth import TwitchOAuth
    from twitch_marker_agent.core.eventsub_ws import (
        EventSubWebSocketClient,
        EventSubMessage,
    )


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class AgentStatus:
    """Status information for the agent runner."""

    is_running: bool = False
    last_error: str | None = None
    session_id: str | None = None
    connected_at: datetime | None = None


# =============================================================================
# Agent Runner
# =============================================================================


class AgentRunner:
    """
    Async EventSub agent orchestrator.

    Connects to EventSub WebSocket, ensures subscriptions,
    and dispatches stream.offline notifications to the export pipeline.

    All dependencies are injected for testability.
    """

    def __init__(
        self,
        config: "AppConfig",
        state_store: "StateStore",
        http_client: "requests.Session",
        oauth: "TwitchOAuth",
        logger: logging.Logger,
        eventsub_client: "EventSubWebSocketClient | None" = None,
        ensure_subscription_fn: Callable[..., Any] | None = None,
        handle_offline_fn: Callable[..., Any] | None = None,
    ) -> None:
        """
        Initialize the agent runner.

        Args:
            config: Application configuration.
            state_store: Persistent state storage.
            http_client: HTTP client for API requests.
            oauth: OAuth client for token management.
            logger: Logger instance.
            eventsub_client: Optional injected EventSub client (for testing).
            ensure_subscription_fn: Optional injected subscription function.
            handle_offline_fn: Optional injected offline handler function.
        """
        self._config = config
        self._state_store = state_store
        self._http_client = http_client
        self._oauth = oauth
        self._logger = logger

        # Inject or create defaults
        self._eventsub_client = eventsub_client
        self._ensure_subscription_fn = ensure_subscription_fn
        self._handle_offline_fn = handle_offline_fn

        # State
        self._is_running = False
        self._last_error: str | None = None
        self._session_id: str | None = None
        self._connected_at: datetime | None = None
        self._stop_event: asyncio.Event | None = None
        self._seen_message_ids: set[str] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

        # Track if client was injected (don't reset injected clients)
        self._client_injected = eventsub_client is not None

        # Notification queue for EventSub messages
        self._notification_queue: asyncio.Queue["EventSubMessage"] | None = None
        self._expected_broadcaster_id: str | None = None

    @property
    def is_running(self) -> bool:
        """Check if agent is currently running."""
        return self._is_running

    @property
    def last_error(self) -> str | None:
        """Get last error message (safe, no secrets)."""
        return self._last_error

    @property
    def session_id(self) -> str | None:
        """Get current EventSub session ID."""
        return self._session_id

    @property
    def status(self) -> AgentStatus:
        """Get full agent status."""
        return AgentStatus(
            is_running=self._is_running,
            last_error=self._last_error,
            session_id=self._session_id,
            connected_at=self._connected_at,
        )

    def _get_eventsub_client(self) -> "EventSubWebSocketClient":
        """Get or create EventSub client."""
        if self._eventsub_client is not None:
            return self._eventsub_client

        # Import here to avoid circular imports
        from twitch_marker_agent.core.eventsub_ws import EventSubWebSocketClient

        # Create notification queue
        self._notification_queue = asyncio.Queue()

        client = EventSubWebSocketClient(
            logger=self._logger,
            notification_queue=self._notification_queue,
        )
        self._eventsub_client = client
        return client

    def _get_ensure_subscription_fn(self) -> Callable[..., Any]:
        """Get or create subscription ensure function."""
        if self._ensure_subscription_fn is not None:
            return self._ensure_subscription_fn

        from twitch_marker_agent.core.eventsub_subscriptions import (
            ensure_stream_offline_subscription,
        )

        return ensure_stream_offline_subscription

    def _get_handle_offline_fn(self) -> Callable[..., Any]:
        """Get or create offline handler function."""
        if self._handle_offline_fn is not None:
            return self._handle_offline_fn

        from twitch_marker_agent.core.offline_handler import handle_stream_offline

        return handle_stream_offline

    def _reset_state(self) -> None:
        """
        Reset per-run state for restart reliability.

        Called at start of run_async() to ensure clean state
        for subsequent runs after Stop -> Start.
        """
        self._stop_event = None
        self._loop = None
        self._seen_message_ids.clear()
        self._session_id = None
        self._connected_at = None
        self._last_error = None
        self._expected_broadcaster_id = None

        # Only reset client and queue if not injected (for testing)
        if not self._client_injected:
            self._eventsub_client = None
            self._notification_queue = None

    async def run_async(self) -> None:
        """
        Main async entrypoint. Blocks until stopped.

        Flow:
        1. Connect to EventSub WebSocket
        2. Wait for session_welcome
        3. Ensure subscription (once per welcome)
        4. Consume notifications and dispatch stream.offline events
        5. Stop on request or fatal error
        """
        from twitch_marker_agent.core.twitch_oauth import TokenRefreshError
        from twitch_marker_agent.core.eventsub_subscriptions import (
            SubscriptionAuthError,
            SubscriptionError,
        )
        from twitch_marker_agent.core.auth_identity import resolve_broadcaster_id
        from twitch_marker_agent.core.eventsub_ws import (
            EventSubConnectionError,
            EventSubConnectionLost,
        )

        self._logger.info("AgentRunner starting")

        # Reset state for restart reliability
        self._reset_state()

        self._is_running = True
        self._stop_event = asyncio.Event()
        self._loop = asyncio.get_running_loop()

        try:
            # Get client
            client = self._get_eventsub_client()

            # Step 1: Connect
            self._logger.info("Connecting to EventSub WebSocket")
            try:
                session_id = await client.connect()
                self._session_id = session_id
                self._connected_at = datetime.now()
                self._logger.info("Connected to EventSub, session established")
            except EventSubConnectionError as e:
                self._last_error = "Failed to connect to EventSub"
                self._logger.error("EventSub connection failed: %s", type(e).__name__)
                return

            # Step 2: Ensure subscription (once per welcome)
            try:
                access_token = self._oauth.get_valid_user_access_token(
                    min_ttl_seconds=60
                )
            except TokenRefreshError:
                self._last_error = "Not authenticated. Run auth-login."
                self._logger.warning("AgentRunner: token refresh failed")
                return

            ensure_fn = self._get_ensure_subscription_fn()
            self._expected_broadcaster_id = resolve_broadcaster_id(
                self._config,
                self._state_store,
            )
            if not self._expected_broadcaster_id:
                self._last_error = "No broadcaster identity found. Authenticate with Twitch."
                self._logger.warning("AgentRunner: broadcaster identity missing")
                return

            try:
                self._logger.info("Ensuring stream.offline subscription")
                ensure_fn(
                    http_client=self._http_client,
                    client_id=self._config.client_id,
                    access_token=access_token,
                    broadcaster_id=self._expected_broadcaster_id,
                    session_id=session_id,
                    logger=self._logger,
                )
                self._logger.info("Subscription ensured")
            except SubscriptionAuthError:
                self._last_error = "Subscription auth failed. Run auth-login."
                self._logger.warning("AgentRunner: subscription auth error")
                return
            except SubscriptionError as e:
                self._last_error = "Subscription setup failed"
                self._logger.error(
                    "AgentRunner: subscription error: %s", type(e).__name__
                )
                return

            # Step 3: Run message loop concurrently with notification consumer
            self._logger.info("Starting notification consumer")

            # Create tasks
            message_loop_task = asyncio.create_task(
                self._run_message_loop(client),
                name="message_loop",
            )
            notification_task = asyncio.create_task(
                self._consume_notifications(),
                name="notification_consumer",
            )
            stop_task = asyncio.create_task(
                self._stop_event.wait(),
                name="stop_event",
            )

            # Wait for stop or task completion
            done, pending = await asyncio.wait(
                [message_loop_task, notification_task, stop_task],
                return_when=asyncio.FIRST_COMPLETED,
            )

            # Check if stop was requested
            if stop_task in done:
                self._logger.info("Stop requested, cancelling tasks")
                # Cancel pending tasks
                for task in pending:
                    task.cancel()
                # Wait for cancellations to complete
                for task in pending:
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
            else:
                # Cancel pending tasks (including stop_task if not done)
                for task in pending:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

                # Check for errors in completed tasks
                for task in done:
                    try:
                        task.result()
                    except EventSubConnectionLost:
                        self._last_error = "EventSub connection lost"
                        self._logger.warning("AgentRunner: connection lost")
                    except asyncio.CancelledError:
                        pass
                    except Exception as e:
                        self._last_error = f"Unexpected error: {type(e).__name__}"
                        self._logger.error(
                            "AgentRunner: unexpected error: %s", type(e).__name__
                        )

        except Exception as e:
            self._last_error = f"Agent error: {type(e).__name__}"
            self._logger.error("AgentRunner: fatal error: %s", type(e).__name__)

        finally:
            self._is_running = False
            self._loop = None  # Clear loop reference
            self._logger.info("AgentRunner stopped")

            # Clean up client with timeout to prevent indefinite hang
            if self._eventsub_client:
                try:
                    await asyncio.wait_for(
                        self._eventsub_client.close(),
                        timeout=2.0,
                    )
                except asyncio.TimeoutError:
                    self._logger.warning("EventSub client close timed out")
                except Exception:
                    pass

    async def _run_message_loop(
        self, client: "EventSubWebSocketClient"
    ) -> None:
        """Run the EventSub message loop until stopped."""
        try:
            await client.run_until_stopped()
        except asyncio.CancelledError:
            raise

    async def _consume_notifications(self) -> None:
        """Consume notifications from the queue and dispatch."""
        from twitch_marker_agent.core.twitch_oauth import TokenRefreshError
        from twitch_marker_agent.core.markers_api import MarkersAuthError

        handle_offline = self._get_handle_offline_fn()

        while not (self._stop_event and self._stop_event.is_set()):
            try:
                # Wait for notification with timeout
                if self._notification_queue is None:
                    await asyncio.sleep(0.1)
                    continue

                try:
                    message = await asyncio.wait_for(
                        self._notification_queue.get(),
                        timeout=1.0,
                    )
                except asyncio.TimeoutError:
                    continue

                # Process notification
                await self._handle_notification(message, handle_offline)

            except asyncio.CancelledError:
                raise
            except Exception as e:
                self._logger.error(
                    "Notification processing error: %s", type(e).__name__
                )

    async def _handle_notification(
        self,
        message: "EventSubMessage",
        handle_offline: Callable[..., Any],
    ) -> None:
        """Handle a single notification message."""
        from twitch_marker_agent.core.twitch_oauth import TokenRefreshError
        from twitch_marker_agent.core.markers_api import MarkersAuthError
        from twitch_marker_agent.core.auth_identity import resolve_broadcaster_id

        # Filter for stream.offline only
        if message.subscription_type != "stream.offline":
            self._logger.debug(
                "Ignoring notification type: %s",
                message.subscription_type,
            )
            return

        # Check message_id for dedupe
        if message.message_id:
            if message.message_id in self._seen_message_ids:
                self._logger.debug("Duplicate message_id, ignoring")
                return
            self._seen_message_ids.add(message.message_id)

        # Extract broadcaster_user_id from event payload
        event = message.payload.get("event", {})
        broadcaster_id = event.get("broadcaster_user_id")

        if not broadcaster_id:
            self._logger.warning("Notification missing broadcaster_user_id")
            return

        # Check broadcaster matches config
        expected_broadcaster_id = self._expected_broadcaster_id or resolve_broadcaster_id(
            self._config,
            self._state_store,
        )
        if not expected_broadcaster_id:
            self._logger.warning("No broadcaster identity configured; ignoring notification")
            return

        if broadcaster_id != expected_broadcaster_id:
            self._logger.debug(
                "Ignoring notification for different broadcaster"
            )
            return

        self._logger.info("Processing stream.offline notification")

        # Get fresh token for handler
        try:
            access_token = self._oauth.get_valid_user_access_token(
                min_ttl_seconds=60
            )
        except TokenRefreshError:
            self._last_error = "Token refresh failed during notification"
            self._logger.warning("Token refresh failed, cannot process offline event")
            return

        # Dispatch to offline handler (run in executor to not block async)
        try:
            # Run sync handler in thread pool
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                lambda: handle_offline(
                    http_client=self._http_client,
                    config=self._config,
                    access_token=access_token,
                    broadcaster_id=broadcaster_id,
                    state_store=self._state_store,
                    logger=self._logger,
                    seen_message_ids=self._seen_message_ids,
                ),
            )
            self._logger.info("stream.offline handled successfully")
        except MarkersAuthError:
            self._last_error = "Markers auth failed. Run auth-login."
            self._logger.warning("Markers auth error during offline handling")
        except Exception as e:
            self._logger.error(
                "Error handling stream.offline: %s", type(e).__name__
            )

    def request_stop(self) -> None:
        """
        Request graceful shutdown of the agent.

        Thread-safe: can be called from any thread.
        """
        self._logger.info("Stop requested for AgentRunner")

        # Set stop event using stored loop (thread-safe)
        if self._stop_event and self._loop:
            try:
                self._loop.call_soon_threadsafe(self._stop_event.set)
            except RuntimeError:
                # Loop closed or not running
                self._logger.debug("Could not signal stop event, loop unavailable")
        elif not self._loop:
            self._logger.debug("No stored loop, stop event not signaled")

        # Stop EventSub client (schedule async stop on event loop)
        if self._eventsub_client and self._loop:
            try:
                stop_result = self._eventsub_client.stop()
                if asyncio.iscoroutine(stop_result):
                    asyncio.run_coroutine_threadsafe(stop_result, self._loop)
                else:
                    self._logger.debug(
                        "EventSub client stop is non-coroutine; skipping async schedule"
                    )
            except TypeError:
                self._logger.debug("Could not schedule client stop, invalid coroutine")
            except RuntimeError:
                # Loop closed or not running
                self._logger.debug("Could not schedule client stop, loop unavailable")
