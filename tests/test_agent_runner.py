"""
Unit tests for AgentRunner.

Tests async orchestrator behavior with mocked dependencies:
- EventSub client connection and subscription ensure
- Notification dispatch to offline handler
- Stop/error handling

Uses unittest + unittest.mock only (no real network/websocket).
"""

from __future__ import annotations

import asyncio
import logging
import unittest
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch


# =============================================================================
# Test Fixtures
# =============================================================================


def make_mock_config() -> MagicMock:
    """Create a mock AppConfig."""
    config = MagicMock()
    config.client_id = "test_client_id"
    config.broadcaster_id = "12345"
    config.export_formats = ("csv",)
    config.output_dir = "/tmp/markers"
    return config


def make_mock_message(
    subscription_type: str = "stream.offline",
    broadcaster_id: str = "12345",
    message_id: str = "msg_001",
) -> MagicMock:
    """Create a mock EventSubMessage."""
    msg = MagicMock()
    msg.subscription_type = subscription_type
    msg.message_id = message_id
    msg.payload = {
        "event": {
            "broadcaster_user_id": broadcaster_id,
        }
    }
    return msg


# =============================================================================
# AgentRunner Tests
# =============================================================================


class TestAgentRunnerInit(unittest.TestCase):
    """Test AgentRunner initialization."""

    def test_init_creates_instance(self) -> None:
        """Should create instance without error."""
        from twitch_marker_agent.core.agent_runner import AgentRunner

        config = make_mock_config()
        state_store = MagicMock()
        http_client = MagicMock()
        oauth = MagicMock()
        logger = MagicMock(spec=logging.Logger)

        runner = AgentRunner(
            config=config,
            state_store=state_store,
            http_client=http_client,
            oauth=oauth,
            logger=logger,
        )

        self.assertIsNotNone(runner)
        self.assertFalse(runner.is_running)
        self.assertIsNone(runner.last_error)


class TestAgentRunnerEnsureSubscription(unittest.TestCase):
    """Test subscription ensure on connect."""

    def test_ensures_subscription_on_welcome_once(self) -> None:
        """Should call ensure_stream_offline_subscription exactly once."""
        from twitch_marker_agent.core.agent_runner import AgentRunner

        config = make_mock_config()
        state_store = MagicMock()
        http_client = MagicMock()
        oauth = MagicMock()
        oauth.get_valid_user_access_token.return_value = "test_token"
        logger = MagicMock(spec=logging.Logger)

        # Mock EventSub client
        eventsub_client = MagicMock()
        eventsub_client.connect = AsyncMock(return_value="session_123")
        eventsub_client.run_until_stopped = AsyncMock()
        eventsub_client.stop = MagicMock()
        eventsub_client.close = AsyncMock()

        # Mock subscription ensure
        ensure_fn = MagicMock()

        # Mock offline handler
        offline_fn = MagicMock()

        runner = AgentRunner(
            config=config,
            state_store=state_store,
            http_client=http_client,
            oauth=oauth,
            logger=logger,
            eventsub_client=eventsub_client,
            ensure_subscription_fn=ensure_fn,
            handle_offline_fn=offline_fn,
        )

        # Run agent briefly then stop
        async def run_test() -> None:
            # Start in background
            task = asyncio.create_task(runner.run_async())
            # Let it connect and ensure
            await asyncio.sleep(0.1)
            # Stop
            runner.request_stop()
            await asyncio.sleep(0.1)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        asyncio.run(run_test())

        # Assert ensure_subscription was called exactly once
        ensure_fn.assert_called_once()
        call_args = ensure_fn.call_args
        self.assertEqual(call_args.kwargs["session_id"], "session_123")
        self.assertEqual(call_args.kwargs["broadcaster_id"], "12345")


