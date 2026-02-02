"""
Twitch Helix API client for stream markers.

Provides access to the Get Stream Markers endpoint to retrieve
marker data from VODs.

API Reference:
https://dev.twitch.tv/docs/api/reference/#get-stream-markers
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import requests
    from twitch_marker_agent.core.config import AppConfig


# Helix API endpoints
HELIX_BASE_URL = "https://api.twitch.tv/helix"
MARKERS_ENDPOINT = f"{HELIX_BASE_URL}/streams/markers"


@dataclass
class Marker:
    """
    Represents a single stream marker.

    Attributes:
        id: Unique marker identifier.
        created_at: ISO 8601 timestamp when marker was created.
        position_seconds: Position in the video in seconds.
        description: User-provided marker description.
    """

    id: str
    created_at: str
    position_seconds: int
    description: str

    def to_dict(self) -> dict[str, Any]:
        """Convert marker to dictionary for serialization."""
        return {
            "id": self.id,
            "created_at": self.created_at,
            "position_seconds": self.position_seconds,
            "description": self.description,
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


def get_stream_markers(
    http_client: requests.Session,
    config: AppConfig,
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
        access_token: Valid OAuth access token with user:read:broadcast scope.
        user_id: Broadcaster user ID (returns markers from recent VODs).
        video_id: Specific video ID to get markers from.
        logger: Optional logger.

    Returns:
        List of MarkerVideo objects containing markers.

    Raises:
        NotImplementedError: API call not yet implemented.
        ValueError: If neither user_id nor video_id provided.
    """
    if not user_id and not video_id:
        raise ValueError("Must provide either user_id or video_id")

    # TODO: Implement Helix Get Stream Markers API call
    # GET https://api.twitch.tv/helix/streams/markers
    # Headers:
    #   Authorization: Bearer <access_token>
    #   Client-Id: <client_id>
    # Query params (one required):
    #   user_id: Get markers from user's recent VODs
    #   video_id: Get markers from specific VOD
    # Optional:
    #   first: Number of results (max 100)
    #   after: Pagination cursor
    #
    # Response format:
    # {
    #   "data": [{
    #     "user_id": "123",
    #     "user_name": "TwitchUser",
    #     "videos": [{
    #       "video_id": "456",
    #       "markers": [{
    #         "id": "789",
    #         "created_at": "2021-01-01T00:00:00Z",
    #         "position_seconds": 3600,
    #         "description": "Marker description"
    #       }]
    #     }]
    #   }],
    #   "pagination": {"cursor": "..."}
    # }
    raise NotImplementedError("TODO: Implement Get Stream Markers API call")


def get_latest_video_id(
    http_client: requests.Session,
    config: AppConfig,
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
        NotImplementedError: API call not yet implemented.
    """
    # TODO: Implement Get Videos API call
    # GET https://api.twitch.tv/helix/videos
    # Query params:
    #   user_id: <user_id>
    #   type: archive (for VODs)
    #   first: 1
    raise NotImplementedError("TODO: Implement Get Videos API call")


def parse_markers_response(response_data: dict[str, Any]) -> list[MarkerVideo]:
    """
    Parse Helix API response into MarkerVideo objects.

    Args:
        response_data: Raw JSON response from Get Stream Markers.

    Returns:
        List of MarkerVideo objects.
    """
    results: list[MarkerVideo] = []

    for user_data in response_data.get("data", []):
        for video_data in user_data.get("videos", []):
            markers = [
                Marker(
                    id=m["id"],
                    created_at=m["created_at"],
                    position_seconds=m["position_seconds"],
                    description=m.get("description", ""),
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
