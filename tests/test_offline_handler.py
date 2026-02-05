"""
Tests for stream offline handler module.

Uses stdlib unittest + mocks only; no real network connections.
"""

from __future__ import annotations

import logging
import tempfile
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch, call

from twitch_marker_agent.core.markers_api import (
    Marker,
    MarkerVideo,
    MarkersAuthError,
    MarkersFetchError,
    MarkersNotFoundError,
    MarkersRateLimitError,
)
from twitch_marker_agent.core.offline_handler import (
    DEFAULT_BASE_DELAY,
    DEFAULT_MAX_ATTEMPTS,
    MarkerExportResult,
    handle_stream_offline,
    should_handle_notification,
    _get_broadcaster_id_from_message,
    _make_processed_key,
)


# =============================================================================
# Test Fixtures
# =============================================================================


@dataclass
class MockEventSubMessage:
    """Mock EventSubMessage for testing."""

    message_type: str = "notification"
    subscription_type: str | None = "stream.offline"
    message_id: str | None = "msg_123"
    payload: dict[str, Any] = field(default_factory=dict)


def make_offline_message(
    broadcaster_id: str = "12345",
    message_id: str = "msg_123",
) -> MockEventSubMessage:
    """Create a mock stream.offline notification message."""
    return MockEventSubMessage(
        message_type="notification",
        subscription_type="stream.offline",
        message_id=message_id,
        payload={
            "subscription": {
                "type": "stream.offline",
                "condition": {"broadcaster_user_id": broadcaster_id},
            },
            "event": {
                "broadcaster_user_id": broadcaster_id,
                "broadcaster_user_login": "testuser",
                "broadcaster_user_name": "TestUser",
            },
        },
    )


def make_mock_config() -> MagicMock:
    """Create a mock AppConfig."""
    config = MagicMock()
    config.client_id = "test_client_id"
    config.output_dir = Path(tempfile.gettempdir()) / "test_markers"
    config.export_formats = ("csv",)
    config.timecode_fps = 24
    return config


def make_markers() -> list[Marker]:
    """Create sample markers."""
    return [
        Marker(
            id="m1",
            created_at="2026-02-04T12:00:00Z",
            position_seconds=3600,
            description="First marker",
        ),
        Marker(
            id="m2",
            created_at="2026-02-04T12:30:00Z",
            position_seconds=5400,
            description="Second marker",
        ),
    ]


# =============================================================================
# Tests for should_handle_notification
# =============================================================================


class TestShouldHandleNotification(unittest.TestCase):
    """Tests for should_handle_notification function."""

    def test_accepts_valid_offline_notification(self) -> None:
        """Should accept valid stream.offline for correct broadcaster."""
        message = make_offline_message(broadcaster_id="12345")
        result = should_handle_notification(
            message=message,
            expected_broadcaster_id="12345",
        )
        self.assertTrue(result)

    def test_rejects_non_notification_type(self) -> None:
        """Should reject non-notification message types."""
        message = MockEventSubMessage(
            message_type="session_keepalive",
            subscription_type="stream.offline",
        )
        result = should_handle_notification(
            message=message,
            expected_broadcaster_id="12345",
        )
        self.assertFalse(result)

    def test_rejects_non_offline_subscription(self) -> None:
        """Should reject non stream.offline subscriptions."""
        message = MockEventSubMessage(
            message_type="notification",
            subscription_type="stream.online",
            payload={"event": {"broadcaster_user_id": "12345"}},
        )
        result = should_handle_notification(
            message=message,
            expected_broadcaster_id="12345",
        )
        self.assertFalse(result)

    def test_rejects_wrong_broadcaster(self) -> None:
        """Should reject notifications for other broadcasters."""
        message = make_offline_message(broadcaster_id="99999")
        result = should_handle_notification(
            message=message,
            expected_broadcaster_id="12345",
        )
        self.assertFalse(result)

    def test_rejects_seen_message_id(self) -> None:
        """Should reject already-seen message IDs."""
        message = make_offline_message(message_id="seen_msg")
        seen_ids = {"seen_msg"}

        result = should_handle_notification(
            message=message,
            expected_broadcaster_id="12345",
            seen_message_ids=seen_ids,
        )
        self.assertFalse(result)

    def test_adds_message_id_to_seen_set(self) -> None:
        """Should add new message_id to seen set."""
        message = make_offline_message(message_id="new_msg")
        seen_ids: set[str] = set()

        should_handle_notification(
            message=message,
            expected_broadcaster_id="12345",
            seen_message_ids=seen_ids,
        )

        self.assertIn("new_msg", seen_ids)


# =============================================================================
# Tests for handle_stream_offline
# =============================================================================


