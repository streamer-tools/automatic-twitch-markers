"""
EventSub WebSocket client for Twitch Marker Agent.

Connects to Twitch EventSub WebSocket transport to receive
real-time notifications for stream events.

WebSocket endpoint: wss://eventsub.wss.twitch.tv/ws

Flow:
1. Connect to WebSocket
2. Receive session_welcome message with session_id
3. Create subscription via Helix API with session_id as transport (caller's responsibility)
4. Receive events (stream.offline)
5. Handle keepalive messages
6. Reconnect on session_reconnect message

Important: After receiving session_welcome, the caller must create subscriptions
within keepalive_timeout_seconds (default 10s) or the server may close the connection
with code 4003.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Awaitable, Callable

import websockets
from websockets.client import WebSocketClientProtocol

if TYPE_CHECKING:
    pass

# EventSub WebSocket endpoint
EVENTSUB_WS_URL = "wss://eventsub.wss.twitch.tv/ws"

# Default timeout for initial welcome message (seconds)
WELCOME_TIMEOUT_SECONDS = 30

# Message types
MSG_TYPE_WELCOME = "session_welcome"
MSG_TYPE_KEEPALIVE = "session_keepalive"
MSG_TYPE_NOTIFICATION = "notification"
MSG_TYPE_RECONNECT = "session_reconnect"
MSG_TYPE_REVOCATION = "revocation"


class EventSubConnectionError(Exception):
    """Raised when WebSocket connection fails."""

    pass


class EventSubConnectionLost(Exception):
    """Raised when connection is lost (no messages within keepalive timeout)."""

    pass


@dataclass
class EventSubMessage:
    """Parsed EventSub WebSocket message."""

    message_type: str  # session_welcome, session_keepalive, notification, etc.
    payload: dict[str, Any] = field(default_factory=dict)
    subscription_type: str | None = None
    message_id: str | None = None


def parse_eventsub_message(raw_json: str) -> EventSubMessage:
    """
    Parse a raw WebSocket message into EventSubMessage.

    Args:
        raw_json: Raw JSON message string.

    Returns:
        Parsed EventSubMessage object.

    Raises:
        json.JSONDecodeError: If JSON is invalid.
        KeyError: If required fields are missing.
    """
    data = json.loads(raw_json)
    metadata = data.get("metadata", {})
    payload = data.get("payload", {})

    return EventSubMessage(
        message_type=metadata.get("message_type", "unknown"),
        payload=payload,
        subscription_type=metadata.get("subscription_type"),
        message_id=metadata.get("message_id"),
    )


def classify_message_type(message: EventSubMessage) -> str:
    """
    Classify an EventSub message by its type.

    Args:
        message: Parsed EventSubMessage.

    Returns:
        One of: 'session_welcome', 'session_keepalive', 'notification',
                'session_reconnect', 'revocation', or 'unknown'.
    """
    known_types = {
        MSG_TYPE_WELCOME,
        MSG_TYPE_KEEPALIVE,
        MSG_TYPE_NOTIFICATION,
        MSG_TYPE_RECONNECT,
        MSG_TYPE_REVOCATION,
    }
    if message.message_type in known_types:
        return message.message_type
    return "unknown"


class EventSubWebSocketClient:
    """
    EventSub WebSocket client for receiving Twitch events.

    Handles:
    - WebSocket connection lifecycle
    - Message parsing and classification
    - Keepalive timeout detection
    - Reconnection on session_reconnect message
    - Notification dispatch via async queue

    The client is async-only. Entry points (CLI, tray app) are responsible
    for bridging to sync contexts if needed.

    Note: asyncio.Queue is async-friendly within a single event loop,
    NOT thread-safe across threads. Thread bridging is caller's responsibility.
    """

    def __init__(
        self,
        logger: logging.Logger,
        notification_queue: asyncio.Queue[EventSubMessage] | None = None,
        on_revocation: Callable[[EventSubMessage], Awaitable[None]] | None = None,
    ) -> None:
        """
        Initialize the EventSub WebSocket client.

        Args:
            logger: Logger instance.
            notification_queue: Async queue to receive notifications.
                Must be consumed within the same event loop.
            on_revocation: Async callback for revocation messages.
        """
        self._logger = logger
        self._notification_queue = notification_queue
        self._on_revocation = on_revocation

        # Connection state
        self._session_id: str | None = None
        self._keepalive_timeout_seconds: int | None = None
        self._last_message_at: datetime | None = None
        self._reconnect_url: str | None = None
        self._ws: WebSocketClientProtocol | None = None
        self._ws_url: str = EVENTSUB_WS_URL

        # Control state
        self._stop_event = asyncio.Event()
        self._is_running: bool = False

    @property
    def session_id(self) -> str | None:
        """Get the current session ID from session_welcome."""
        return self._session_id

    @property
    def keepalive_timeout_seconds(self) -> int | None:
        """Get the keepalive timeout from session_welcome."""
        return self._keepalive_timeout_seconds

    @property
    def is_connected(self) -> bool:
        """Check if currently connected with a valid session."""
        return self._ws is not None and self._session_id is not None

    async def connect(self, url: str = EVENTSUB_WS_URL) -> str:
        """
        Connect to EventSub WebSocket and return session ID.

        Important: After this returns, the caller should create subscriptions
        within keepalive_timeout_seconds (default 10s) or the server may close
        the connection with code 4003.

        Args:
            url: WebSocket URL to connect to.

        Returns:
            Session ID from session_welcome message.

        Raises:
            EventSubConnectionError: If connection or welcome fails.
        """
        self._ws_url = url
        self._logger.info("Connecting to EventSub WebSocket...")

        try:
            # ping_interval=None: Twitch EventSub is outgoing-only,
            # client pings would cause server to close connection
            self._ws = await websockets.connect(
                url,
                ping_interval=None,
            )
            self._logger.debug("WebSocket connection established")
        except Exception as e:
            self._logger.error("Failed to connect to WebSocket: %s", type(e).__name__)
            raise EventSubConnectionError(f"WebSocket connection failed: {e}") from e

        # Wait for session_welcome
        try:
            raw_message = await asyncio.wait_for(
                self._ws.recv(),
                timeout=WELCOME_TIMEOUT_SECONDS,
            )
            self._update_last_message_at()
        except asyncio.TimeoutError:
            await self._close_ws()
            raise EventSubConnectionError(
                f"No welcome message received within {WELCOME_TIMEOUT_SECONDS}s"
            )
        except Exception as e:
            await self._close_ws()
            raise EventSubConnectionError(f"Error receiving welcome: {e}") from e

        # Parse welcome message
        try:
            message = parse_eventsub_message(raw_message)
        except (json.JSONDecodeError, KeyError) as e:
            await self._close_ws()
            raise EventSubConnectionError(f"Invalid welcome message: {e}") from e

        if message.message_type != MSG_TYPE_WELCOME:
            await self._close_ws()
            raise EventSubConnectionError(
                f"Expected session_welcome, got {message.message_type}"
            )

        # Extract session info
        session = message.payload.get("session", {})
        self._session_id = session.get("id")
        self._keepalive_timeout_seconds = session.get("keepalive_timeout_seconds", 10)

        if not self._session_id:
            await self._close_ws()
            raise EventSubConnectionError("Welcome message missing session ID")

        # Log success (only first 8 chars of session ID for security)
        session_id_preview = self._session_id[:8] if self._session_id else "?"
        self._logger.info(
            "Connected to EventSub, session_id=%s..., keepalive=%ds",
            session_id_preview,
            self._keepalive_timeout_seconds,
        )
        self._logger.warning(
            "Caller must create subscription within %ds or server may close (code 4003)",
            self._keepalive_timeout_seconds,
        )

        return self._session_id

    async def run_until_stopped(self) -> None:
        """
        Main message loop. Blocks until stop() is called or connection lost.

        Handles:
        - session_keepalive: updates last_message_at
        - notification: pushes to notification_queue
        - session_reconnect: reconnects to new URL
        - revocation: calls on_revocation callback

        Raises:
            EventSubConnectionLost: If no message received within keepalive timeout.
            EventSubConnectionError: If connection fails during reconnect.
        """
        if not self._ws or not self._session_id:
            raise EventSubConnectionError("Not connected. Call connect() first.")

        self._is_running = True
        self._stop_event.clear()
        self._logger.info("Starting EventSub message loop")

        # Use keepalive timeout + 10s buffer for recv timeout
        recv_timeout = (self._keepalive_timeout_seconds or 10) + 10

        try:
            while self._is_running and not self._stop_event.is_set():
                await self._receive_and_handle_message(recv_timeout)
        except EventSubConnectionLost:
            self._logger.error("Connection lost (no messages within timeout)")
            raise
        finally:
            self._is_running = False
            self._logger.debug("Message loop exited")

    async def _receive_and_handle_message(self, timeout: float) -> None:
        """Receive and handle a single message with timeout."""
        try:
            raw_message = await asyncio.wait_for(
                self._ws.recv(),
                timeout=timeout,
            )
            self._update_last_message_at()
        except asyncio.TimeoutError:
            # No message within timeout - connection assumed lost
            raise EventSubConnectionLost(
                f"No message received within {timeout}s (keepalive timeout exceeded)"
            )
        except websockets.exceptions.ConnectionClosed as e:
            self._logger.info("WebSocket closed: code=%s", e.code)
            raise EventSubConnectionLost(f"WebSocket closed: {e.code}")

        # Parse message
        try:
            message = parse_eventsub_message(raw_message)
        except (json.JSONDecodeError, KeyError) as e:
            self._logger.warning("Failed to parse message: %s", e)
            return

        msg_type = classify_message_type(message)
        self._logger.debug("Received message type: %s", msg_type)

        # Handle by type
        if msg_type == MSG_TYPE_KEEPALIVE:
            # Already updated last_message_at above
            pass
        elif msg_type == MSG_TYPE_NOTIFICATION:
            await self._handle_notification(message)
        elif msg_type == MSG_TYPE_RECONNECT:
            await self._handle_reconnect(message)
        elif msg_type == MSG_TYPE_REVOCATION:
            await self._handle_revocation(message)
        elif msg_type == MSG_TYPE_WELCOME:
            # Unexpected welcome during run - log but continue
            self._logger.warning("Unexpected session_welcome during run")
        else:
            self._logger.debug("Unknown message type: %s", message.message_type)

    async def _handle_notification(self, message: EventSubMessage) -> None:
        """Handle notification message by pushing to queue."""
        sub_type = message.subscription_type or "unknown"
        self._logger.info("Received notification: %s", sub_type)

        if self._notification_queue:
            await self._notification_queue.put(message)

    async def _handle_revocation(self, message: EventSubMessage) -> None:
        """Handle revocation message by calling callback."""
        sub_type = message.subscription_type or "unknown"
        self._logger.warning("Subscription revoked: %s", sub_type)

        if self._on_revocation:
            try:
                await self._on_revocation(message)
            except Exception as e:
                self._logger.error("Revocation callback failed: %s", type(e).__name__)

    async def _handle_reconnect(self, message: EventSubMessage) -> None:
        """
        Handle session_reconnect by connecting to new URL.

        Per Twitch docs:
        - Connect to reconnect_url
        - Wait for welcome on new connection
        - Only then close old connection
        - Subscriptions are preserved
        """
        session = message.payload.get("session", {})
        reconnect_url = session.get("reconnect_url")

        if not reconnect_url:
            self._logger.error("Reconnect message missing reconnect_url")
            return

        self._logger.info("Reconnect requested, connecting to new URL")
        self._reconnect_url = reconnect_url

        # Save old websocket
        old_ws = self._ws

        try:
            # Connect to new URL
            new_ws = await websockets.connect(
                reconnect_url,
                ping_interval=None,
            )

            # Wait for welcome on new connection
            raw_welcome = await asyncio.wait_for(
                new_ws.recv(),
                timeout=WELCOME_TIMEOUT_SECONDS,
            )

            welcome = parse_eventsub_message(raw_welcome)
            if welcome.message_type != MSG_TYPE_WELCOME:
                await new_ws.close()
                self._logger.error("Expected welcome on reconnect, got %s", welcome.message_type)
                return

            # Update state with new connection
            new_session = welcome.payload.get("session", {})
            new_session_id = new_session.get("id")
            new_keepalive = new_session.get("keepalive_timeout_seconds", 10)

            self._ws = new_ws
            self._session_id = new_session_id
            self._keepalive_timeout_seconds = new_keepalive
            self._update_last_message_at()

            session_id_preview = self._session_id[:8] if self._session_id else "?"
            self._logger.info(
                "Reconnected, new session_id=%s..., keepalive=%ds",
                session_id_preview,
                self._keepalive_timeout_seconds,
            )

            # NOW close old connection
            if old_ws:
                try:
                    await old_ws.close(code=1000)
                except Exception:
                    pass  # Best effort close

        except Exception as e:
            self._logger.error("Reconnect failed: %s", type(e).__name__)
            # Keep using old connection if reconnect failed
            self._ws = old_ws

    async def stop(self) -> None:
        """Signal graceful shutdown of the message loop."""
        self._logger.info("Stopping EventSub client...")
        self._stop_event.set()
        self._is_running = False

    async def close(self) -> None:
        """Close websocket connection and clear state."""
        await self._close_ws()
        self._session_id = None
        self._keepalive_timeout_seconds = None
        self._last_message_at = None
        self._reconnect_url = None
        self._logger.debug("EventSub client closed")

    async def _close_ws(self) -> None:
        """Close websocket connection."""
        if self._ws:
            try:
                await self._ws.close(code=1000)
            except Exception:
                pass  # Best effort
            self._ws = None

    def _update_last_message_at(self) -> None:
        """Update last message timestamp."""
        self._last_message_at = datetime.now(timezone.utc)

