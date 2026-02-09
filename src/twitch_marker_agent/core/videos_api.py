"""
Twitch Helix API client for video listing.

Provides access to the Get Videos endpoint to retrieve archived VODs
within a specified date range.

API Reference:
https://dev.twitch.tv/docs/api/reference/#get-videos
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import requests
    from twitch_marker_agent.core.config import AppConfig


# Helix API endpoints
HELIX_BASE_URL = "https://api.twitch.tv/helix"
VIDEOS_ENDPOINT = f"{HELIX_BASE_URL}/videos"

# HTTP timeouts (connect, read) in seconds
HTTP_TIMEOUT = (10, 30)


# =============================================================================
# Custom Exceptions
# =============================================================================


class VideosFetchError(Exception):
    """Raised when video fetch operation fails."""

    pass


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class ArchivedVideo:
    """
    Represents an archived VOD.

    Attributes:
        video_id: Twitch VOD ID.
        title: VOD title.
        created_at: Creation timestamp (timezone-aware).
        url: VOD URL.
    """

    video_id: str
    title: str
    created_at: datetime
    url: str


# =============================================================================
# Helper Functions
# =============================================================================


def _build_auth_headers(client_id: str, access_token: str) -> dict[str, str]:
    """Build authorization headers for Helix API calls."""
    return {
        "Authorization": f"Bearer {access_token}",
        "Client-Id": client_id,
    }


def _parse_rfc3339_to_datetime(timestamp: str) -> datetime:
    """
    Parse RFC3339 timestamp to timezone-aware datetime.

    Handles both 'Z' suffix and timezone offsets.

    Args:
        timestamp: RFC3339 formatted timestamp (e.g., "2024-01-15T12:00:00Z").

    Returns:
        Timezone-aware datetime object.

    Raises:
        ValueError: If timestamp format is invalid.
    """
    # Replace 'Z' with '+00:00' for consistent parsing
    if timestamp.endswith("Z"):
        timestamp = timestamp[:-1] + "+00:00"

    try:
        return datetime.fromisoformat(timestamp)
    except ValueError as e:
        raise ValueError(f"Invalid RFC3339 timestamp: {timestamp}") from e


# =============================================================================
# API Functions
# =============================================================================


def list_videos_in_date_range(
    http_client: "requests.Session",
    config: "AppConfig",
    access_token: str,
    user_id: str,
    start_date: date,
    end_date: date,
    logger: logging.Logger | None = None,
) -> list[ArchivedVideo]:
    """
    List archived VODs within a date range using Helix Get Videos.

    Fetches all archived VODs for a broadcaster whose created_at date
    falls within [start_date, end_date] inclusive. Uses cursor pagination
    and stops early when encountering videos older than start_date.

    Args:
        http_client: Configured requests Session.
        config: Application configuration.
        access_token: Valid OAuth access token.
        user_id: Broadcaster user ID.
        start_date: Range start (inclusive).
        end_date: Range end (inclusive).
        logger: Optional logger.

    Returns:
        List of ArchivedVideo objects in range, newest first.

    Raises:
        ValueError: If start_date > end_date.
        VideosFetchError: On API errors.
    """
    log = logger or logging.getLogger(__name__)

    if start_date > end_date:
        raise ValueError(f"start_date ({start_date}) must be <= end_date ({end_date})")

    headers = _build_auth_headers(config.client_id, access_token)

    results: list[ArchivedVideo] = []
    cursor: str | None = None
    page_count = 0

    log.info(
        "Fetching archived videos in range: %s to %s",
        start_date.isoformat(),
        end_date.isoformat(),
    )

    while True:
        page_count += 1
        params: dict[str, str] = {
            "user_id": user_id,
            "type": "archive",
            "first": "100",  # Max per page
        }
        if cursor:
            params["after"] = cursor

        log.debug("Fetching videos page %d", page_count)

        try:
            response = http_client.get(
                VIDEOS_ENDPOINT,
                headers=headers,
                params=params,
                timeout=HTTP_TIMEOUT,
            )
        except Exception as e:
            log.error("Network error fetching videos: %s", type(e).__name__)
            raise VideosFetchError(f"Network error: {type(e).__name__}") from e

        log.debug("Videos response status: %d", response.status_code)

        # Handle error responses
        if response.status_code == 401:
            log.error("Authentication failed (401)")
            raise VideosFetchError(
                "Token invalid or expired. Run 'auth-login' to re-authenticate."
            )

        if response.status_code == 403:
            log.error("Forbidden (403)")
            raise VideosFetchError("Forbidden. Re-authenticate with proper scopes.")

        if response.status_code == 429:
            log.warning("Rate limited (429)")
            raise VideosFetchError("Rate limited. Try again later.")

        if response.status_code != 200:
            log.error("Unexpected status code: %d", response.status_code)
            raise VideosFetchError(
                f"Failed to fetch videos (HTTP {response.status_code})"
            )

        # Parse response
        try:
            response_data = response.json()
            videos_data = response_data.get("data", [])
            pagination = response_data.get("pagination", {})
            cursor = pagination.get("cursor")

        except (json.JSONDecodeError, KeyError) as e:
            log.error("Failed to parse videos response: %s", type(e).__name__)
            raise VideosFetchError("Failed to parse videos response") from e

        if not videos_data:
            log.debug("No more videos in page %d", page_count)
            break

        # Process videos in this page
        for video_data in videos_data:
            try:
                created_at_str = video_data["created_at"]
                created_at_dt = _parse_rfc3339_to_datetime(created_at_str)
                video_date = created_at_dt.date()

                # Check if video is older than range start (early stop)
                if video_date < start_date:
                    log.debug(
                        "Encountered video older than start_date (%s < %s), stopping pagination",
                        video_date.isoformat(),
                        start_date.isoformat(),
                    )
                    cursor = None  # Stop pagination
                    break

                # Filter by date range (inclusive)
                if start_date <= video_date <= end_date:
                    video = ArchivedVideo(
                        video_id=video_data["id"],
                        title=video_data.get("title", ""),
                        created_at=created_at_dt,
                        url=video_data.get("url", ""),
                    )
                    results.append(video)
                    log.debug(
                        "Added video: id=%s, date=%s",
                        video.video_id[:8],
                        video_date.isoformat(),
                    )

            except (KeyError, ValueError) as e:
                log.warning("Skipping malformed video entry: %s", type(e).__name__)
                continue

        # Stop if no more pages or early stop triggered
        if not cursor:
            break

    log.info("Retrieved %d videos in date range across %d pages", len(results), page_count)
    return results
