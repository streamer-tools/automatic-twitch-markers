"""
Tests for tray controller module.

Uses stdlib unittest + mocks only; no real network calls or pystray.
"""

from __future__ import annotations

import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from twitch_marker_agent.tray_controller import (
    AutoModeState,
    TRAY_EDL_ENABLED_KEY,
    TRAY_OUTPUT_DIR_KEY,
    ManualFetchResult,
    TrayState,
    get_edl_enabled,
    get_export_formats_from_edl_flag,
    get_manual_fetch_formats,
    resolve_output_dir,
    run_manual_fetch,
    set_edl_enabled,
    set_output_dir,
    start_auto_mode,
    stop_auto_mode,
)


# =============================================================================
# Test Fixtures
# =============================================================================


def make_mock_config() -> MagicMock:
    """Create a mock AppConfig."""
    config = MagicMock()
    config.output_dir = Path(tempfile.gettempdir()) / "test_markers"
    config.export_formats = ("csv",)
    config.client_id = "test_client_id"
    config.broadcaster_id = "12345"
    config.timecode_fps = 24
    config.resolve_offset_enabled = False
    config.resolve_offset_timecode = "01:00:00:00"
    return config


def make_mock_state_store() -> MagicMock:
    """Create a mock StateStore."""
    store = MagicMock()
    store.get_state.return_value = None
    return store


def make_mock_oauth() -> MagicMock:
    """Create a mock TwitchOAuth."""
    oauth = MagicMock()
    oauth.get_valid_user_access_token.return_value = "test_access_token"
    return oauth


# =============================================================================
# Tests for resolve_output_dir
# =============================================================================


