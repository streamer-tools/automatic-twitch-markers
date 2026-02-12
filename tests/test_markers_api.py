"""
Tests for markers API module.

Uses stdlib unittest + mocks only; no real network connections.
"""

from __future__ import annotations

import json
import logging
import unittest
from unittest.mock import MagicMock, patch

from twitch_marker_agent.core.markers_api import (
    HTTP_TIMEOUT,
    Marker,
    MarkerVideo,
    MarkersAuthError,
    MarkersFetchError,
    MarkersNotFoundError,
    MarkersRateLimitError,
    get_latest_video_id,
    get_stream_markers,
    parse_markers_response,
)


# =============================================================================
# Test Fixtures
# =============================================================================


def make_mock_config() -> MagicMock:
    """Create a mock AppConfig."""
    config = MagicMock()
    config.client_id = "test_client_id"
    return config


def make_markers_response(
    video_id: str = "video_123",
    markers: list[dict] | None = None,
) -> dict:
    """Create a sample markers API response."""
    if markers is None:
        markers = [
            {
                "id": "marker_1",
                "created_at": "2026-02-04T12:00:00Z",
                "position_seconds": 3600,
                "description": "First marker",
            },
            {
                "id": "marker_2",
                "created_at": "2026-02-04T12:30:00Z",
                "position_seconds": 5400,
                "description": "Second marker",
            },
        ]
    return {
        "data": [
            {
                "user_id": "12345",
                "user_name": "TestUser",
                "videos": [
                    {
                        "video_id": video_id,
                        "markers": markers,
                    }
                ],
            }
        ],
        "pagination": {},
    }


def make_videos_response(video_id: str = "video_123") -> dict:
    """Create a sample videos API response."""
    return {
        "data": [
            {
                "id": video_id,
                "user_id": "12345",
                "user_name": "TestUser",
                "title": "Test Stream",
                "created_at": "2026-02-04T10:00:00Z",
            }
        ],
        "pagination": {},
    }


def make_mock_response(status_code: int, json_data: dict | None = None) -> MagicMock:
    """Create a mock requests.Response."""
    response = MagicMock()
    response.status_code = status_code
    if json_data is not None:
        response.json.return_value = json_data
    return response


# =============================================================================
# Tests for parse_markers_response
# =============================================================================


class TestParseMarkersResponse(unittest.TestCase):
    """Tests for parse_markers_response function."""

    def test_parses_single_video_with_markers(self) -> None:
        """Should parse markers from single video."""
        response = make_markers_response(video_id="vid_123")
        result = parse_markers_response(response)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].video_id, "vid_123")
        self.assertEqual(len(result[0].markers), 2)
        self.assertEqual(result[0].markers[0].id, "marker_1")
        self.assertEqual(result[0].markers[0].position_seconds, 3600)

    def test_parses_empty_markers(self) -> None:
        """Should handle video with no markers."""
        response = make_markers_response(markers=[])
        result = parse_markers_response(response)

        self.assertEqual(len(result), 1)
        self.assertEqual(len(result[0].markers), 0)

    def test_parses_empty_data(self) -> None:
        """Should handle empty data array."""
        result = parse_markers_response({"data": []})
        self.assertEqual(len(result), 0)

    def test_handles_missing_description(self) -> None:
        """Should default missing description to empty string."""
        response = make_markers_response(
            markers=[
                {
                    "id": "m1",
                    "created_at": "2026-02-04T00:00:00Z",
                    "position_seconds": 100,
                    # No description field
                }
            ]
        )
        result = parse_markers_response(response)

        self.assertEqual(result[0].markers[0].description, "")

    def test_populates_username_from_user_name(self) -> None:
        """Should use user_name for marker username when available."""
        response = make_markers_response()
        result = parse_markers_response(response, broadcaster_user_id="12345")

        self.assertEqual(result[0].markers[0].username, "TestUser")

    def test_username_falls_back_to_user_login(self) -> None:
        """Should fall back to user_login when user_name is missing."""
        response = make_markers_response()
        user_block = response["data"][0]
        user_block.pop("user_name", None)
        user_block["user_login"] = "test_login"

        result = parse_markers_response(response, broadcaster_user_id="12345")

        self.assertEqual(result[0].markers[0].username, "test_login")

    def test_user_type_broadcaster_when_user_matches(self) -> None:
        """Should set user_type Broadcaster for matching broadcaster user_id."""
        response = make_markers_response()

        result = parse_markers_response(response, broadcaster_user_id="12345")

        self.assertEqual(result[0].markers[0].user_type, "Broadcaster")

    def test_user_type_editor_when_user_does_not_match(self) -> None:
        """Should set user_type Editor for non-broadcaster marker users."""
        response = make_markers_response()

        result = parse_markers_response(response, broadcaster_user_id="99999")

        self.assertEqual(result[0].markers[0].user_type, "Editor")


# =============================================================================
# Tests for get_stream_markers
# =============================================================================