class TestAgentRunnerNotificationDispatch(unittest.TestCase):
    """Test notification handling."""

    def test_dispatches_stream_offline_notification(self) -> None:
        """Should call offline handler for stream.offline notification."""
        from twitch_marker_agent.core.agent_runner import AgentRunner

        config = make_mock_config()
        state_store = MagicMock()
        http_client = MagicMock()
        oauth = MagicMock()
        oauth.get_valid_user_access_token.return_value = "test_token"
        logger = MagicMock(spec=logging.Logger)

        # Create notification queue
        notification_queue: asyncio.Queue[Any] = asyncio.Queue()

        # Mock EventSub client
        eventsub_client = MagicMock()
        eventsub_client.connect = AsyncMock(return_value="session_123")

        async def slow_run() -> None:
            # Just wait a while
            await asyncio.sleep(10)

        eventsub_client.run_until_stopped = AsyncMock(side_effect=slow_run)
        eventsub_client.stop = AsyncMock()
        eventsub_client.close = AsyncMock()

        # Mock subscription ensure
        ensure_fn = MagicMock()

        # Mock offline handler
        offline_fn = MagicMock()

        runner = AgentRunner(
            config=config,
            state_store=state_store,
            http_client=http_client,
            oauth=oauth,
            logger=logger,
            eventsub_client=eventsub_client,
            ensure_subscription_fn=ensure_fn,
            handle_offline_fn=offline_fn,
        )
        runner._notification_queue = notification_queue

        # Run agent and send notification
        async def run_test() -> None:
            # Start in background
            task = asyncio.create_task(runner.run_async())
            # Wait for startup
            await asyncio.sleep(0.1)

            # Send notification
            msg = make_mock_message()
            await notification_queue.put(msg)
            # Wait for processing
            await asyncio.sleep(0.2)

            # Stop
            runner.request_stop()
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        asyncio.run(run_test())

        # Assert offline handler was called
        offline_fn.assert_called_once()
        call_args = offline_fn.call_args
        self.assertEqual(call_args.kwargs["broadcaster_id"], "12345")

    def test_ignores_other_subscription_types(self) -> None:
        """Should ignore non stream.offline notifications."""
        from twitch_marker_agent.core.agent_runner import AgentRunner

        config = make_mock_config()
        oauth = MagicMock()
        oauth.get_valid_user_access_token.return_value = "test_token"
        logger = MagicMock(spec=logging.Logger)

        notification_queue: asyncio.Queue[Any] = asyncio.Queue()

        eventsub_client = MagicMock()
        eventsub_client.connect = AsyncMock(return_value="session_123")
        eventsub_client.run_until_stopped = AsyncMock(
            side_effect=lambda: asyncio.sleep(10)
        )
        eventsub_client.stop = AsyncMock()
        eventsub_client.close = AsyncMock()

        ensure_fn = MagicMock()
        offline_fn = MagicMock()

        runner = AgentRunner(
            config=config,
            state_store=MagicMock(),
            http_client=MagicMock(),
            oauth=oauth,
            logger=logger,
            eventsub_client=eventsub_client,
            ensure_subscription_fn=ensure_fn,
            handle_offline_fn=offline_fn,
        )
        runner._notification_queue = notification_queue

        async def run_test() -> None:
            task = asyncio.create_task(runner.run_async())
            await asyncio.sleep(0.1)

            # Send non-offline notification
            msg = make_mock_message(subscription_type="stream.online")
            await notification_queue.put(msg)
            await asyncio.sleep(0.1)

            runner.request_stop()
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        asyncio.run(run_test())

        # Offline handler should NOT be called
        offline_fn.assert_not_called()

    def test_ignores_other_broadcaster_id(self) -> None:
        """Should ignore notifications for other broadcasters."""
        from twitch_marker_agent.core.agent_runner import AgentRunner

        config = make_mock_config()
        config.broadcaster_id = "12345"
        oauth = MagicMock()
        oauth.get_valid_user_access_token.return_value = "test_token"
        logger = MagicMock(spec=logging.Logger)

        notification_queue: asyncio.Queue[Any] = asyncio.Queue()

        eventsub_client = MagicMock()
        eventsub_client.connect = AsyncMock(return_value="session_123")
        eventsub_client.run_until_stopped = AsyncMock(
            side_effect=lambda: asyncio.sleep(10)
        )
        eventsub_client.stop = AsyncMock()
        eventsub_client.close = AsyncMock()

        ensure_fn = MagicMock()
        offline_fn = MagicMock()

        runner = AgentRunner(
            config=config,
            state_store=MagicMock(),
            http_client=MagicMock(),
            oauth=oauth,
            logger=logger,
            eventsub_client=eventsub_client,
            ensure_subscription_fn=ensure_fn,
            handle_offline_fn=offline_fn,
        )
        runner._notification_queue = notification_queue

        async def run_test() -> None:
            task = asyncio.create_task(runner.run_async())
            await asyncio.sleep(0.1)

            # Send notification for different broadcaster
            msg = make_mock_message(broadcaster_id="99999")
            await notification_queue.put(msg)
            await asyncio.sleep(0.1)

            runner.request_stop()
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        asyncio.run(run_test())

        # Offline handler should NOT be called
        offline_fn.assert_not_called()


