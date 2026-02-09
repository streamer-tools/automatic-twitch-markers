"""
Unit tests for core/videos_api.py

Tests list_videos_in_date_range function with various scenarios including
pagination, date filtering, error handling, and RFC3339 timestamp parsing.
"""

import json
from datetime import date, datetime, timezone
from pathlib import Path
import unittest
from unittest.mock import MagicMock, Mock

# Mock config before importing videos_api
mock_config = MagicMock()
mock_config.client_id = "test_client"


class TestListVideosInDateRange(unittest.TestCase):
    """Tests for list_videos_in_date_range function."""

    def setUp(self):
        """Set up test fixtures."""
        from twitch_marker_agent.core import videos_api

        self.videos_api = videos_api
        self.config = mock_config
        self.access_token = "test_token"
        self.user_id = "123456"

    def test_empty_results(self):
        """Should return empty list when API returns no data."""
        http_client = MagicMock()
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"data": [], "pagination": {}}
        http_client.get.return_value = response

        videos = self.videos_api.list_videos_in_date_range(
            http_client=http_client,
            config=self.config,
            access_token=self.access_token,
            user_id=self.user_id,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )

        self.assertEqual(len(videos), 0)

    def test_single_page_all_in_range(self):
        """Should return all videos when all fit in range on single page."""
        http_client = MagicMock()
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "data": [
                {
                    "id": "v1",
                    "title": "Stream 1",
                    "created_at": "2024-01-15T12:00:00Z",
                    "url": "https://twitch.tv/v1",
                },
                {
                    "id": "v2",
                    "title": "Stream 2",
                    "created_at": "2024-01-10T14:30:00Z",
                    "url": "https://twitch.tv/v2",
                },
            ],
            "pagination": {},
        }
        http_client.get.return_value = response

        videos = self.videos_api.list_videos_in_date_range(
            http_client=http_client,
            config=self.config,
            access_token=self.access_token,
            user_id=self.user_id,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )

        self.assertEqual(len(videos), 2)
        self.assertEqual(videos[0].video_id, "v1")
        self.assertEqual(videos[1].video_id, "v2")

    def test_pagination_multiple_pages(self):
        """Should paginate through multiple pages."""
        http_client = MagicMock()

        # First page
        response1 = Mock()
        response1.status_code = 200
        response1.json.return_value = {
            "data": [
                {
                    "id": "v1",
                    "title": "Stream 1",
                    "created_at": "2024-01-20T12:00:00Z",
                    "url": "https://twitch.tv/v1",
                },
            ],
            "pagination": {"cursor": "cursor1"},
        }

        # Second page
        response2 = Mock()
        response2.status_code = 200
        response2.json.return_value = {
            "data": [
                {
                    "id": "v2",
                    "title": "Stream 2",
                    "created_at": "2024-01-15T12:00:00Z",
                    "url": "https://twitch.tv/v2",
                },
            ],
            "pagination": {},
        }

        http_client.get.side_effect = [response1, response2]

        videos = self.videos_api.list_videos_in_date_range(
            http_client=http_client,
            config=self.config,
            access_token=self.access_token,
            user_id=self.user_id,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )

        self.assertEqual(len(videos), 2)
        self.assertEqual(http_client.get.call_count, 2)

    def test_early_stop_on_old_video(self):
        """Should stop pagination when encountering video older than start_date."""
        http_client = MagicMock()
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "data": [
                {
                    "id": "v1",
                    "title": "Stream 1",
                    "created_at": "2024-01-20T12:00:00Z",
                    "url": "https://twitch.tv/v1",
                },
                {
                    "id": "v2",
                    "title": "Stream 2",
                    "created_at": "2023-12-25T12:00:00Z",  # Before start_date
                    "url": "https://twitch.tv/v2",
                },
            ],
            "pagination": {"cursor": "cursor1"},  # Has more pages but should stop
        }
        http_client.get.return_value = response

        videos = self.videos_api.list_videos_in_date_range(
            http_client=http_client,
            config=self.config,
            access_token=self.access_token,
            user_id=self.user_id,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )

        # Should only return v1 (in range) and stop pagination
        self.assertEqual(len(videos), 1)
        self.assertEqual(videos[0].video_id, "v1")
        # Should only make 1 request (early stop)
        self.assertEqual(http_client.get.call_count, 1)

    def test_filters_by_date_range_inclusive(self):
        """Should only return videos within [start, end] inclusive."""
        http_client = MagicMock()
        response = Mock()
        response.status_code = 200
        # API returns newest-first, so order is: v5 (after), v4 (on end), v3 (in range), v2 (on start), v1 (before)
        response.json.return_value = {
            "data": [
                {
                    "id": "v5",
                    "title": "After range",
                    "created_at": "2024-02-01T00:00:00Z",  # After end
                    "url": "https://twitch.tv/v5",
                },
                {
                    "id": "v4",
                    "title": "On end date",
                    "created_at": "2024-01-31T23:59:59Z",  # On end
                    "url": "https://twitch.tv/v4",
                },
                {
                    "id": "v3",
                    "title": "In range",
                    "created_at": "2024-01-15T12:00:00Z",  # In range
                    "url": "https://twitch.tv/v3",
                },
                {
                    "id": "v2",
                    "title": "On start date",
                    "created_at": "2024-01-01T00:00:00Z",  # On start
                    "url": "https://twitch.tv/v2",
                },
                {
                    "id": "v1",
                    "title": "Before range",
                    "created_at": "2023-12-31T23:59:59Z",  # Before start
                    " url": "https://twitch.tv/v1",
                },
            ],
            "pagination": {},
        }
        http_client.get.return_value = response

        videos = self.videos_api.list_videos_in_date_range(
            http_client=http_client,
            config=self.config,
            access_token=self.access_token,
            user_id=self.user_id,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )

        # Should return v2, v3, v4 (inclusive range), skip v5 (after), and stop at v1 (before)
        self.assertEqual(len(videos), 3)
        video_ids = [v.video_id for v in videos]
        self.assertIn("v2", video_ids)
        self.assertIn("v3", video_ids)
        self.assertIn("v4", video_ids)
        self.assertNotIn("v1", video_ids)
        self.assertNotIn("v5", video_ids)

    def test_api_error_raises_videos_fetch_error(self):
        """Should raise VideosFetchError on API errors."""
        http_client = MagicMock()

        # Test 401
        response = Mock()
        response.status_code = 401
        http_client.get.return_value = response

        with self.assertRaises(self.videos_api.VideosFetchError) as cm:
            self.videos_api.list_videos_in_date_range(
                http_client=http_client,
                config=self.config,
                access_token=self.access_token,
                user_id=self.user_id,
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 31),
            )
        self.assertIn("Token invalid", str(cm.exception))

    def test_start_date_after_end_date_raises_value_error(self):
        """Should raise ValueError if start_date > end_date."""
        http_client = MagicMock()

        with self.assertRaises(ValueError) as cm:
            self.videos_api.list_videos_in_date_range(
                http_client=http_client,
                config=self.config,
                access_token=self.access_token,
                user_id=self.user_id,
                start_date=date(2024, 2, 1),
                end_date=date(2024, 1, 1),
            )
        self.assertIn("must be <=", str(cm.exception))


