"""
Twitch Helix API client for stream markers.

Provides access to the Get Stream Markers endpoint to retrieve
marker data from VODs.

API Reference:
https://dev.twitch.tv/docs/api/reference/#get-stream-markers
https://dev.twitch.tv/docs/api/reference/#get-videos
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Tuple

if TYPE_CHECKING:
    import requests
    from twitch_marker_agent.core.config import AppConfig


# Helix API endpoints
HELIX_BASE_URL = "https://api.twitch.tv/helix"
MARKERS_ENDPOINT = f"{HELIX_BASE_URL}/streams/markers"
VIDEOS_ENDPOINT = f"{HELIX_BASE_URL}/videos"

# HTTP timeouts (connect, read) in seconds
HTTP_TIMEOUT = (10, 30)


# =============================================================================
# Custom Exceptions
# =============================================================================


class MarkersFetchError(Exception):
    """Base exception for marker fetch operations."""

    pass


class MarkersAuthError(MarkersFetchError):
    """Raised when authentication/authorization fails (401/403)."""

    pass


class MarkersNotFoundError(MarkersFetchError):
    """Raised when markers or video not found (404)."""

    pass


class MarkersRateLimitError(MarkersFetchError):
    """Raised when rate limited (429)."""

    pass


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class Marker:
    """
    Represents a single stream marker.

    Attributes:
        id: Unique marker identifier.
        created_at: ISO 8601 timestamp when marker was created.
        position_seconds: Position in the video in seconds.
        description: User-provided marker description.
        user_type: Type of user who created the marker (default: "broadcaster").
        username: Twitch username who created the marker (default: "streamer").
    """

    id: str
    created_at: str
    position_seconds: int
    description: str
    user_type: str = "broadcaster"
    username: str = "streamer"

    def to_dict(self) -> dict[str, Any]:
        """Convert marker to dictionary for serialization."""
        return {
            "id": self.id,
            "created_at": self.created_at,
            "position_seconds": self.position_seconds,
            "description": self.description,
            "user_type": self.user_type,
            "username": self.username,
        }


@dataclass
class MarkerVideo:
    """
    Container for markers associated with a specific video.

    Attributes:
        video_id: Twitch VOD ID.
        markers: List of markers in the video.
    """

    video_id: str
    markers: list[Marker]


# =============================================================================
# Helper Functions
# =============================================================================


def _build_auth_headers(client_id: str, access_token: str) -> dict[str, str]:
    """Build authorization headers for Helix API calls."""
    return {
        "Authorization": f"Bearer {access_token}",
        "Client-Id": client_id,
    }


def parse_markers_response(
    response_data: dict[str, Any],
    broadcaster_user_id: str | None = None,
) -> list[MarkerVideo]:
    """
    Parse Helix API response into MarkerVideo objects.

    Args:
        response_data: Raw JSON response from Get Stream Markers.
        broadcaster_user_id: Broadcaster user ID used to infer marker user_type.

    Returns:
        List of MarkerVideo objects.
    """
    results: list[MarkerVideo] = []

    for user_data in response_data.get("data", []):
        user_id = user_data.get("user_id")
        username = (
            user_data.get("user_name")
            or user_data.get("user_login")
            or Marker.username
        )
        user_type = "Broadcaster" if broadcaster_user_id and user_id == broadcaster_user_id else "Editor"

        for video_data in user_data.get("videos", []):
            markers = [
                Marker(
                    id=m["id"],
                    created_at=m["created_at"],
                    position_seconds=m["position_seconds"],
                    description=m.get("description", ""),
                    user_type=user_type,
                    username=username,
                )
                for m in video_data.get("markers", [])
            ]
            results.append(
                MarkerVideo(
                    video_id=video_data["video_id"],
                    markers=markers,
                )
            )

    return results


def get_video_title_and_date(
    http_client,  # requests.Session
    config,       # AppConfig
    access_token: str,
    video_id: str,
    logger=None,
) -> tuple[str | None, str | None]:
    url = "https://api.twitch.tv/helix/videos"
    headers = {
        "Client-ID": config.client_id,
        "Authorization": f"Bearer {access_token}",
    }
    resp = http_client.get(url, headers=headers, params={"id": video_id}, timeout=10)
    resp.raise_for_status()
    payload = resp.json()
    data = payload.get("data") or []
    if not data:
        return None, None

    title = data[0].get("title") or None
    created_at = data[0].get("created_at") or None
    stream_date = created_at[:10] if created_at else None  # YYYY-MM-DD
    return title, stream_date


# =============================================================================
# API Functions
# =============================================================================


def get_stream_markers(
    http_client: "requests.Session",
    config: "AppConfig",
    access_token: str,
    user_id: str | None = None,
    video_id: str | None = None,
    logger: logging.Logger | None = None,
) -> list[MarkerVideo]:
    """
    Fetch stream markers from Twitch Helix API.

    Must provide either user_id (for recent VODs) or video_id (for specific VOD).

    Args:
        http_client: Configured requests Session.
        config: Application configuration.
        access_token: Valid OAuth access token with channel:manage:broadcast scope.
        user_id: Broadcaster user ID (returns markers from recent VODs).
        video_id: Specific video ID to get markers from.
        logger: Optional logger.

    Returns:
        List of MarkerVideo objects containing markers.

    Raises:
        ValueError: If neither user_id nor video_id provided.
        MarkersAuthError: If authentication fails (401/403).
        MarkersNotFoundError: If markers not found (404).
        MarkersRateLimitError: If rate limited (429).
        MarkersFetchError: For other failures.
    """
    log = logger or logging.getLogger(__name__)

    if not user_id and not video_id:
        raise ValueError("Must provide either user_id or video_id")

    headers = _build_auth_headers(config.client_id, access_token)

    # Build query params
    params: dict[str, str] = {}
    if user_id:
        params["user_id"] = user_id
    if video_id:
        params["video_id"] = video_id

    log.info("Fetching stream markers")
    log.debug("Markers request params: %s", list(params.keys()))

    try:
        response = http_client.get(
            MARKERS_ENDPOINT,
            headers=headers,
            params=params,
            timeout=HTTP_TIMEOUT,
        )
    except Exception as e:
        log.error("Network error fetching markers: %s", type(e).__name__)
        raise MarkersFetchError(f"Network error: {type(e).__name__}") from e

    log.debug("Markers response status: %d", response.status_code)

    # Handle error responses
    if response.status_code == 401:
        log.error("Authentication failed (401)")
        raise MarkersAuthError(
            "Token invalid or expired. Run 'auth-login' to re-authenticate."
        )

    if response.status_code == 403:
        log.error("Forbidden (403) - missing required scope")
        raise MarkersAuthError(
            "Missing required scope. Run 'auth-login' to re-authenticate with "
            "channel:manage:broadcast scope."
        )

    if response.status_code == 404:
        log.warning("Markers not found (404)")
        raise MarkersNotFoundError("Markers not found for the specified user/video.")

    if response.status_code == 429:
        log.warning("Rate limited (429)")
        raise MarkersRateLimitError("Rate limited. Try again later.")

    if response.status_code != 200:
        log.error("Unexpected status code: %d", response.status_code)
        raise MarkersFetchError(
            f"Failed to fetch markers (HTTP {response.status_code})"
        )

    # Parse success response
    try:
        response_data = response.json()
        marker_videos = parse_markers_response(
            response_data,
            broadcaster_user_id=user_id,
        )
        total_markers = sum(len(mv.markers) for mv in marker_videos)
        log.info("Retrieved %d markers from %d videos", total_markers, len(marker_videos))
        return marker_videos

    except (json.JSONDecodeError, KeyError) as e:
        log.error("Failed to parse markers response: %s", type(e).__name__)
        raise MarkersFetchError("Failed to parse markers response") from e


def get_latest_video_id(
    http_client: "requests.Session",
    config: "AppConfig",
    access_token: str,
    user_id: str,
    logger: logging.Logger | None = None,
) -> str | None:
    """
    Get the most recent VOD ID for a user.

    Useful for fetching markers after stream.offline when we need
    to find which VOD was just created.

    Args:
        http_client: Configured requests Session.
        config: Application configuration.
        access_token: Valid OAuth access token.
        user_id: Broadcaster user ID.
        logger: Optional logger.

    Returns:
        Video ID of the most recent VOD, or None if no VODs.

    Raises:
        MarkersAuthError: If authentication fails (401/403).
        MarkersRateLimitError: If rate limited (429).
        MarkersFetchError: For other failures.
    """
    log = logger or logging.getLogger(__name__)

    headers = _build_auth_headers(config.client_id, access_token)

    params = {
        "user_id": user_id,
        "type": "archive",  # VODs only
        "first": "1",  # Most recent only
    }

    log.info("Fetching latest video ID for user")
    log.debug("Videos request for user_id=%s", user_id)

    try:
        response = http_client.get(
            VIDEOS_ENDPOINT,
            headers=headers,
            params=params,
            timeout=HTTP_TIMEOUT,
        )
    except Exception as e:
        log.error("Network error fetching videos: %s", type(e).__name__)
        raise MarkersFetchError(f"Network error: {type(e).__name__}") from e

    log.debug("Videos response status: %d", response.status_code)

    # Handle error responses
    if response.status_code == 401:
        log.error("Authentication failed (401)")
        raise MarkersAuthError(
            "Token invalid or expired. Run 'auth-login' to re-authenticate."
        )

    if response.status_code == 403:
        log.error("Forbidden (403)")
        raise MarkersAuthError(
            "Forbidden. Run 'auth-login' to re-authenticate."
        )

    if response.status_code == 404:
        log.info("No videos found (404)")
        return None

    if response.status_code == 429:
        log.warning("Rate limited (429)")
        raise MarkersRateLimitError("Rate limited. Try again later.")

    if response.status_code != 200:
        log.error("Unexpected status code: %d", response.status_code)
        raise MarkersFetchError(
            f"Failed to fetch videos (HTTP {response.status_code})"
        )

    # Parse success response
    try:
        response_data = response.json()
        videos = response_data.get("data", [])

        if not videos:
            log.info("No VODs found for user")
            return None

        video_id = videos[0].get("id")
        log.info("Found latest video: id=%s...", video_id[:8] if video_id else "none")
        return video_id

    except (json.JSONDecodeError, KeyError, IndexError) as e:
        log.error("Failed to parse videos response: %s", type(e).__name__)
        raise MarkersFetchError("Failed to parse videos response") from e