class TestHandleStreamOffline(unittest.TestCase):
    """Tests for handle_stream_offline function."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.logger = MagicMock(spec=logging.Logger)
        self.http_client = MagicMock()
        self.config = make_mock_config()
        self.state_store = MagicMock()
        self.state_store.get_state.return_value = None  # Not processed
        self.access_token = "test_token"
        self.broadcaster_id = "12345"

    @patch("twitch_marker_agent.core.offline_handler.get_latest_video_id")
    @patch("twitch_marker_agent.core.offline_handler.get_stream_markers")
    @patch("twitch_marker_agent.core.offline_handler.export_markers_csv")
    def test_success_exports_markers(
        self,
        mock_export: MagicMock,
        mock_markers: MagicMock,
        mock_video: MagicMock,
    ) -> None:
        """Should fetch and export markers successfully."""
        mock_video.return_value = "vid_123"
        mock_markers.return_value = [MarkerVideo("vid_123", make_markers())]
        mock_export.return_value = Path("/tmp/markers.csv")

        result = handle_stream_offline(
            http_client=self.http_client,
            config=self.config,
            access_token=self.access_token,
            broadcaster_id=self.broadcaster_id,
            state_store=self.state_store,
            logger=self.logger,
            max_attempts=1,  # No retries for speed
        )

        self.assertEqual(result.video_id, "vid_123")
        self.assertEqual(result.marker_count, 2)
        self.assertEqual(len(result.export_paths), 1)
        self.assertFalse(result.skipped)

    @patch("twitch_marker_agent.core.offline_handler.get_latest_video_id")
    @patch("twitch_marker_agent.core.offline_handler.get_stream_markers")
    @patch("twitch_marker_agent.core.offline_handler.export_markers_csv")
    def test_marks_video_as_processed(
        self,
        mock_export: MagicMock,
        mock_markers: MagicMock,
        mock_video: MagicMock,
    ) -> None:
        """Should mark video as processed in state store."""
        mock_video.return_value = "vid_123"
        mock_markers.return_value = [MarkerVideo("vid_123", make_markers())]
        mock_export.return_value = Path("/tmp/markers.csv")

        handle_stream_offline(
            http_client=self.http_client,
            config=self.config,
            access_token=self.access_token,
            broadcaster_id=self.broadcaster_id,
            state_store=self.state_store,
            logger=self.logger,
            max_attempts=1,
        )

        # Verify set_state was called with processed key
        self.state_store.set_state.assert_called()
        call_args = self.state_store.set_state.call_args
        self.assertIn("processed_video", call_args[0][0])

    @patch("twitch_marker_agent.core.offline_handler.get_latest_video_id")
    def test_skips_if_no_vod(self, mock_video: MagicMock) -> None:
        """Should skip if no VOD found."""
        mock_video.return_value = None

        result = handle_stream_offline(
            http_client=self.http_client,
            config=self.config,
            access_token=self.access_token,
            broadcaster_id=self.broadcaster_id,
            state_store=self.state_store,
            logger=self.logger,
        )

        self.assertTrue(result.skipped)
        self.assertIn("No VOD", result.skip_reason or "")

    @patch("twitch_marker_agent.core.offline_handler.get_latest_video_id")
    def test_skips_if_already_processed(self, mock_video: MagicMock) -> None:
        """Should skip if video already processed."""
        mock_video.return_value = "vid_123"
        self.state_store.get_state.return_value = "2026-02-04T00:00:00Z"

        result = handle_stream_offline(
            http_client=self.http_client,
            config=self.config,
            access_token=self.access_token,
            broadcaster_id=self.broadcaster_id,
            state_store=self.state_store,
            logger=self.logger,
        )

        self.assertTrue(result.skipped)
        self.assertIn("Already processed", result.skip_reason or "")

    @patch("twitch_marker_agent.core.offline_handler.get_latest_video_id")
    @patch("twitch_marker_agent.core.offline_handler.get_stream_markers")
    @patch("twitch_marker_agent.core.offline_handler.export_markers_csv")
    def test_skips_if_no_markers(
        self,
        mock_export: MagicMock,
        mock_markers: MagicMock,
        mock_video: MagicMock,
    ) -> None:
        """Should skip if video has no markers."""
        mock_video.return_value = "vid_123"
        mock_markers.return_value = [MarkerVideo("vid_123", [])]  # Empty markers

        result = handle_stream_offline(
            http_client=self.http_client,
            config=self.config,
            access_token=self.access_token,
            broadcaster_id=self.broadcaster_id,
            state_store=self.state_store,
            logger=self.logger,
            max_attempts=1,
        )

        self.assertTrue(result.skipped)
        self.assertIn("No markers", result.skip_reason or "")
        mock_export.assert_not_called()

    @patch("twitch_marker_agent.core.offline_handler.get_latest_video_id")
    @patch("twitch_marker_agent.core.offline_handler.get_stream_markers")
    @patch("twitch_marker_agent.core.offline_handler.export_markers_csv")
    @patch("twitch_marker_agent.core.retry.time.sleep")  # Mock sleep to speed up
    def test_retries_on_404(
        self,
        mock_sleep: MagicMock,
        mock_export: MagicMock,
        mock_markers: MagicMock,
        mock_video: MagicMock,
    ) -> None:
        """Should retry when markers not found (404)."""
        mock_video.return_value = "vid_123"
        # First call 404, second call success
        mock_markers.side_effect = [
            MarkersNotFoundError("Not found"),
            [MarkerVideo("vid_123", make_markers())],
        ]
        mock_export.return_value = Path("/tmp/markers.csv")

        result = handle_stream_offline(
            http_client=self.http_client,
            config=self.config,
            access_token=self.access_token,
            broadcaster_id=self.broadcaster_id,
            state_store=self.state_store,
            logger=self.logger,
            max_attempts=2,
            base_delay=0.1,
        )

        self.assertFalse(result.skipped)
        self.assertEqual(mock_markers.call_count, 2)

    @patch("twitch_marker_agent.core.offline_handler.get_latest_video_id")
    @patch("twitch_marker_agent.core.offline_handler.get_stream_markers")
    @patch("twitch_marker_agent.core.retry.time.sleep")
    def test_retries_on_429(
        self,
        mock_sleep: MagicMock,
        mock_markers: MagicMock,
        mock_video: MagicMock,
    ) -> None:
        """Should retry when rate limited (429)."""
        mock_video.return_value = "vid_123"
        # All calls rate limited
        mock_markers.side_effect = MarkersRateLimitError("Rate limited")

        with self.assertRaises(MarkersFetchError):
            handle_stream_offline(
                http_client=self.http_client,
                config=self.config,
                access_token=self.access_token,
                broadcaster_id=self.broadcaster_id,
                state_store=self.state_store,
                logger=self.logger,
                max_attempts=3,
                base_delay=0.1,
            )

        # Should have retried
        self.assertEqual(mock_markers.call_count, 3)

    @patch("twitch_marker_agent.core.offline_handler.get_latest_video_id")
    @patch("twitch_marker_agent.core.offline_handler.get_stream_markers")
    def test_does_not_retry_auth_error(
        self,
        mock_markers: MagicMock,
        mock_video: MagicMock,
    ) -> None:
        """Should not retry auth errors (401/403)."""
        mock_video.return_value = "vid_123"
        mock_markers.side_effect = MarkersAuthError("Token invalid")

        with self.assertRaises(MarkersAuthError):
            handle_stream_offline(
                http_client=self.http_client,
                config=self.config,
                access_token=self.access_token,
                broadcaster_id=self.broadcaster_id,
                state_store=self.state_store,
                logger=self.logger,
                max_attempts=3,
            )

        # Should not retry - only 1 call
        self.assertEqual(mock_markers.call_count, 1)

    def test_no_token_in_log_calls(self) -> None:
        """Verify that tokens are not included in log calls."""
        # Use the mock logger from setUp
        with patch("twitch_marker_agent.core.offline_handler.get_latest_video_id") as mock_video:
            mock_video.return_value = None  # No VOD, early exit

            handle_stream_offline(
                http_client=self.http_client,
                config=self.config,
                access_token="SECRET_TOKEN_12345",
                broadcaster_id=self.broadcaster_id,
                state_store=self.state_store,
                logger=self.logger,
            )

        # Check all log method calls don't contain token
        for method_name in ["info", "debug", "warning", "error"]:
            method = getattr(self.logger, method_name)
            for call in method.call_args_list:
                args = call.args if call.args else ()
                kwargs = call.kwargs if call.kwargs else {}
                all_args = " ".join(str(a) for a in args) + " ".join(str(v) for v in kwargs.values())
                self.assertNotIn("SECRET_TOKEN", all_args)


# =============================================================================
# Tests for Helper Functions
# =============================================================================


class TestHelperFunctions(unittest.TestCase):
    """Tests for helper functions."""

    def test_make_processed_key(self) -> None:
        """Should format processed key correctly."""
        key = _make_processed_key("broadcaster_123", "video_456")
        self.assertEqual(key, "processed_video:broadcaster_123:video_456")

    def test_get_broadcaster_id_from_message(self) -> None:
        """Should extract broadcaster ID from message payload."""
        message = make_offline_message(broadcaster_id="12345")
        result = _get_broadcaster_id_from_message(message)
        self.assertEqual(result, "12345")


# =============================================================================
# Tests for EDL Offset Wiring
# =============================================================================


class TestEdlOffsetWiring(unittest.TestCase):
    """Tests for resolve_offset_enabled + resolve_offset_timecode wiring."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.logger = MagicMock(spec=logging.Logger)
        self.http_client = MagicMock()
        self.state_store = MagicMock()
        self.state_store.get_state.return_value = None
        self.broadcaster_id = "12345"

    def _make_config(self, offset_enabled: bool, offset_timecode: str) -> MagicMock:
        """Create mock config with specific offset settings."""
        config = MagicMock()
        config.client_id = "test_client_id"
        config.output_dir = Path(tempfile.gettempdir()) / "test_markers_edl"
        config.export_formats = ("edl",)  # EDL only
        config.timecode_fps = 24
        config.resolve_offset_enabled = offset_enabled
        config.resolve_offset_timecode = offset_timecode
        return config

    @patch("twitch_marker_agent.core.offline_handler.get_latest_video_id")
    @patch("twitch_marker_agent.core.offline_handler.get_stream_markers")
    @patch("twitch_marker_agent.core.offline_handler.export_markers_edl")
    def test_offset_disabled_passes_zero(
        self,
        mock_export: MagicMock,
        mock_markers: MagicMock,
        mock_video: MagicMock,
    ) -> None:
        """When resolve_offset_enabled=False, should pass timecode_offset_seconds=0."""
        mock_video.return_value = "vid_123"
        mock_markers.return_value = [MarkerVideo("vid_123", make_markers())]
        mock_export.return_value = Path("/tmp/markers.edl")

        config = self._make_config(offset_enabled=False, offset_timecode="01:00:00:00")

        handle_stream_offline(
            http_client=self.http_client,
            config=config,
            access_token="token",
            broadcaster_id=self.broadcaster_id,
            state_store=self.state_store,
            logger=self.logger,
            max_attempts=1,
        )

        mock_export.assert_called_once()
        call_kwargs = mock_export.call_args.kwargs
        self.assertEqual(call_kwargs["timecode_offset_seconds"], 0)

    @patch("twitch_marker_agent.core.offline_handler.get_latest_video_id")
    @patch("twitch_marker_agent.core.offline_handler.get_stream_markers")
    @patch("twitch_marker_agent.core.offline_handler.export_markers_edl")
    def test_offset_enabled_parses_timecode(
        self,
        mock_export: MagicMock,
        mock_markers: MagicMock,
        mock_video: MagicMock,
    ) -> None:
        """When resolve_offset_enabled=True, should parse and pass timecode as seconds."""
        mock_video.return_value = "vid_123"
        mock_markers.return_value = [MarkerVideo("vid_123", make_markers())]
        mock_export.return_value = Path("/tmp/markers.edl")

        config = self._make_config(offset_enabled=True, offset_timecode="01:00:00:00")

        handle_stream_offline(
            http_client=self.http_client,
            config=config,
            access_token="token",
            broadcaster_id=self.broadcaster_id,
            state_store=self.state_store,
            logger=self.logger,
            max_attempts=1,
        )

        mock_export.assert_called_once()
        call_kwargs = mock_export.call_args.kwargs
        self.assertEqual(call_kwargs["timecode_offset_seconds"], 3600)

    @patch("twitch_marker_agent.core.offline_handler.get_latest_video_id")
    @patch("twitch_marker_agent.core.offline_handler.get_stream_markers")
    @patch("twitch_marker_agent.core.offline_handler.export_markers_edl")
    def test_invalid_timecode_falls_back_to_default(
        self,
        mock_export: MagicMock,
        mock_markers: MagicMock,
        mock_video: MagicMock,
    ) -> None:
        """When resolve_offset_timecode is invalid, should fall back to 3600."""
        mock_video.return_value = "vid_123"
        mock_markers.return_value = [MarkerVideo("vid_123", make_markers())]
        mock_export.return_value = Path("/tmp/markers.edl")

        config = self._make_config(offset_enabled=True, offset_timecode="invalid")

        handle_stream_offline(
            http_client=self.http_client,
            config=config,
            access_token="token",
            broadcaster_id=self.broadcaster_id,
            state_store=self.state_store,
            logger=self.logger,
            max_attempts=1,
        )

        # Should fall back to default 3600
        mock_export.assert_called_once()
        call_kwargs = mock_export.call_args.kwargs
        self.assertEqual(call_kwargs["timecode_offset_seconds"], 3600)

        # Should log a warning
        self.logger.warning.assert_called()
        warning_call = self.logger.warning.call_args
        self.assertIn("Invalid", warning_call[0][0])


if __name__ == "__main__":
    unittest.main()
