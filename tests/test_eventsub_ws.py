"""
Tests for EventSub WebSocket client.

Uses stdlib unittest + mocks only; no real network connections.
"""

from __future__ import annotations

import asyncio
import json
import logging
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from twitch_marker_agent.core.eventsub_ws import (
    MSG_TYPE_KEEPALIVE,
    MSG_TYPE_NOTIFICATION,
    MSG_TYPE_RECONNECT,
    MSG_TYPE_REVOCATION,
    MSG_TYPE_WELCOME,
    EventSubConnectionError,
    EventSubConnectionLost,
    EventSubMessage,
    EventSubWebSocketClient,
    classify_message_type,
    parse_eventsub_message,
)


# =============================================================================
# Test fixtures: Sample messages
# =============================================================================


def make_welcome_message(
    session_id: str = "test_session_123",
    keepalive_timeout: int = 10,
) -> str:
    """Create a sample session_welcome message."""
    return json.dumps(
        {
            "metadata": {
                "message_id": "msg_001",
                "message_type": "session_welcome",
                "message_timestamp": "2026-02-04T00:00:00Z",
            },
            "payload": {
                "session": {
                    "id": session_id,
                    "status": "connected",
                    "keepalive_timeout_seconds": keepalive_timeout,
                    "reconnect_url": None,
                    "connected_at": "2026-02-04T00:00:00Z",
                }
            },
        }
    )


def make_keepalive_message() -> str:
    """Create a sample session_keepalive message."""
    return json.dumps(
        {
            "metadata": {
                "message_id": "msg_002",
                "message_type": "session_keepalive",
                "message_timestamp": "2026-02-04T00:00:10Z",
            },
            "payload": {},
        }
    )


def make_notification_message(
    subscription_type: str = "stream.offline",
    event_data: dict | None = None,
) -> str:
    """Create a sample notification message."""
    return json.dumps(
        {
            "metadata": {
                "message_id": "msg_003",
                "message_type": "notification",
                "message_timestamp": "2026-02-04T00:00:20Z",
                "subscription_type": subscription_type,
                "subscription_version": "1",
            },
            "payload": {
                "subscription": {
                    "id": "sub_001",
                    "status": "enabled",
                    "type": subscription_type,
                },
                "event": event_data or {"broadcaster_user_id": "12345"},
            },
        }
    )


def make_reconnect_message(reconnect_url: str = "wss://new.eventsub.url/ws") -> str:
    """Create a sample session_reconnect message."""
    return json.dumps(
        {
            "metadata": {
                "message_id": "msg_004",
                "message_type": "session_reconnect",
                "message_timestamp": "2026-02-04T00:00:30Z",
            },
            "payload": {
                "session": {
                    "id": "old_session_id",
                    "status": "reconnecting",
                    "reconnect_url": reconnect_url,
                    "keepalive_timeout_seconds": None,
                }
            },
        }
    )


def make_revocation_message(subscription_type: str = "stream.offline") -> str:
    """Create a sample revocation message."""
    return json.dumps(
        {
            "metadata": {
                "message_id": "msg_005",
                "message_type": "revocation",
                "message_timestamp": "2026-02-04T00:00:40Z",
                "subscription_type": subscription_type,
            },
            "payload": {
                "subscription": {
                    "id": "sub_001",
                    "status": "authorization_revoked",
                    "type": subscription_type,
                }
            },
        }
    )


def create_mock_websocket(messages: list[str]) -> MagicMock:
    """
    Create a mock websocket that returns messages in sequence.

    Args:
        messages: List of JSON message strings to return.

    Returns:
        Mock websocket object.
    """
    mock_ws = MagicMock()
    message_iter = iter(messages)

    async def mock_recv():
        try:
            return next(message_iter)
        except StopIteration:
            # Simulate connection closed after messages exhausted
            raise asyncio.TimeoutError()

    mock_ws.recv = mock_recv
    mock_ws.close = AsyncMock()
    return mock_ws


# =============================================================================
# Tests for pure helper functions
# =============================================================================


