"""
EventSub WebSocket client for Twitch Marker Agent.

Connects to Twitch EventSub WebSocket transport to receive
real-time notifications for stream events.

WebSocket endpoint: wss://eventsub.wss.twitch.tv/ws

Flow:
1. Connect to WebSocket
2. Receive session_welcome message with session_id
3. Create subscription via Helix API with session_id as transport
4. Receive events (stream.offline)
5. Handle keepalive messages
6. Reconnect on disconnect
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Any

if TYPE_CHECKING:
    from twitch_marker_agent.core.config import AppConfig

# EventSub WebSocket endpoint
EVENTSUB_WS_URL = "wss://eventsub.wss.twitch.tv/ws"


@dataclass
class EventSubMessage:
    """Parsed EventSub WebSocket message."""

    message_type: str  # session_welcome, session_keepalive, notification, etc.
    payload: dict[str, Any]
    subscription_type: str | None = None


class EventSubClient:
    """
    EventSub WebSocket client for receiving Twitch events.

    Handles:
    - WebSocket connection lifecycle
    - Message parsing
    - Automatic reconnection
    - Subscription creation via callback

    The client is designed to be run in an event loop. Use start()
    to begin listening and shutdown() to gracefully disconnect.
    """

    def __init__(
        self,
        config: AppConfig,
        access_token: str,
        logger: logging.Logger,
        on_stream_offline: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        """
        Initialize the EventSub client.

        Args:
            config: Application configuration.
            access_token: Valid OAuth access token.
            logger: Logger instance.
            on_stream_offline: Callback for stream.offline events.
        """
        self._config = config
        self._access_token = access_token
        self._logger = logger
        self._on_stream_offline = on_stream_offline

        self._session_id: str | None = None
        self._is_running: bool = False
        self._should_reconnect: bool = True

    @property
    def session_id(self) -> str | None:
        """Get the current session ID from session_welcome."""
        return self._session_id

    @property
    def is_connected(self) -> bool:
        """Check if currently connected."""
        return self._session_id is not None

    async def connect(self) -> str:
        """
        Connect to EventSub WebSocket and return session ID.

        Returns:
            Session ID from session_welcome message.

        Raises:
            NotImplementedError: WebSocket connection not yet implemented.
        """
        # TODO: Implement WebSocket connection
        # 1. Connect to EVENTSUB_WS_URL using websockets library
        # 2. Wait for session_welcome message
        # 3. Parse session_id from message
        # 4. Store session_id
        # 5. Return session_id
        raise NotImplementedError("TODO: Implement EventSub WebSocket connect")

    async def subscribe_stream_offline(self, broadcaster_user_id: str) -> dict[str, Any]:
        """
        Create stream.offline subscription via Helix API.

        Must be called after connect() to have a valid session_id.

        Args:
            broadcaster_user_id: Twitch user ID to monitor.

        Returns:
            Subscription response from Helix API.

        Raises:
            NotImplementedError: Subscription creation not yet implemented.
        """
        # TODO: Implement subscription creation
        # POST https://api.twitch.tv/helix/eventsub/subscriptions
        # {
        #   "type": "stream.offline",
        #   "version": "1",
        #   "condition": {"broadcaster_user_id": broadcaster_user_id},
        #   "transport": {"method": "websocket", "session_id": self._session_id}
        # }
        raise NotImplementedError("TODO: Implement stream.offline subscription")

    async def run(self) -> None:
        """
        Main event loop - listen for messages until shutdown.

        Handles:
        - Keepalive messages
        - Notification messages (triggers callbacks)
        - Reconnection on disconnect

        Raises:
            NotImplementedError: Message loop not yet implemented.
        """
        # TODO: Implement message loop
        # 1. Set self._is_running = True
        # 2. Loop while self._is_running:
        #    a. Receive message
        #    b. Parse message type
        #    c. Handle session_keepalive (reset timeout)
        #    d. Handle notification (dispatch to callbacks)
        #    e. Handle session_reconnect (reconnect to new URL)
        # 3. On disconnect, reconnect if self._should_reconnect
        raise NotImplementedError("TODO: Implement EventSub message loop")

    async def shutdown(self) -> None:
        """
        Gracefully shutdown the WebSocket connection.

        Stops the message loop and closes the connection.

        Raises:
            NotImplementedError: Shutdown not yet implemented.
        """
        # TODO: Implement graceful shutdown
        # 1. Set self._is_running = False
        # 2. Set self._should_reconnect = False
        # 3. Close WebSocket connection
        # 4. Clear session_id
        self._logger.info("Shutting down EventSub client...")
        self._is_running = False
        self._should_reconnect = False
        raise NotImplementedError("TODO: Implement EventSub shutdown")

    def _parse_message(self, raw_message: str) -> EventSubMessage:
        """
        Parse a raw WebSocket message into EventSubMessage.

        Args:
            raw_message: Raw JSON message string.

        Returns:
            Parsed EventSubMessage object.
        """
        import json

        data = json.loads(raw_message)
        metadata = data.get("metadata", {})
        payload = data.get("payload", {})

        return EventSubMessage(
            message_type=metadata.get("message_type", "unknown"),
            payload=payload,
            subscription_type=metadata.get("subscription_type"),
        )