class TestResolveOutputDir(unittest.TestCase):
    """Tests for resolve_output_dir function."""

    def test_uses_state_store_if_set(self) -> None:
        """Should use StateStore value if it's a valid directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = make_mock_config()
            state_store = make_mock_state_store()
            state_store.get_state.return_value = tmpdir

            result = resolve_output_dir(config, state_store)

            self.assertEqual(result, Path(tmpdir))
            state_store.get_state.assert_called_once_with(TRAY_OUTPUT_DIR_KEY)

    def test_fallback_to_config(self) -> None:
        """Should fall back to config.output_dir if StateStore empty."""
        config = make_mock_config()
        state_store = make_mock_state_store()
        state_store.get_state.return_value = None

        result = resolve_output_dir(config, state_store)

        self.assertEqual(result, Path(config.output_dir))

    def test_invalid_state_falls_back(self) -> None:
        """Should fall back to config if StateStore path is invalid."""
        config = make_mock_config()
        state_store = make_mock_state_store()
        # Non-existent directory
        state_store.get_state.return_value = "/nonexistent/path/that/does/not/exist"

        result = resolve_output_dir(config, state_store)

        self.assertEqual(result, Path(config.output_dir))


# =============================================================================
# Tests for set_output_dir
# =============================================================================


class TestSetOutputDir(unittest.TestCase):
    """Tests for set_output_dir function."""

    def test_persists_to_state_store(self) -> None:
        """Should persist path to StateStore."""
        state_store = make_mock_state_store()
        output_dir = Path("/some/output/dir")

        set_output_dir(state_store, output_dir)

        state_store.set_state.assert_called_once_with(
            TRAY_OUTPUT_DIR_KEY, str(output_dir)
        )


# =============================================================================
# Tests for EDL Toggle Functions
# =============================================================================


class TestGetEdlEnabled(unittest.TestCase):
    """Tests for get_edl_enabled function."""

    def test_returns_false_by_default(self) -> None:
        """Should return False when StateStore has no value."""
        state_store = make_mock_state_store()
        state_store.get_state.return_value = None

        result = get_edl_enabled(state_store)

        self.assertFalse(result)
        state_store.get_state.assert_called_once_with(TRAY_EDL_ENABLED_KEY)

    def test_returns_true_for_true_string(self) -> None:
        """Should return True for 'true' string."""
        state_store = make_mock_state_store()
        state_store.get_state.return_value = "true"

        result = get_edl_enabled(state_store)

        self.assertTrue(result)

    def test_returns_true_for_one(self) -> None:
        """Should return True for '1' string."""
        state_store = make_mock_state_store()
        state_store.get_state.return_value = "1"

        result = get_edl_enabled(state_store)

        self.assertTrue(result)

    def test_returns_true_for_yes(self) -> None:
        """Should return True for 'yes' string."""
        state_store = make_mock_state_store()
        state_store.get_state.return_value = "yes"

        result = get_edl_enabled(state_store)

        self.assertTrue(result)

    def test_returns_false_for_false_string(self) -> None:
        """Should return False for 'false' string."""
        state_store = make_mock_state_store()
        state_store.get_state.return_value = "false"

        result = get_edl_enabled(state_store)

        self.assertFalse(result)

    def test_case_insensitive(self) -> None:
        """Should handle case-insensitive values."""
        state_store = make_mock_state_store()
        state_store.get_state.return_value = "TRUE"

        result = get_edl_enabled(state_store)

        self.assertTrue(result)


class TestSetEdlEnabled(unittest.TestCase):
    """Tests for set_edl_enabled function."""

    def test_persists_true(self) -> None:
        """Should store 'true' when enabled=True."""
        state_store = make_mock_state_store()

        set_edl_enabled(state_store, True)

        state_store.set_state.assert_called_once_with(TRAY_EDL_ENABLED_KEY, "true")

    def test_persists_false(self) -> None:
        """Should store 'false' when enabled=False."""
        state_store = make_mock_state_store()

        set_edl_enabled(state_store, False)

        state_store.set_state.assert_called_once_with(TRAY_EDL_ENABLED_KEY, "false")


class TestGetExportFormatsFromEdlFlag(unittest.TestCase):
    """Tests for get_export_formats_from_edl_flag function."""

    def test_csv_only_when_disabled(self) -> None:
        """Should return only CSV when EDL disabled."""
        result = get_export_formats_from_edl_flag(False)

        self.assertEqual(result, ("csv",))

    def test_csv_and_edl_when_enabled(self) -> None:
        """Should return CSV and EDL when EDL enabled."""
        result = get_export_formats_from_edl_flag(True)

        self.assertEqual(result, ("csv", "edl"))


# =============================================================================
# Tests for get_manual_fetch_formats
# =============================================================================



class TestGetManualFetchFormats(unittest.TestCase):
    """Tests for get_manual_fetch_formats function."""

    def test_csv_only_when_edl_disabled(self) -> None:
        """Should return only CSV when EDL disabled."""
        config = make_mock_config()

        result = get_manual_fetch_formats(config, edl_enabled=False)

        self.assertEqual(result, ("csv",))

    def test_csv_and_edl_when_edl_enabled(self) -> None:
        """Should return CSV and EDL when EDL enabled."""
        config = make_mock_config()

        result = get_manual_fetch_formats(config, edl_enabled=True)

        self.assertEqual(result, ("csv", "edl"))

    def test_config_parameter_unused(self) -> None:
        """Config parameter is present but unused (for future extensibility)."""
        config = make_mock_config()
        config.export_formats = ("csv", "edl")  # Config is ignored

        result = get_manual_fetch_formats(config, edl_enabled=False)

        self.assertEqual(result, ("csv",))  # Only CSV, EDL disabled




# =============================================================================
# Tests for run_manual_fetch
# =============================================================================


class TestRunManualFetch(unittest.TestCase):
    """Tests for run_manual_fetch function."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.logger = MagicMock(spec=logging.Logger)
        self.http_client = MagicMock()
        self.config = make_mock_config()
        self.state_store = make_mock_state_store()
        self.oauth = make_mock_oauth()
        self.output_dir = Path(tempfile.gettempdir()) / "test_export"
        self.export_formats = ("csv",)

    @patch("twitch_marker_agent.core.markers_api.get_latest_video_id")
    @patch("twitch_marker_agent.core.markers_api.get_stream_markers")
    @patch("twitch_marker_agent.core.export_csv.export_markers_csv")
    def test_calls_handler(
        self,
        mock_csv: MagicMock,
        mock_markers: MagicMock,
        mock_video: MagicMock,
    ) -> None:
        """Should call marker API and export functions."""
        from twitch_marker_agent.core.markers_api import Marker, MarkerVideo

        mock_video.return_value = "vid_123"
        mock_markers.return_value = [
            MarkerVideo(
                "vid_123",
                [
                    Marker(
                        id="m1",
                        created_at="2026-02-04T12:00:00Z",
                        position_seconds=3600,
                        description="Test marker",
                    )
                ],
            )
        ]
        mock_csv.return_value = self.output_dir / "markers.csv"

        result = run_manual_fetch(
            http_client=self.http_client,
            config=self.config,
            state_store=self.state_store,
            oauth=self.oauth,
            output_dir=self.output_dir,
            export_formats=self.export_formats,
            logger=self.logger,
        )

        self.assertTrue(result.success)
        mock_video.assert_called_once()
        mock_markers.assert_called_once()
        mock_csv.assert_called_once()

    @patch("twitch_marker_agent.core.markers_api.get_latest_video_id")
    @patch("twitch_marker_agent.core.markers_api.get_stream_markers")
    @patch("twitch_marker_agent.core.export_csv.export_markers_csv")
    def test_uses_force_true(
        self,
        mock_csv: MagicMock,
        mock_markers: MagicMock,
        mock_video: MagicMock,
    ) -> None:
        """Should always export (no dedupe check for manual fetch)."""
        from twitch_marker_agent.core.markers_api import Marker, MarkerVideo

        mock_video.return_value = "vid_123"
        mock_markers.return_value = [
            MarkerVideo(
                "vid_123",
                [
                    Marker(
                        id="m1",
                        created_at="2026-02-04T12:00:00Z",
                        position_seconds=3600,
                        description="Test marker",
                    )
                ],
            )
        ]
        mock_csv.return_value = self.output_dir / "markers.csv"

        # Run twice - should export both times (no dedupe)
        result1 = run_manual_fetch(
            http_client=self.http_client,
            config=self.config,
            state_store=self.state_store,
            oauth=self.oauth,
            output_dir=self.output_dir,
            export_formats=self.export_formats,
            logger=self.logger,
        )
        result2 = run_manual_fetch(
            http_client=self.http_client,
            config=self.config,
            state_store=self.state_store,
            oauth=self.oauth,
            output_dir=self.output_dir,
            export_formats=self.export_formats,
            logger=self.logger,
        )

        self.assertTrue(result1.success)
        self.assertTrue(result2.success)
        self.assertEqual(mock_csv.call_count, 2)  # No dedupe

    def test_handles_token_error(self) -> None:
        """Should handle TokenRefreshError gracefully."""
        from twitch_marker_agent.core.twitch_oauth import TokenRefreshError

        self.oauth.get_valid_user_access_token.side_effect = TokenRefreshError(
            "Not authenticated"
        )

        result = run_manual_fetch(
            http_client=self.http_client,
            config=self.config,
            state_store=self.state_store,
            oauth=self.oauth,
            output_dir=self.output_dir,
            export_formats=self.export_formats,
            logger=self.logger,
        )

        self.assertFalse(result.success)
        self.assertIn("Not logged in", result.message)

    @patch("twitch_marker_agent.core.markers_api.get_latest_video_id")
    @patch("twitch_marker_agent.core.markers_api.get_stream_markers")
    def test_handles_fetch_error(
        self,
        mock_markers: MagicMock,
        mock_video: MagicMock,
    ) -> None:
        """Should handle MarkersFetchError gracefully."""
        from twitch_marker_agent.core.markers_api import MarkersFetchError

        mock_video.return_value = "vid_123"
        mock_markers.side_effect = MarkersFetchError("API error")

        result = run_manual_fetch(
            http_client=self.http_client,
            config=self.config,
            state_store=self.state_store,
            oauth=self.oauth,
            output_dir=self.output_dir,
            export_formats=self.export_formats,
            logger=self.logger,
        )

        self.assertFalse(result.success)
        self.assertIn("Failed to fetch", result.message)

    @patch("twitch_marker_agent.core.markers_api.get_latest_video_id")
    @patch("twitch_marker_agent.core.markers_api.get_stream_markers")
    def test_handles_auth_error(
        self,
        mock_markers: MagicMock,
        mock_video: MagicMock,
    ) -> None:
        """Should handle MarkersAuthError with reauth message."""
        from twitch_marker_agent.core.markers_api import MarkersAuthError

        mock_video.return_value = "vid_123"
        mock_markers.side_effect = MarkersAuthError("401 Unauthorized")

        result = run_manual_fetch(
            http_client=self.http_client,
            config=self.config,
            state_store=self.state_store,
            oauth=self.oauth,
            output_dir=self.output_dir,
            export_formats=self.export_formats,
            logger=self.logger,
        )

        self.assertFalse(result.success)
        self.assertIn("Re-auth required", result.message)
        self.assertIn("auth-login", result.message)

    @patch("twitch_marker_agent.core.markers_api.get_latest_video_id")
    @patch("twitch_marker_agent.core.markers_api.get_stream_markers")
    def test_auth_error_no_secrets(
        self,
        mock_markers: MagicMock,
        mock_video: MagicMock,
    ) -> None:
        """Should not log tokens in auth error path."""
        from twitch_marker_agent.core.markers_api import MarkersAuthError

        mock_video.return_value = "vid_123"
        mock_markers.side_effect = MarkersAuthError("401 Unauthorized")

        run_manual_fetch(
            http_client=self.http_client,
            config=self.config,
            state_store=self.state_store,
            oauth=self.oauth,
            output_dir=self.output_dir,
            export_formats=self.export_formats,
            logger=self.logger,
        )

        # Check all log calls don't contain token
        token = "test_access_token"
        for method_name in ["info", "debug", "warning", "error"]:
            method = getattr(self.logger, method_name)
            for call in method.call_args_list:
                args = call.args if call.args else ()
                all_args = " ".join(str(a) for a in args)
                self.assertNotIn(token, all_args)

    @patch("twitch_marker_agent.core.markers_api.get_latest_video_id")
    @patch("twitch_marker_agent.core.markers_api.get_stream_markers")
    @patch("twitch_marker_agent.core.export_csv.export_markers_csv")
    def test_no_secrets_in_logs(
        self,
        mock_csv: MagicMock,
        mock_markers: MagicMock,
        mock_video: MagicMock,
    ) -> None:
        """Should not log tokens or secrets."""
        from twitch_marker_agent.core.markers_api import Marker, MarkerVideo

        mock_video.return_value = "vid_123"
        mock_markers.return_value = [
            MarkerVideo(
                "vid_123",
                [
                    Marker(
                        id="m1",
                        created_at="2026-02-04T12:00:00Z",
                        position_seconds=3600,
                        description="Test marker",
                    )
                ],
            )
        ]
        mock_csv.return_value = self.output_dir / "markers.csv"

        run_manual_fetch(
            http_client=self.http_client,
            config=self.config,
            state_store=self.state_store,
            oauth=self.oauth,
            output_dir=self.output_dir,
            export_formats=self.export_formats,
            logger=self.logger,
        )

        # Check all log calls don't contain token
        token = "test_access_token"
        for method_name in ["info", "debug", "warning", "error"]:
            method = getattr(self.logger, method_name)
            for call in method.call_args_list:
                args = call.args if call.args else ()
                all_args = " ".join(str(a) for a in args)
                self.assertNotIn(token, all_args)


