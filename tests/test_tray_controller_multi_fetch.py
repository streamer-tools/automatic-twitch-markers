"""
Unit tests for tray_controller multi-fetch functions.

Tests validate_date_range and run_multandfetch with various scenarios.
"""

import logging
from datetime import date, timedelta
from pathlib import Path
import unittest
from unittest.mock import MagicMock, Mock, call

# Create mock objects for dependencies
mock_config = MagicMock()
mock_config.client_id = "test_client"
mock_config.broadcaster_id = "123456"


class TestValidateDateRange(unittest.TestCase):
    """Tests for validate_date_range function."""

    def setUp(self):
        """Set up test fixtures."""
        from twitch_marker_agent import tray_controller

        self.tray_controller = tray_controller
        self.today = date.today()

    def test_valid_range_within_last_60_days(self):
        """Should return valid for range within last 60 days."""
        start = self.today - timedelta(days=30)
        end = self.today - timedelta(days=5)

        is_valid, error_msg = self.tray_controller.validate_date_range(start, end)

        self.assertTrue(is_valid)
        self.assertEqual(error_msg, "")

    def test_start_after_end_invalid(self):
        """Should return invalid when start > end."""
        start = self.today - timedelta(days=5)
        end = self.today - timedelta(days=10)

        is_valid, error_msg = self.tray_controller.validate_date_range(start, end)

        self.assertFalse(is_valid)
        self.assertIn("must be before or equal to", error_msg)

    def test_end_in_future_invalid(self):
        """Should return invalid when end is in future."""
        start = self.today - timedelta(days=10)
        end = self.today + timedelta(days=1)

        is_valid, error_msg = self.tray_controller.validate_date_range(start, end)

        self.assertFalse(is_valid)
        self.assertIn("cannot be in the future", error_msg)

    def test_start_too_old_invalid(self):
        """Should return invalid when start is more than max_days_back."""
        start = self.today - timedelta(days=61)
        end = self.today

        is_valid, error_msg = self.tray_controller.validate_date_range(start, end, max_days_back=60)

        self.assertFalse(is_valid)
        self.assertIn("cannot be more than 60 days ago", error_msg)

    def test_boundary_cases_valid(self):
        """Should return valid for boundary cases."""
        # Start exactly 60 days ago, end today
        start = self.today - timedelta(days=60)
        end = self.today

        is_valid, error_msg = self.tray_controller.validate_date_range(start, end, max_days_back=60)

        self.assertTrue(is_valid)
        self.assertEqual(error_msg, "")