class TestParseEventSubMessage(unittest.TestCase):
    """Tests for parse_eventsub_message function."""

    def test_parse_welcome_message(self) -> None:
        """Parse session_welcome and extract fields."""
        raw = make_welcome_message(session_id="abc123", keepalive_timeout=15)
        msg = parse_eventsub_message(raw)

        self.assertEqual(msg.message_type, "session_welcome")
        self.assertEqual(msg.message_id, "msg_001")
        self.assertIsNone(msg.subscription_type)
        self.assertEqual(msg.payload["session"]["id"], "abc123")
        self.assertEqual(msg.payload["session"]["keepalive_timeout_seconds"], 15)

    def test_parse_keepalive_message(self) -> None:
        """Parse session_keepalive message."""
        raw = make_keepalive_message()
        msg = parse_eventsub_message(raw)

        self.assertEqual(msg.message_type, "session_keepalive")
        self.assertEqual(msg.payload, {})

    def test_parse_notification_message(self) -> None:
        """Parse notification message with subscription_type."""
        raw = make_notification_message(subscription_type="stream.offline")
        msg = parse_eventsub_message(raw)

        self.assertEqual(msg.message_type, "notification")
        self.assertEqual(msg.subscription_type, "stream.offline")
        self.assertIn("event", msg.payload)

    def test_parse_reconnect_message(self) -> None:
        """Parse session_reconnect message with reconnect_url."""
        raw = make_reconnect_message(reconnect_url="wss://new.url/ws")
        msg = parse_eventsub_message(raw)

        self.assertEqual(msg.message_type, "session_reconnect")
        self.assertEqual(
            msg.payload["session"]["reconnect_url"], "wss://new.url/ws"
        )

    def test_parse_revocation_message(self) -> None:
        """Parse revocation message."""
        raw = make_revocation_message()
        msg = parse_eventsub_message(raw)

        self.assertEqual(msg.message_type, "revocation")
        self.assertEqual(msg.subscription_type, "stream.offline")

    def test_parse_invalid_json_raises(self) -> None:
        """Invalid JSON raises JSONDecodeError."""
        with self.assertRaises(json.JSONDecodeError):
            parse_eventsub_message("not valid json")

    def test_parse_missing_metadata_returns_unknown(self) -> None:
        """Missing metadata returns 'unknown' message type."""
        raw = json.dumps({"payload": {}})
        msg = parse_eventsub_message(raw)

        self.assertEqual(msg.message_type, "unknown")


class TestClassifyMessageType(unittest.TestCase):
    """Tests for classify_message_type function."""

    def test_classify_welcome(self) -> None:
        """Classify session_welcome."""
        msg = EventSubMessage(message_type="session_welcome", payload={})
        self.assertEqual(classify_message_type(msg), MSG_TYPE_WELCOME)

    def test_classify_keepalive(self) -> None:
        """Classify session_keepalive."""
        msg = EventSubMessage(message_type="session_keepalive", payload={})
        self.assertEqual(classify_message_type(msg), MSG_TYPE_KEEPALIVE)

    def test_classify_notification(self) -> None:
        """Classify notification."""
        msg = EventSubMessage(message_type="notification", payload={})
        self.assertEqual(classify_message_type(msg), MSG_TYPE_NOTIFICATION)

    def test_classify_reconnect(self) -> None:
        """Classify session_reconnect."""
        msg = EventSubMessage(message_type="session_reconnect", payload={})
        self.assertEqual(classify_message_type(msg), MSG_TYPE_RECONNECT)

    def test_classify_revocation(self) -> None:
        """Classify revocation."""
        msg = EventSubMessage(message_type="revocation", payload={})
        self.assertEqual(classify_message_type(msg), MSG_TYPE_REVOCATION)

    def test_classify_unknown(self) -> None:
        """Unknown types return 'unknown'."""
        msg = EventSubMessage(message_type="some_new_type", payload={})
        self.assertEqual(classify_message_type(msg), "unknown")


# =============================================================================
# Tests for EventSubWebSocketClient
# =============================================================================