class TestGetStreamMarkers(unittest.TestCase):
    """Tests for get_stream_markers function."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.logger = MagicMock(spec=logging.Logger)
        self.http_client = MagicMock()
        self.config = make_mock_config()
        self.access_token = "test_token"

    def test_success_returns_marker_videos(self) -> None:
        """200 response should return parsed MarkerVideo list."""
        response_data = make_markers_response(video_id="vid_456")
        self.http_client.get.return_value = make_mock_response(200, response_data)

        result = get_stream_markers(
            http_client=self.http_client,
            config=self.config,
            access_token=self.access_token,
            video_id="vid_456",
            logger=self.logger,
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].video_id, "vid_456")
        self.assertEqual(len(result[0].markers), 2)

    def test_requires_user_id_or_video_id(self) -> None:
        """Should raise ValueError if neither user_id nor video_id provided."""
        with self.assertRaises(ValueError) as ctx:
            get_stream_markers(
                http_client=self.http_client,
                config=self.config,
                access_token=self.access_token,
                logger=self.logger,
            )

        self.assertIn("user_id or video_id", str(ctx.exception))

    def test_401_raises_auth_error(self) -> None:
        """401 should raise MarkersAuthError with reauth message."""
        self.http_client.get.return_value = make_mock_response(401)

        with self.assertRaises(MarkersAuthError) as ctx:
            get_stream_markers(
                http_client=self.http_client,
                config=self.config,
                access_token=self.access_token,
                video_id="vid_123",
                logger=self.logger,
            )

        self.assertIn("auth-login", str(ctx.exception).lower())

    def test_403_raises_auth_error(self) -> None:
        """403 should raise MarkersAuthError with scope message."""
        self.http_client.get.return_value = make_mock_response(403)

        with self.assertRaises(MarkersAuthError) as ctx:
            get_stream_markers(
                http_client=self.http_client,
                config=self.config,
                access_token=self.access_token,
                video_id="vid_123",
                logger=self.logger,
            )

        self.assertIn("scope", str(ctx.exception).lower())

    def test_404_raises_not_found(self) -> None:
        """404 should raise MarkersNotFoundError."""
        self.http_client.get.return_value = make_mock_response(404)

        with self.assertRaises(MarkersNotFoundError):
            get_stream_markers(
                http_client=self.http_client,
                config=self.config,
                access_token=self.access_token,
                video_id="vid_123",
                logger=self.logger,
            )

    def test_429_raises_rate_limit_error(self) -> None:
        """429 should raise MarkersRateLimitError."""
        self.http_client.get.return_value = make_mock_response(429)

        with self.assertRaises(MarkersRateLimitError):
            get_stream_markers(
                http_client=self.http_client,
                config=self.config,
                access_token=self.access_token,
                video_id="vid_123",
                logger=self.logger,
            )

    def test_network_error_raises_fetch_error(self) -> None:
        """Network error should raise MarkersFetchError."""
        self.http_client.get.side_effect = ConnectionError("Network down")

        with self.assertRaises(MarkersFetchError) as ctx:
            get_stream_markers(
                http_client=self.http_client,
                config=self.config,
                access_token=self.access_token,
                video_id="vid_123",
                logger=self.logger,
            )

        self.assertIn("network", str(ctx.exception).lower())

    def test_passes_broadcaster_id_to_parser(self) -> None:
        """Should pass user_id through for user_type inference in parser."""
        response_data = make_markers_response(video_id="vid_456")
        self.http_client.get.return_value = make_mock_response(200, response_data)

        with patch(
            "twitch_marker_agent.core.markers_api.parse_markers_response",
            return_value=[],
        ) as mock_parse:
            result = get_stream_markers(
                http_client=self.http_client,
                config=self.config,
                access_token=self.access_token,
                user_id="12345",
                logger=self.logger,
            )

        self.assertEqual(result, [])
        mock_parse.assert_called_once_with(
            response_data,
            broadcaster_user_id="12345",
        )


# =============================================================================
# Tests for get_latest_video_id
# =============================================================================


class TestGetLatestVideoId(unittest.TestCase):
    """Tests for get_latest_video_id function."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.logger = MagicMock(spec=logging.Logger)
        self.http_client = MagicMock()
        self.config = make_mock_config()
        self.access_token = "test_token"

    def test_success_returns_video_id(self) -> None:
        """200 response should return video ID."""
        response_data = make_videos_response(video_id="latest_vid_789")
        self.http_client.get.return_value = make_mock_response(200, response_data)

        result = get_latest_video_id(
            http_client=self.http_client,
            config=self.config,
            access_token=self.access_token,
            user_id="12345",
            logger=self.logger,
        )

        self.assertEqual(result, "latest_vid_789")

    def test_empty_videos_returns_none(self) -> None:
        """Should return None if no videos."""
        self.http_client.get.return_value = make_mock_response(200, {"data": []})

        result = get_latest_video_id(
            http_client=self.http_client,
            config=self.config,
            access_token=self.access_token,
            user_id="12345",
            logger=self.logger,
        )

        self.assertIsNone(result)

    def test_404_returns_none(self) -> None:
        """404 should return None (no videos)."""
        self.http_client.get.return_value = make_mock_response(404)

        result = get_latest_video_id(
            http_client=self.http_client,
            config=self.config,
            access_token=self.access_token,
            user_id="12345",
            logger=self.logger,
        )

        self.assertIsNone(result)

    def test_401_raises_auth_error(self) -> None:
        """401 should raise MarkersAuthError."""
        self.http_client.get.return_value = make_mock_response(401)

        with self.assertRaises(MarkersAuthError):
            get_latest_video_id(
                http_client=self.http_client,
                config=self.config,
                access_token=self.access_token,
                user_id="12345",
                logger=self.logger,
            )

    def test_429_raises_rate_limit_error(self) -> None:
        """429 should raise MarkersRateLimitError."""
        self.http_client.get.return_value = make_mock_response(429)

        with self.assertRaises(MarkersRateLimitError):
            get_latest_video_id(
                http_client=self.http_client,
                config=self.config,
                access_token=self.access_token,
                user_id="12345",
                logger=self.logger,
            )


if __name__ == "__main__":
    unittest.main()