# =============================================================================
# Tests for TrayState dataclass
# =============================================================================


class TestTrayState(unittest.TestCase):
    """Tests for TrayState dataclass."""

    def test_default_values(self) -> None:
        """Should have correct default values."""
        state = TrayState()

        self.assertEqual(state.selected_formats, [])
        self.assertFalse(state.is_fetching)
        self.assertIsNone(state.last_fetch_result)


# =============================================================================
# Tests for AutoModeState and start/stop functions
# =============================================================================


class TestAutoModeState(unittest.TestCase):
    """Tests for AutoModeState dataclass."""

    def test_default_values(self) -> None:
        """Should have correct default values."""
        state = AutoModeState()

        self.assertFalse(state.is_running)
        self.assertIsNone(state.thread)
        self.assertIsNone(state.last_error)


class TestStartAutoMode(unittest.TestCase):
    """Tests for start_auto_mode function."""

    def test_spawns_thread_once(self) -> None:
        """Should create and start worker thread."""
        state = AutoModeState()
        agent = MagicMock()
        agent.run_async = MagicMock(return_value=MagicMock())  # Coroutine-like
        logger = MagicMock(spec=logging.Logger)

        # Patch asyncio.run to avoid actual async execution
        with patch("twitch_marker_agent.tray_controller.asyncio.run"):
            new_state = start_auto_mode(state, agent, logger)

        self.assertTrue(new_state.is_running)
        self.assertIsNotNone(new_state.thread)
        self.assertIsNone(new_state.last_error)
        logger.info.assert_called()

    def test_noop_when_running(self) -> None:
        """Should return same state if already running."""
        state = AutoModeState(is_running=True, thread=MagicMock())
        agent = MagicMock()
        logger = MagicMock(spec=logging.Logger)

        new_state = start_auto_mode(state, agent, logger)

        self.assertIs(new_state, state)
        logger.debug.assert_called()