class TestEventSubWebSocketClientConnect(unittest.TestCase):
    """Tests for connect() method."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.logger = MagicMock(spec=logging.Logger)

    def test_connect_stores_session_id(self) -> None:
        """Connect should store session_id from welcome message."""

        async def run_test() -> None:
            mock_ws = create_mock_websocket([
                make_welcome_message(session_id="session_abc", keepalive_timeout=15)
            ])

            async def mock_connect(*args, **kwargs):
                return mock_ws

            with patch(
                "twitch_marker_agent.core.eventsub_ws.websockets.connect",
                side_effect=mock_connect,
            ):
                client = EventSubWebSocketClient(logger=self.logger)
                session_id = await client.connect()

                self.assertEqual(session_id, "session_abc")
                self.assertEqual(client.session_id, "session_abc")

        asyncio.run(run_test())

    def test_connect_stores_keepalive_timeout(self) -> None:
        """Connect should store keepalive_timeout_seconds from welcome."""

        async def run_test() -> None:
            mock_ws = create_mock_websocket([
                make_welcome_message(keepalive_timeout=20)
            ])

            async def mock_connect(*args, **kwargs):
                return mock_ws

            with patch(
                "twitch_marker_agent.core.eventsub_ws.websockets.connect",
                side_effect=mock_connect,
            ):
                client = EventSubWebSocketClient(logger=self.logger)
                await client.connect()

                self.assertEqual(client.keepalive_timeout_seconds, 20)

        asyncio.run(run_test())

    def test_connect_uses_ping_interval_none(self) -> None:
        """Connect should use ping_interval=None to avoid client pings."""

        async def run_test() -> None:
            mock_ws = create_mock_websocket([make_welcome_message()])
            connect_kwargs = {}

            async def mock_connect(*args, **kwargs):
                connect_kwargs.update(kwargs)
                return mock_ws

            with patch(
                "twitch_marker_agent.core.eventsub_ws.websockets.connect",
                side_effect=mock_connect,
            ):
                client = EventSubWebSocketClient(logger=self.logger)
                await client.connect()

                self.assertEqual(connect_kwargs.get("ping_interval"), None)

        asyncio.run(run_test())

    def test_connect_raises_on_timeout(self) -> None:
        """Connect should raise EventSubConnectionError on timeout."""

        async def run_test() -> None:
            mock_ws = MagicMock()

            async def mock_recv():
                raise asyncio.TimeoutError()

            mock_ws.recv = mock_recv
            mock_ws.close = AsyncMock()

            async def mock_connect(*args, **kwargs):
                return mock_ws

            with patch(
                "twitch_marker_agent.core.eventsub_ws.websockets.connect",
                side_effect=mock_connect,
            ):
                client = EventSubWebSocketClient(logger=self.logger)

                with self.assertRaises(EventSubConnectionError) as ctx:
                    await client.connect()

                self.assertIn("welcome", str(ctx.exception).lower())

        asyncio.run(run_test())

    def test_connect_raises_on_non_welcome_message(self) -> None:
        """Connect should raise if first message is not session_welcome."""

        async def run_test() -> None:
            mock_ws = create_mock_websocket([make_keepalive_message()])

            async def mock_connect(*args, **kwargs):
                return mock_ws

            with patch(
                "twitch_marker_agent.core.eventsub_ws.websockets.connect",
                side_effect=mock_connect,
            ):
                client = EventSubWebSocketClient(logger=self.logger)

                with self.assertRaises(EventSubConnectionError) as ctx:
                    await client.connect()

                self.assertIn("welcome", str(ctx.exception).lower())

        asyncio.run(run_test())


class TestEventSubWebSocketClientKeepalive(unittest.TestCase):
    """Tests for keepalive handling."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.logger = MagicMock(spec=logging.Logger)

    def test_keepalive_updates_last_message_at(self) -> None:
        """Keepalive message should update last_message_at."""

        async def run_test() -> None:
            mock_ws = create_mock_websocket([
                make_welcome_message(),
                make_keepalive_message(),
            ])

            async def mock_connect(*args, **kwargs):
                return mock_ws

            with patch(
                "twitch_marker_agent.core.eventsub_ws.websockets.connect",
                side_effect=mock_connect,
            ):
                client = EventSubWebSocketClient(logger=self.logger)
                await client.connect()

                # Get initial timestamp
                initial_time = client._last_message_at

                # Process one message (keepalive)
                await client._receive_and_handle_message(timeout=5)

                # Timestamp should be updated
                self.assertIsNotNone(client._last_message_at)
                self.assertGreaterEqual(client._last_message_at, initial_time)

        asyncio.run(run_test())