class TestAgentRunnerStop(unittest.TestCase):
    """Test stop behavior."""

    def test_request_stop_stops_loop(self) -> None:
        """Should call eventsub_client.stop when request_stop is called."""
        from twitch_marker_agent.core.agent_runner import AgentRunner

        config = make_mock_config()
        oauth = MagicMock()
        oauth.get_valid_user_access_token.return_value = "test_token"
        logger = MagicMock(spec=logging.Logger)

        # Track if run_until_stopped was awaited
        run_started = asyncio.Event()

        async def slow_run() -> None:
            run_started.set()
            await asyncio.sleep(10)

        eventsub_client = MagicMock()
        eventsub_client.connect = AsyncMock(return_value="session_123")
        eventsub_client.run_until_stopped = AsyncMock(side_effect=slow_run)
        eventsub_client.stop = AsyncMock()
        eventsub_client.close = AsyncMock()

        ensure_fn = MagicMock()

        runner = AgentRunner(
            config=config,
            state_store=MagicMock(),
            http_client=MagicMock(),
            oauth=oauth,
            logger=logger,
            eventsub_client=eventsub_client,
            ensure_subscription_fn=ensure_fn,
        )

        async def run_test() -> None:
            task = asyncio.create_task(runner.run_async())
            # Wait for run_until_stopped to start
            await asyncio.wait_for(run_started.wait(), timeout=2.0)

            # Now request stop
            runner.request_stop()
            await asyncio.sleep(0.1)

            # Client stop should be called
            eventsub_client.stop.assert_called()

            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        asyncio.run(run_test())


class TestAgentRunnerErrorHandling(unittest.TestCase):
    """Test error handling."""

    def test_handles_token_refresh_error(self) -> None:
        """Should set last_error and stop on token refresh failure."""
        from twitch_marker_agent.core.agent_runner import AgentRunner
        from twitch_marker_agent.core.twitch_oauth import TokenRefreshError

        config = make_mock_config()
        oauth = MagicMock()
        oauth.get_valid_user_access_token.side_effect = TokenRefreshError(
            "refresh failed"
        )
        logger = MagicMock(spec=logging.Logger)

        eventsub_client = MagicMock()
        eventsub_client.connect = AsyncMock(return_value="session_123")
        eventsub_client.close = AsyncMock()

        runner = AgentRunner(
            config=config,
            state_store=MagicMock(),
            http_client=MagicMock(),
            oauth=oauth,
            logger=logger,
            eventsub_client=eventsub_client,
        )

        asyncio.run(runner.run_async())

        self.assertFalse(runner.is_running)
        self.assertIsNotNone(runner.last_error)
        self.assertIn("auth", runner.last_error.lower())

    def test_handles_subscription_auth_error(self) -> None:
        """Should set last_error and stop on subscription auth failure."""
        from twitch_marker_agent.core.agent_runner import AgentRunner
        from twitch_marker_agent.core.eventsub_subscriptions import (
            SubscriptionAuthError,
        )

        config = make_mock_config()
        oauth = MagicMock()
        oauth.get_valid_user_access_token.return_value = "test_token"
        logger = MagicMock(spec=logging.Logger)

        eventsub_client = MagicMock()
        eventsub_client.connect = AsyncMock(return_value="session_123")
        eventsub_client.close = AsyncMock()

        ensure_fn = MagicMock(side_effect=SubscriptionAuthError("auth failed"))

        runner = AgentRunner(
            config=config,
            state_store=MagicMock(),
            http_client=MagicMock(),
            oauth=oauth,
            logger=logger,
            eventsub_client=eventsub_client,
            ensure_subscription_fn=ensure_fn,
        )

        asyncio.run(runner.run_async())

        self.assertFalse(runner.is_running)
        self.assertIsNotNone(runner.last_error)
        self.assertIn("auth", runner.last_error.lower())