class TestStopAutoMode(unittest.TestCase):
    """Tests for stop_auto_mode function."""

    def test_calls_request_stop_and_joins(self) -> None:
        """Should call agent.request_stop and join thread."""
        mock_thread = MagicMock()
        mock_thread.is_alive.return_value = False
        state = AutoModeState(is_running=True, thread=mock_thread)
        agent = MagicMock()
        agent.last_error = None
        logger = MagicMock(spec=logging.Logger)

        new_state = stop_auto_mode(state, agent, logger)

        agent.request_stop.assert_called_once()
        mock_thread.join.assert_called_once()
        self.assertFalse(new_state.is_running)
        self.assertIsNone(new_state.thread)

    def test_noop_when_not_running(self) -> None:
        """Should return same state if not running."""
        state = AutoModeState(is_running=False)
        agent = MagicMock()
        logger = MagicMock(spec=logging.Logger)

        new_state = stop_auto_mode(state, agent, logger)

        self.assertIs(new_state, state)
        agent.request_stop.assert_not_called()

    def test_timeout_records_warning(self) -> None:
        """Should log warning if thread doesn't exit in time."""
        mock_thread = MagicMock()
        mock_thread.is_alive.return_value = True  # Thread still running
        state = AutoModeState(is_running=True, thread=mock_thread)
        agent = MagicMock()
        agent.last_error = None
        logger = MagicMock(spec=logging.Logger)

        new_state = stop_auto_mode(state, agent, logger, timeout_seconds=0.1)

        # Should still mark as stopped despite timeout
        self.assertFalse(new_state.is_running)
        logger.warning.assert_called()

    def test_no_secrets_in_logs(self) -> None:
        """Should not log tokens in auto mode paths."""
        mock_thread = MagicMock()
        mock_thread.is_alive.return_value = False
        state = AutoModeState(is_running=True, thread=mock_thread)
        agent = MagicMock()
        agent.last_error = "secret_token_12345"  # Simulate error with secret
        logger = MagicMock(spec=logging.Logger)

        # Note: last_error might contain user-facing message
        # but should never contain raw token value
        new_state = stop_auto_mode(state, agent, logger)

        # Check log calls don't contain tokens
        for method_name in ["info", "debug", "warning", "error"]:
            method = getattr(logger, method_name)
            for call in method.call_args_list:
                args = call.args if call.args else ()
                all_args = " ".join(str(a) for a in args)
                # Token values should not appear in log messages
                self.assertNotIn("secret_token_12345", all_args)