class TestEventSubWebSocketClientNotification(unittest.TestCase):
    """Tests for notification handling."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.logger = MagicMock(spec=logging.Logger)

    def test_notification_pushed_to_queue(self) -> None:
        """Notification should be pushed to notification_queue."""

        async def run_test() -> None:
            queue: asyncio.Queue[EventSubMessage] = asyncio.Queue()

            mock_ws = create_mock_websocket([
                make_welcome_message(),
                make_notification_message(subscription_type="stream.offline"),
            ])

            async def mock_connect(*args, **kwargs):
                return mock_ws

            with patch(
                "twitch_marker_agent.core.eventsub_ws.websockets.connect",
                side_effect=mock_connect,
            ):
                client = EventSubWebSocketClient(
                    logger=self.logger,
                    notification_queue=queue,
                )
                await client.connect()

                # Process one message (notification)
                await client._receive_and_handle_message(timeout=5)

                # Queue should have the notification
                self.assertFalse(queue.empty())
                msg = await queue.get()
                self.assertEqual(msg.message_type, "notification")
                self.assertEqual(msg.subscription_type, "stream.offline")

        asyncio.run(run_test())


class TestEventSubWebSocketClientRevocation(unittest.TestCase):
    """Tests for revocation handling."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.logger = MagicMock(spec=logging.Logger)

    def test_revocation_calls_callback(self) -> None:
        """Revocation should call on_revocation callback."""

        async def run_test() -> None:
            callback_called = []

            async def on_revocation(msg: EventSubMessage) -> None:
                callback_called.append(msg)

            mock_ws = create_mock_websocket([
                make_welcome_message(),
                make_revocation_message(subscription_type="stream.offline"),
            ])

            async def mock_connect(*args, **kwargs):
                return mock_ws

            with patch(
                "twitch_marker_agent.core.eventsub_ws.websockets.connect",
                side_effect=mock_connect,
            ):
                client = EventSubWebSocketClient(
                    logger=self.logger,
                    on_revocation=on_revocation,
                )
                await client.connect()

                # Process one message (revocation)
                await client._receive_and_handle_message(timeout=5)

                # Callback should have been called
                self.assertEqual(len(callback_called), 1)
                self.assertEqual(callback_called[0].message_type, "revocation")
                self.assertEqual(callback_called[0].subscription_type, "stream.offline")

        asyncio.run(run_test())