class TestAgentRunnerNoSecrets(unittest.TestCase):
    """Test that no secrets are logged."""

    def test_no_secrets_in_logs(self) -> None:
        """Should not log tokens or secrets."""
        from twitch_marker_agent.core.agent_runner import AgentRunner
        from twitch_marker_agent.core.twitch_oauth import TokenRefreshError

        config = make_mock_config()
        config.client_secret = "super_secret_value"
        oauth = MagicMock()
        token = "secret_access_token_12345"
        oauth.get_valid_user_access_token.return_value = token
        logger = MagicMock(spec=logging.Logger)

        eventsub_client = MagicMock()
        eventsub_client.connect = AsyncMock(return_value="session_123")
        eventsub_client.run_until_stopped = AsyncMock(
            side_effect=lambda: asyncio.sleep(0.1)
        )
        eventsub_client.stop = AsyncMock()
        eventsub_client.close = AsyncMock()

        ensure_fn = MagicMock()

        runner = AgentRunner(
            config=config,
            state_store=MagicMock(),
            http_client=MagicMock(),
            oauth=oauth,
            logger=logger,
            eventsub_client=eventsub_client,
            ensure_subscription_fn=ensure_fn,
        )

        async def run_test() -> None:
            task = asyncio.create_task(runner.run_async())
            await asyncio.sleep(0.2)
            runner.request_stop()
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        asyncio.run(run_test())

        # Check all logger calls
        for method_name in ["info", "debug", "warning", "error"]:
            method = getattr(logger, method_name)
            for call in method.call_args_list:
                args = call.args if call.args else ()
                all_args = " ".join(str(a) for a in args)
                self.assertNotIn(token, all_args)
                self.assertNotIn("super_secret_value", all_args)


class TestAgentRunnerStopSignaling(unittest.TestCase):
    """Test thread-safe stop signaling."""

    def test_request_stop_uses_stored_loop(self) -> None:
        """Should use stored loop to call_soon_threadsafe the stop event."""
        from twitch_marker_agent.core.agent_runner import AgentRunner

        config = make_mock_config()
        logger = MagicMock(spec=logging.Logger)

        runner = AgentRunner(
            config=config,
            state_store=MagicMock(),
            http_client=MagicMock(),
            oauth=MagicMock(),
            logger=logger,
        )

        # Simulate state as if run_async() had started
        mock_loop = MagicMock()
        mock_stop_event = MagicMock()
        runner._loop = mock_loop
        runner._stop_event = mock_stop_event

        # Call request_stop from "tray thread"
        runner.request_stop()

        # Assert call_soon_threadsafe was called with stop_event.set
        mock_loop.call_soon_threadsafe.assert_called_once_with(
            mock_stop_event.set
        )

    @patch("twitch_marker_agent.core.agent_runner.asyncio.run_coroutine_threadsafe")
    def test_request_stop_schedules_async_client_stop(
        self, mock_run_coro: MagicMock
    ) -> None:
        """Should schedule async client.stop() using run_coroutine_threadsafe."""
        from twitch_marker_agent.core.agent_runner import AgentRunner

        config = make_mock_config()
        logger = MagicMock(spec=logging.Logger)

        # Create mock eventsub client with async stop
        mock_client = MagicMock()
        mock_client.stop = AsyncMock()

        runner = AgentRunner(
            config=config,
            state_store=MagicMock(),
            http_client=MagicMock(),
            oauth=MagicMock(),
            logger=logger,
            eventsub_client=mock_client,
        )

        # Simulate state as if run_async() had started
        mock_loop = MagicMock()
        mock_stop_event = MagicMock()
        runner._loop = mock_loop
        runner._stop_event = mock_stop_event

        # Call request_stop
        runner.request_stop()

        # Verify run_coroutine_threadsafe was called
        mock_run_coro.assert_called_once()
        call_args = mock_run_coro.call_args
        # First arg should be a coroutine, second should be the loop
        self.assertEqual(call_args.args[1], mock_loop)
        # Verify the coroutine is from client.stop()
        # (we can't easily inspect the coroutine object, but we know it was created)