class TestParseRFC3339ToDatetime(unittest.TestCase):
    """Tests for _parse_rfc3339_to_datetime helper."""

    def setUp(self):
        """Set up test fixtures."""
        from twitch_marker_agent.core import videos_api

        self.videos_api = videos_api

    def test_with_z_suffix(self):
        """Should parse timestamp with Z suffix."""
        dt = self.videos_api._parse_rfc3339_to_datetime("2024-01-15T12:30:00Z")

        self.assertEqual(dt.year, 2024)
        self.assertEqual(dt.month, 1)
        self.assertEqual(dt.day, 15)
        self.assertEqual(dt.hour, 12)
        self.assertEqual(dt.minute, 30)
        self.assertEqual(dt.second, 0)
        self.assertIsNotNone(dt.tzinfo)

    def test_with_timezone_offset(self):
        """Should parse timestamp with timezone offset."""
        dt = self.videos_api._parse_rfc3339_to_datetime("2024-01-15T12:30:00+00:00")

        self.assertEqual(dt.year, 2024)
        self.assertEqual(dt.month, 1)
        self.assertEqual(dt.day, 15)

    def test_invalid_format_raises_value_error(self):
        """Should raise ValueError for malformed timestamp."""
        with self.assertRaises(ValueError) as cm:
            self.videos_api._parse_rfc3339_to_datetime("not-a-timestamp")

        self.assertIn("Invalid RFC3339", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