class TestRunMultiFetch(unittest.TestCase):
    """Tests for run_multi_fetch function."""

    def setUp(self):
        """Set up test fixtures."""
        from twitch_marker_agent import tray_controller

        self.tray_controller = tray_controller
        self.http_client = MagicMock()
        self.config = mock_config
        self.state_store = MagicMock()
        self.oauth = MagicMock()
        self.output_dir = Path("test_output")
        self.export_formats = ("csv",)
        self.logger = logging.getLogger("test")

    def tearDown(self):
        """Clean up."""
        # Note: test output dir is not created in these unit tests (all mocked)
        pass

    def test_no_vods_found(self):
        """Should return success with 0 VODs when no videos found."""
        from twitch_marker_agent.core.videos_api import ArchivedVideo
        from datetime import datetime, timezone

        self.oauth.get_valid_user_access_token.return_value = "test_token"

        # Mock list_videos_in_date_range - it's imported locally in run_multi_fetch
        with unittest.mock.patch(
            "twitch_marker_agent.core.videos_api.list_videos_in_date_range"
        ) as mock_list_videos:
            mock_list_videos.return_value = []

            # Use recent dates to avoid validation errors
            start_date = date.today() - timedelta(days=14)
            end_date = date.today() - timedelta(days=7)

            result = self.tray_controller.run_multi_fetch(
                http_client=self.http_client,
                config=self.config,
                state_store=self.state_store,
                oauth=self.oauth,
                output_dir=self.output_dir,
                export_formats=self.export_formats,
                start_date=start_date,
                end_date=end_date,
                logger=self.logger,
            )

        self.assertTrue(result.success)
        self.assertEqual(result.total_vods, 0)
        self.assertIn("No VODs found", result.message)

    def test_token_refresh_error(self):
        """Should return error result when token refresh fails."""
        from twitch_marker_agent.core.twitch_oauth import TokenRefreshError

        self.oauth.get_valid_user_access_token.side_effect = TokenRefreshError("Not authenticated")

        # Use recent dates to avoid validation errors
        start_date = date.today() - timedelta(days=14)
        end_date = date.today() - timedelta(days=7)

        result = self.tray_controller.run_multi_fetch(
            http_client=self.http_client,
            config=self.config,
            state_store=self.state_store,
            oauth=self.oauth,
            output_dir=self.output_dir,
            export_formats=self.export_formats,
            start_date=start_date,
            end_date=end_date,
            logger=self.logger,
        )

        self.assertFalse(result.success)
        self.assertIn("Not logged in", result.message)

    def test_export_call_signature_csv(self):
        """Should call export_markers_csv with correct kwargs (output_path, config, video_id)."""
        from twitch_marker_agent.core.videos_api import ArchivedVideo
        from twitch_marker_agent.core.markers_api import MarkerVideo, Marker
        from datetime import datetime, timezone

        self.oauth.get_valid_user_access_token.return_value = "test_token"
        self.config.resolve_offset_enabled = False

        # Create test data
        test_video = ArchivedVideo(
            video_id="video123",
            title="Test Stream",
            created_at=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
            url="https://twitch.tv/videos/video123",
        )
        test_marker = Marker(
            id="marker1",
            created_at="2024-01-15T12:05:00Z",
            position_seconds=300,
            description="Test marker",
            user_type="broadcaster",
            username="testuser",
        )
        test_marker_video = MarkerVideo(video_id="video123", markers=[test_marker])

        start_date = date.today() - timedelta(days=14)
        end_date = date.today() - timedelta(days=7)

        with unittest.mock.patch(
            "twitch_marker_agent.core.videos_api.list_videos_in_date_range"
        ) as mock_list, unittest.mock.patch(
            "twitch_marker_agent.core.markers_api.get_stream_markers"
        ) as mock_markers, unittest.mock.patch(
            "twitch_marker_agent.core.export_csv.export_markers_csv"
        ) as mock_csv:
            mock_list.return_value = [test_video]
            mock_markers.return_value = [test_marker_video]
            mock_csv.return_value = Path("test.csv")

            self.tray_controller.run_multi_fetch(
                http_client=self.http_client,
                config=self.config,
                state_store=self.state_store,
                oauth=self.oauth,
                output_dir=self.output_dir,
                export_formats=("csv",),
                start_date=start_date,
                end_date=end_date,
                logger=self.logger,
            )

            # Assert export_markers_csv was called with correct kwargs
            mock_csv.assert_called_once()
            call_kwargs = mock_csv.call_args.kwargs
            self.assertIn("output_path", call_kwargs)
            self.assertIn("config", call_kwargs)
            self.assertIn("video_id", call_kwargs)
            self.assertEqual(call_kwargs["video_id"], "video123")

    def test_export_with_edl_offset(self):
        """Should call export_markers_edl with timecode_offset_seconds when enabled."""
        from twitch_marker_agent.core.videos_api import ArchivedVideo
        from twitch_marker_agent.core.markers_api import MarkerVideo, Marker
        from datetime import datetime, timezone

        self.oauth.get_valid_user_access_token.return_value = "test_token"
        self.config.resolve_offset_enabled = True
        self.config.resolve_offset_timecode = "01:00:00:00"  # 3600 seconds

        test_video = ArchivedVideo(
            video_id="video456",
            title="EDL Test",
            created_at=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
            url="https://twitch.tv/videos/video456",
        )
        test_marker = Marker(
            id="marker1",
            created_at="2024-01-15T12:01:40Z",
            position_seconds=100,
            description="Test",
            user_type="broadcaster",
            username="testuser",
        )
        test_marker_video = MarkerVideo(video_id="video456", markers=[test_marker])

        start_date = date.today() - timedelta(days=14)
        end_date = date.today() - timedelta(days=7)

        with unittest.mock.patch(
            "twitch_marker_agent.core.videos_api.list_videos_in_date_range"
        ) as mock_list, unittest.mock.patch(
            "twitch_marker_agent.core.markers_api.get_stream_markers"
        ) as mock_markers, unittest.mock.patch(
            "twitch_marker_agent.core.export_edl.export_markers_edl"
        ) as mock_edl:
            mock_list.return_value = [test_video]
            mock_markers.return_value = [test_marker_video]
            mock_edl.return_value = Path("test.edl")

            self.tray_controller.run_multi_fetch(
                http_client=self.http_client,
                config=self.config,
                state_store=self.state_store,
                oauth=self.oauth,
                output_dir=self.output_dir,
                export_formats=("edl",),
                start_date=start_date,
                end_date=end_date,
                logger=self.logger,
            )

            mock_edl.assert_called_once()
            call_kwargs = mock_edl.call_args.kwargs
            self.assertIn("timecode_offset_seconds", call_kwargs)
            self.assertEqual(call_kwargs["timecode_offset_seconds"], 3600)

    def test_vod_success_only_when_exported(self):
        """VOD should only count as successful if at least one export succeeds."""
        from twitch_marker_agent.core.videos_api import ArchivedVideo
        from twitch_marker_agent.core.markers_api import MarkerVideo, Marker
        from datetime import datetime, timezone

        self.oauth.get_valid_user_access_token.return_value = "test_token"
        self.config.resolve_offset_enabled = False

        test_video = ArchivedVideo(
            video_id="video789",
            title="Fail Test",
            created_at=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
            url="https://twitch.tv/videos/video789",
        )
        test_marker = Marker(
            id="marker1",
            created_at="2024-01-15T12:01:40Z",
            position_seconds=100,
            description="Test",
            user_type="broadcaster",
            username="testuser",
        )
        test_marker_video = MarkerVideo(video_id="video789", markers=[test_marker])

        start_date = date.today() - timedelta(days=14)
        end_date = date.today() - timedelta(days=7)

        with unittest.mock.patch(
            "twitch_marker_agent.core.videos_api.list_videos_in_date_range"
        ) as mock_list, unittest.mock.patch(
            "twitch_marker_agent.core.markers_api.get_stream_markers"
        ) as mock_markers, unittest.mock.patch(
            "twitch_marker_agent.core.export_csv.export_markers_csv"
        ) as mock_csv:
            mock_list.return_value = [test_video]
            mock_markers.return_value = [test_marker_video]
            mock_csv.side_effect = Exception("Export failed")  # Force failure

            result = self.tray_controller.run_multi_fetch(
                http_client=self.http_client,
                config=self.config,
                state_store=self.state_store,
                oauth=self.oauth,
                output_dir=self.output_dir,
                export_formats=("csv",),
                start_date=start_date,
                end_date=end_date,
                logger=self.logger,
            )

            # VOD should be counted as failed, not successful
            self.assertEqual(result.failed_vods, 1)
            self.assertEqual(result.successful_vods, 0)


if __name__ == "__main__":
    unittest.main()