class TestAgentRunnerRestartReliability(unittest.TestCase):
    """Test restart reliability via _reset_state()."""

    def test_restart_resets_state(self) -> None:
        """Should reset per-run state at start of run_async()."""
        from twitch_marker_agent.core.agent_runner import AgentRunner

        config = make_mock_config()
        oauth = MagicMock()
        oauth.get_valid_user_access_token.return_value = "test_token"
        logger = MagicMock(spec=logging.Logger)

        # Create a mock eventsub client for run
        async def slow_run() -> None:
            await asyncio.sleep(10)

        mock_client = MagicMock()
        mock_client.connect = AsyncMock(return_value="new_session")
        mock_client.run_until_stopped = AsyncMock(side_effect=slow_run)
        mock_client.stop = AsyncMock()
        mock_client.close = AsyncMock()

        # Create runner with mocked dependencies
        runner = AgentRunner(
            config=config,
            state_store=MagicMock(),
            http_client=MagicMock(),
            oauth=oauth,
            logger=logger,
            eventsub_client=mock_client,
            ensure_subscription_fn=MagicMock(),  # Mock to avoid real call
        )

        # Simulate state after a previous run
        runner._seen_message_ids.add("old_msg_123")
        runner._session_id = "old_session"
        runner._last_error = "previous error"

        async def run_test() -> None:
            task = asyncio.create_task(runner.run_async())
            await asyncio.sleep(0.1)

            # Verify state was reset (seen_message_ids cleared, loop set)
            self.assertEqual(len(runner._seen_message_ids), 0)
            self.assertIsNotNone(runner._loop)
            self.assertIsNotNone(runner._stop_event)

            runner.request_stop()
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        asyncio.run(run_test())


class TestAgentRunnerStopResponsive(unittest.TestCase):
    """Test that AgentRunner responds immediately to stop requests."""

    def test_exits_promptly_on_stop_request(self) -> None:
        """Should exit run_async promptly when request_stop is called."""
        from twitch_marker_agent.core.agent_runner import AgentRunner

        config = make_mock_config()
        oauth = MagicMock()
        oauth.get_valid_user_access_token.return_value = "test_token"
        logger = MagicMock(spec=logging.Logger)

        # Eventsub client that will not complete on its own
        async def never_complete() -> None:
            await asyncio.sleep(100)  # Long sleep

        mock_client = MagicMock()
        mock_client.connect = AsyncMock(return_value="session_123")
        mock_client.run_until_stopped = AsyncMock(side_effect=never_complete)
        mock_client.stop = AsyncMock()
        mock_client.close = AsyncMock()

        runner = AgentRunner(
            config=config,
            state_store=MagicMock(),
            http_client=MagicMock(),
            oauth=oauth,
            logger=logger,
            eventsub_client=mock_client,
            ensure_subscription_fn=MagicMock(),
        )

        async def run_test() -> None:
            import time

            task = asyncio.create_task(runner.run_async())
            await asyncio.sleep(0.1)  # Let it start

            # Request stop and measure time to exit
            start = time.time()
            runner.request_stop()
            await task  # Should complete quickly
            elapsed = time.time() - start

            # Should exit in under 1 second (immediate response)
            self.assertLess(elapsed, 1.0, "run_async should exit promptly on stop")
            self.assertFalse(runner.is_running)

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()

