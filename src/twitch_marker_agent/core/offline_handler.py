"""
Stream offline notification handler for Twitch Marker Agent.

Handles stream.offline EventSub notifications by:
1. Validating and deduplicating notifications
2. Fetching markers with retry for eventual consistency
3. Exporting markers to configured formats

This module is framework-agnostic with pure functions for testability.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any

from twitch_marker_agent.core.export_csv import export_markers_csv
from twitch_marker_agent.core.export_edl import (
    DEFAULT_OFFSET_SECONDS,
    export_markers_edl,
    timecode_to_seconds,
)
from twitch_marker_agent.core.markers_api import (
    MarkersFetchError,
    MarkersAuthError,
    MarkersNotFoundError,
    MarkersRateLimitError,
    get_latest_video_id,
    get_video_title_and_date,
    get_stream_markers,
)
from twitch_marker_agent.core.retry import RetryError, retry_with_backoff

if TYPE_CHECKING:
    import requests
    from twitch_marker_agent.core.config import AppConfig
    from twitch_marker_agent.core.eventsub_ws import EventSubMessage
    from twitch_marker_agent.core.state_store import StateStore


# Retry configuration for eventual consistency
# VOD markers may not be available immediately after stream.offline
DEFAULT_MAX_ATTEMPTS = 6
DEFAULT_BASE_DELAY = 5.0  # seconds
DEFAULT_MAX_DELAY = 60.0  # seconds


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class MarkerExportResult:
    """
    Result of a marker export operation.

    Attributes:
        video_id: The video ID that was processed (or attempted).
        marker_count: Number of markers exported.
        export_paths: List of paths to exported files.
        skipped: True if export was skipped (duplicate or no markers).
        skip_reason: Human-readable reason if skipped.
    """

    video_id: str
    marker_count: int = 0
    export_paths: list[Path] = field(default_factory=list)
    skipped: bool = False
    skip_reason: str | None = None


# =============================================================================
# Helper Functions
# =============================================================================


def _get_broadcaster_id_from_message(message: "EventSubMessage") -> str | None:
    """Extract broadcaster_user_id from EventSub notification payload."""
    event = message.payload.get("event", {})
    return event.get("broadcaster_user_id")


def _make_processed_key(broadcaster_id: str, video_id: str) -> str:
    """Build StateStore key for tracking processed videos."""
    return f"processed_video:{broadcaster_id}:{video_id}"


# =============================================================================
# Notification Filtering
# =============================================================================


def should_handle_notification(
    message: "EventSubMessage",
    expected_broadcaster_id: str,
    seen_message_ids: set[str] | None = None,
) -> bool:
    """
    Check if an EventSub notification should be processed.

    Filters out:
    - Non stream.offline notifications
    - Notifications for other broadcasters
    - Duplicate messages (by message_id)

    Args:
        message: EventSub notification message.
        expected_broadcaster_id: The broadcaster ID we're monitoring.
        seen_message_ids: Set of already-seen message IDs for dedupe.

    Returns:
        True if notification should be processed, False otherwise.
    """
    # Must be a notification
    if message.message_type != "notification":
        return False

    # Must be stream.offline subscription type
    if message.subscription_type != "stream.offline":
        return False

    # Must match our broadcaster
    broadcaster_id = _get_broadcaster_id_from_message(message)
    if broadcaster_id != expected_broadcaster_id:
        return False

    # Check message_id dedupe
    if seen_message_ids is not None and message.message_id:
        if message.message_id in seen_message_ids:
            return False
        # Mark as seen
        seen_message_ids.add(message.message_id)

    return True


# =============================================================================
# Main Handler
# =============================================================================


def handle_stream_offline(
    http_client: "requests.Session",
    config: "AppConfig",
    access_token: str,
    broadcaster_id: str,
    state_store: "StateStore",
    logger: logging.Logger,
    seen_message_ids: set[str] | None = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
) -> MarkerExportResult:
    """
    Handle stream.offline by fetching and exporting markers.

    Flow:
    1. Get latest video ID for broadcaster
    2. Check if already processed (dedupe)
    3. Fetch markers with retry (for eventual consistency)
    4. Export to configured formats
    5. Mark as processed in StateStore

    Args:
        http_client: Configured requests Session.
        config: Application configuration.
        access_token: Valid OAuth access token.
        broadcaster_id: Broadcaster user ID from the offline event.
        state_store: Persistent state storage.
        logger: Logger instance.
        seen_message_ids: In-memory set for message_id dedupe (optional).
        max_attempts: Maximum retry attempts for marker fetch.
        base_delay: Initial retry delay in seconds.
        max_delay: Maximum retry delay in seconds.

    Returns:
        MarkerExportResult with export details or skip reason.

    Raises:
        MarkersAuthError: If authentication fails (needs reauth).
        MarkersFetchError: If fetch fails after all retries.
    """
    logger.info("Handling stream.offline for broadcaster_id=%s", broadcaster_id)

    # Step 1: Get latest video ID
    logger.info("Fetching latest video ID")
    video_id = get_latest_video_id(
        http_client=http_client,
        config=config,
        access_token=access_token,
        user_id=broadcaster_id,
        logger=logger,
    )

    if not video_id:
        logger.warning("No VOD found for broadcaster, skipping export")
        return MarkerExportResult(
            video_id="",
            skipped=True,
            skip_reason="No VOD found for broadcaster",
        )

    # Step 2: Check if already processed (persistent dedupe)
    processed_key = _make_processed_key(broadcaster_id, video_id)
    if state_store.get_state(processed_key):
        logger.info(
            "Video already processed: %s..., skipping",
            video_id[:8] if len(video_id) >= 8 else video_id,
        )
        return MarkerExportResult(
            video_id=video_id,
            skipped=True,
            skip_reason="Already processed",
        )

    # Step 3: Fetch markers with retry for eventual consistency
    logger.info("Fetching markers for video_id=%s...", video_id[:8])

    def fetch_markers() -> Any:
        """Wrapper for retry_with_backoff."""
        return get_stream_markers(
            http_client=http_client,
            config=config,
            access_token=access_token,
            video_id=video_id,
            logger=logger,
        )

    try:
        marker_videos = retry_with_backoff(
            fn=fetch_markers,
            max_attempts=max_attempts,
            base_delay=base_delay,
            max_delay=max_delay,
            retryable_exceptions=(MarkersNotFoundError, MarkersRateLimitError),
            logger=logger,
        )
    except RetryError as e:
        # All retries exhausted
        logger.error("Failed to fetch markers after %d attempts", max_attempts)
        # Check if it was auth error wrapped
        if isinstance(e.last_exception, MarkersAuthError):
            raise e.last_exception from e
        raise MarkersFetchError(
            f"Failed to fetch markers after {max_attempts} attempts"
        ) from e
    except MarkersAuthError:
        # Auth errors should not be retried
        raise

    # Flatten markers from all videos (should be just one for video_id query)
    all_markers = []
    for mv in marker_videos:
        all_markers.extend(mv.markers)

    if not all_markers:
        logger.info("No markers found for video, skipping export")
        # Still mark as processed to avoid retrying
        state_store.set_state(processed_key, "no_markers")
        return MarkerExportResult(
            video_id=video_id,
            marker_count=0,
            skipped=True,
            skip_reason="No markers in video",
        )

    # Step 4: Export to configured formats
    # Respect tray EDL toggle if present, fallback to config
    export_paths: list[Path] = []

    # Fetch title/date for preferred filenames (non-fatal if it fails)
    stream_title: str | None = None
    stream_date: str | None = None
    try:
        stream_title, stream_date = get_video_title_and_date(
            http_client=http_client,
            config=config,
            access_token=access_token,
            video_id=video_id,
            logger=logger,
        )
    except Exception as e:
        logger.warning("VOD metadata unavailable; using fallback filename (%s)", type(e).__name__)


    # Determine which formats to export
    # Try tray EDL toggle first (if running in tray context)
    from twitch_marker_agent.tray_controller import (
        TRAY_EDL_ENABLED_KEY,
        get_export_formats_from_edl_flag,
    )

    tray_edl_toggle = state_store.get_state(TRAY_EDL_ENABLED_KEY)
    if tray_edl_toggle is not None:
        # Tray toggle is set, use it
        edl_enabled = tray_edl_toggle.strip().lower() in ("true", "1", "yes")
        formats_to_export = get_export_formats_from_edl_flag(edl_enabled)
    else:
        # No tray toggle, fall back to config
        formats_to_export = config.export_formats

    # Ensure output directory exists
    output_dir = config.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    # Export to CSV (always, since it's implemented)
    if "csv" in formats_to_export:
        csv_path = export_markers_csv(
            markers=all_markers,
            output_path=config.output_dir,
            config=config,
            video_id=video_id,
            stream_title=stream_title,
            stream_date=stream_date,
            logger=logger,
        )
        export_paths.append(csv_path)

    # EDL export
    if "edl" in formats_to_export:
        # Compute offset from config
        edl_offset_seconds = 0
        if config.resolve_offset_enabled:
            try:
                edl_offset_seconds = timecode_to_seconds(config.resolve_offset_timecode)
            except (ValueError, AttributeError):
                logger.warning(
                    "Invalid resolve_offset_timecode, falling back to default offset"
                )
                edl_offset_seconds = DEFAULT_OFFSET_SECONDS

        edl_path = export_markers_edl(
            markers=all_markers,
            output_path=config.output_dir,
            config=config,
            video_id=video_id,
            stream_title=stream_title,
            stream_date=stream_date,
            timecode_offset_seconds=edl_offset_seconds,
            logger=logger,
        )
        export_paths.append(edl_path)

    # Step 5: Mark as processed
    from datetime import datetime, timezone
    state_store.set_state(processed_key, datetime.now(timezone.utc).isoformat())

    logger.info(
        "Export complete: %d markers to %d files",
        len(all_markers),
        len(export_paths),
    )

    return MarkerExportResult(
        video_id=video_id,
        marker_count=len(all_markers),
        export_paths=export_paths,
        skipped=False,
    )