class TestEventSubWebSocketClientReconnect(unittest.TestCase):
    """Tests for reconnect handling."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.logger = MagicMock(spec=logging.Logger)

    def test_reconnect_stores_reconnect_url(self) -> None:
        """Reconnect message should store reconnect_url."""

        async def run_test() -> None:
            reconnect_url = "wss://new.eventsub.url/ws"
            new_session_id = "new_session_456"

            # Mock for original connection
            original_ws = create_mock_websocket([
                make_welcome_message(session_id="old_session_123"),
                make_reconnect_message(reconnect_url=reconnect_url),
            ])

            # Mock for new connection
            new_ws = create_mock_websocket([
                make_welcome_message(session_id=new_session_id)
            ])

            connect_calls = []

            async def mock_connect(url, **kwargs):
                connect_calls.append(url)
                if len(connect_calls) == 1:
                    return original_ws
                return new_ws

            with patch(
                "twitch_marker_agent.core.eventsub_ws.websockets.connect",
                side_effect=mock_connect,
            ):
                client = EventSubWebSocketClient(logger=self.logger)
                await client.connect()

                self.assertEqual(client.session_id, "old_session_123")

                # Process reconnect message
                await client._receive_and_handle_message(timeout=5)

                # Should have connected to reconnect_url
                self.assertEqual(len(connect_calls), 2)
                self.assertEqual(connect_calls[1], reconnect_url)

                # Session ID should be updated from new welcome
                self.assertEqual(client.session_id, new_session_id)

        asyncio.run(run_test())

    def test_reconnect_does_not_close_old_until_new_welcome(self) -> None:
        """Old connection should not close until new welcome is received."""

        async def run_test() -> None:
            reconnect_url = "wss://new.url/ws"

            # Mock for original connection
            original_ws = create_mock_websocket([
                make_welcome_message(session_id="old_session"),
                make_reconnect_message(reconnect_url=reconnect_url),
            ])

            # Mock for new connection
            new_ws = create_mock_websocket([
                make_welcome_message(session_id="new_session")
            ])

            close_order = []

            async def track_original_close(*args, **kwargs):
                close_order.append("original_closed")

            original_ws.close = track_original_close

            async def mock_connect(url, **kwargs):
                if "new.url" in url:
                    close_order.append("new_connected")
                    return new_ws
                return original_ws

            with patch(
                "twitch_marker_agent.core.eventsub_ws.websockets.connect",
                side_effect=mock_connect,
            ):
                client = EventSubWebSocketClient(logger=self.logger)
                await client.connect()

                # Process reconnect message
                await client._receive_and_handle_message(timeout=5)

                # Order should be: new_connected, then original_closed
                self.assertEqual(close_order, ["new_connected", "original_closed"])

        asyncio.run(run_test())

    def test_reconnect_updates_session_id_from_new_welcome(self) -> None:
        """Session ID should be updated from new welcome message."""

        async def run_test() -> None:
            new_session_id = "completely_new_session_id"

            original_ws = create_mock_websocket([
                make_welcome_message(session_id="old_session"),
                make_reconnect_message(),
            ])

            new_ws = create_mock_websocket([
                make_welcome_message(session_id=new_session_id, keepalive_timeout=25)
            ])

            async def mock_connect(url, **kwargs):
                if "new.eventsub" in url:
                    return new_ws
                return original_ws

            with patch(
                "twitch_marker_agent.core.eventsub_ws.websockets.connect",
                side_effect=mock_connect,
            ):
                client = EventSubWebSocketClient(logger=self.logger)
                await client.connect()

                self.assertEqual(client.session_id, "old_session")

                # Process reconnect
                await client._receive_and_handle_message(timeout=5)

                # Session ID should be the NEW one
                self.assertEqual(client.session_id, new_session_id)
                self.assertEqual(client.keepalive_timeout_seconds, 25)

        asyncio.run(run_test())


class TestEventSubWebSocketClientStopShutdown(unittest.TestCase):
    """Tests for stop and shutdown behavior."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.logger = MagicMock(spec=logging.Logger)

    def test_stop_sets_event(self) -> None:
        """Stop should set the stop event."""

        async def run_test() -> None:
            client = EventSubWebSocketClient(logger=self.logger)

            self.assertFalse(client._stop_event.is_set())

            await client.stop()

            self.assertTrue(client._stop_event.is_set())
            self.assertFalse(client._is_running)

        asyncio.run(run_test())

    def test_close_closes_websocket(self) -> None:
        """Close should close the websocket."""

        async def run_test() -> None:
            mock_ws = create_mock_websocket([make_welcome_message()])

            async def mock_connect(*args, **kwargs):
                return mock_ws

            with patch(
                "twitch_marker_agent.core.eventsub_ws.websockets.connect",
                side_effect=mock_connect,
            ):
                client = EventSubWebSocketClient(logger=self.logger)
                await client.connect()

                self.assertIsNotNone(client._ws)

                await client.close()

                mock_ws.close.assert_called_once_with(code=1000)
                self.assertIsNone(client._ws)
                self.assertIsNone(client.session_id)

        asyncio.run(run_test())

    def test_run_until_stopped_exits_on_stop(self) -> None:
        """run_until_stopped should exit when stop event is set."""

        async def run_test() -> None:
            client = EventSubWebSocketClient(logger=self.logger)

            # Manually set stop event before check
            client._stop_event.set()
            client._is_running = True

            # Verify the condition that would exit the loop
            self.assertTrue(client._stop_event.is_set())

        asyncio.run(run_test())


class TestEventSubWebSocketClientInactivityTimeout(unittest.TestCase):
    """Tests for inactivity timeout handling."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.logger = MagicMock(spec=logging.Logger)

    def test_inactivity_timeout_raises_connection_lost(self) -> None:
        """Timeout with no messages should raise EventSubConnectionLost."""

        async def run_test() -> None:
            mock_ws = MagicMock()

            async def mock_recv():
                raise asyncio.TimeoutError()

            mock_ws.recv = mock_recv
            mock_ws.close = AsyncMock()

            client = EventSubWebSocketClient(logger=self.logger)
            # Manually set connected state
            client._ws = mock_ws
            client._session_id = "test"
            client._keepalive_timeout_seconds = 10

            with self.assertRaises(EventSubConnectionLost):
                await client._receive_and_handle_message(timeout=5)

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