class TestAutoModeStatusChecks(unittest.TestCase):
    """Test that status derives from thread.is_alive()."""

    def test_status_checks_thread_is_alive(self) -> None:
        """Should derive running state from thread.is_alive()."""
        # Simulate menu predicates logic from app.py

        # Case 1: Thread alive -> running
        mock_thread_alive = MagicMock()
        mock_thread_alive.is_alive.return_value = True
        auto_state = AutoModeState(is_running=True, thread=mock_thread_alive)

        # Replicate the predicate logic
        thread_alive = (
            auto_state.thread is not None and auto_state.thread.is_alive()
        )
        is_stopped = auto_state.thread is None or not auto_state.thread.is_alive()
        is_running = auto_state.thread is not None and auto_state.thread.is_alive()

        self.assertTrue(thread_alive)
        self.assertFalse(is_stopped)
        self.assertTrue(is_running)

        # Case 2: Thread dead -> stopped
        mock_thread_dead = MagicMock()
        mock_thread_dead.is_alive.return_value = False
        auto_state2 = AutoModeState(is_running=True, thread=mock_thread_dead)

        thread_alive2 = (
            auto_state2.thread is not None and auto_state2.thread.is_alive()
        )
        is_stopped2 = auto_state2.thread is None or not auto_state2.thread.is_alive()
        is_running2 = auto_state2.thread is not None and auto_state2.thread.is_alive()

        self.assertFalse(thread_alive2)
        self.assertTrue(is_stopped2)
        self.assertFalse(is_running2)

    def test_dead_thread_shows_stopped(self) -> None:
        """Should show stopped when thread died even if is_running flag is True."""
        # This tests the stale flag scenario

        # AutoModeState with is_running=True but thread is dead
        mock_dead_thread = MagicMock()
        mock_dead_thread.is_alive.return_value = False
        auto_state = AutoModeState(
            is_running=True,  # Stale flag!
            thread=mock_dead_thread,
            last_error="Connection lost",
        )

        # UI predicates should derive from thread, not flag
        is_stopped = auto_state.thread is None or not auto_state.thread.is_alive()
        is_running = auto_state.thread is not None and auto_state.thread.is_alive()

        # Despite is_running=True, predicates should show stopped
        self.assertTrue(is_stopped)
        self.assertFalse(is_running)

        # Status should show error
        if auto_state.thread is not None and auto_state.thread.is_alive():
            status = "Auto: Running"
        elif auto_state.last_error:
            status = "Auto: Error"
        else:
            status = "Auto: Stopped"

        self.assertEqual(status, "Auto: Error")


# =============================================================================
# Tests for stop_auto_mode
# =============================================================================


class TestStopAutoMode(unittest.TestCase):
    """Tests for stop_auto_mode function."""

    def test_keeps_accurate_state_on_timeout(self) -> None:
        """Should keep thread and is_running=True when timeout occurs."""
        import threading
        import time

        # Create a mock agent that responds to request_stop
        agent = unittest.mock.MagicMock()
        agent.last_error = None
        agent.request_stop = unittest.mock.MagicMock()

        # Create a thread that won't exit promptly
        def slow_worker() -> None:
            time.sleep(10)  # Long sleep

        thread = threading.Thread(target=slow_worker, daemon=True)
        thread.start()

        # Initial state with running thread
        state = AutoModeState(
            is_running=True,
            thread=thread,
            last_error=None,
        )

        logger = unittest.mock.MagicMock(spec=logging.Logger)

        # Call stop_auto_mode with very short timeout
        result = stop_auto_mode(state, agent, logger, timeout_seconds=0.1)

        # Verify state accurately reflects thread still running
        self.assertTrue(result.is_running, "Should report is_running=True when thread doesn't exit")
        self.assertIsNotNone(result.thread, "Should keep thread reference")
        self.assertIs(result.thread, thread, "Should keep same thread reference")
        self.assertIsNotNone(result.last_error)
        self.assertIn("not exit", result.last_error)

        # Verify agent.request_stop was called
        agent.request_stop.assert_called_once()

    def test_marks_stopped_when_thread_exits(self) -> None:
        """Should mark stopped when thread exits within timeout."""
        import threading
        import time

        agent = unittest.mock.MagicMock()
        agent.last_error = "some error"
        agent.request_stop = unittest.mock.MagicMock()

        # Create a thread that exits quickly
        def quick_worker() -> None:
            time.sleep(0.05)

        thread = threading.Thread(target=quick_worker, daemon=True)
        thread.start()

        state = AutoModeState(
            is_running=True,
            thread=thread,
            last_error=None,
        )

        logger = unittest.mock.MagicMock(spec=logging.Logger)

        # Call with sufficient timeout
        result = stop_auto_mode(state, agent, logger, timeout_seconds=1.0)

        # Verify clean stop
        self.assertFalse(result.is_running)
        self.assertIsNone(result.thread)
        self.assertEqual(result.last_error, "some error")  # From agent


if __name__ == "__main__":
    unittest.main()

