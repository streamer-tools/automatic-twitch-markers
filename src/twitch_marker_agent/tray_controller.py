"""
Tray controller with UI-agnostic, testable pure functions.

This module provides the business logic for the tray application
without any pystray dependencies. All pystray/UI code lives in app.py.

Functions:
- resolve_output_dir: Get output directory from StateStore or config
- set_output_dir: Persist output directory to StateStore
- get_manual_fetch_formats: Get export formats for manual fetch
- run_manual_fetch: Execute manual marker fetch and export
- start_auto_mode: Start agent runner in worker thread
- stop_auto_mode: Stop agent runner gracefully
"""

from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import requests
    from twitch_marker_agent.core.agent_runner import AgentRunner
    from twitch_marker_agent.core.config import AppConfig
    from twitch_marker_agent.core.state_store import StateStore
    from twitch_marker_agent.core.twitch_oauth import TwitchOAuth


# =============================================================================
# Constants
# =============================================================================

TRAY_OUTPUT_DIR_KEY = "tray.output_dir"
TRAY_EDL_ENABLED_KEY = "tray.edl_enabled"


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class TrayState:
    """Mutable state for tray application."""

    selected_formats: list[str] = field(default_factory=list)
    is_fetching: bool = False
    last_fetch_result: str | None = None


@dataclass
class ManualFetchResult:
    """Result of manual fetch operation."""

    success: bool
    message: str
    export_paths: list[Path] = field(default_factory=list)
    marker_count: int = 0


@dataclass
class MultiFetchResult:
    """Result from multi-fetch operation."""

    success: bool
    message: str
    total_vods: int = 0
    successful_vods: int = 0
    skipped_vods: int = 0  # No markers found
    failed_vods: int = 0
    export_paths: list[Path] = field(default_factory=list)


@dataclass
class AutoModeState:
    """Mutable state for auto mode."""

    is_running: bool = False
    thread: threading.Thread | None = None
    last_error: str | None = None


# =============================================================================
# Output Directory Functions
# =============================================================================


def resolve_output_dir(
    config: "AppConfig",
    state_store: "StateStore",
) -> Path:
    """
    Get output directory from StateStore or config fallback.

    Precedence:
    1. StateStore value (if valid existing directory)
    2. config.output_dir (fallback)

    Args:
        config: Application configuration.
        state_store: State storage.

    Returns:
        Path to output directory.
    """
    stored_path = state_store.get_state(TRAY_OUTPUT_DIR_KEY)

    if stored_path:
        path = Path(stored_path)
        if path.is_dir():
            return path

    # Fallback to config
    return Path(config.output_dir)


def set_output_dir(
    state_store: "StateStore",
    output_dir: Path,
) -> None:
    """
    Persist output directory to StateStore.

    Args:
        state_store: State storage.
        output_dir: Directory path to persist.
    """
    state_store.set_state(TRAY_OUTPUT_DIR_KEY, str(output_dir))


# =============================================================================
# EDL Toggle Functions
# =============================================================================


def get_edl_enabled(state_store: "StateStore") -> bool:
    """
    Get EDL export enabled flag from StateStore.

    Args:
        state_store: State storage.

    Returns:
        True if EDL export is enabled, False otherwise (default).
    """
    stored_value = state_store.get_state(TRAY_EDL_ENABLED_KEY)

    if stored_value is None:
        return False

    # Treat "true"/"1"/"yes" as True (case-insensitive)
    normalized = str(stored_value).strip().lower()
    return normalized in ("true", "1", "yes")


def set_edl_enabled(state_store: "StateStore", enabled: bool) -> None:
    """
    Persist EDL export enabled flag to StateStore.

    Args:
        state_store: State storage.
        enabled: Whether EDL export is enabled.
    """
    state_store.set_state(TRAY_EDL_ENABLED_KEY, "true" if enabled else "false")


def get_export_formats_from_edl_flag(edl_enabled: bool) -> tuple[str, ...]:
    """
    Derive export formats list from EDL enabled flag.

    CSV is always included. EDL included if edl_enabled=True.

    Args:
        edl_enabled: Whether EDL export is enabled.

    Returns:
        Tuple of format strings ("csv",) or ("csv", "edl").
    """
    if edl_enabled:
        return ("csv", "edl")
    return ("csv",)


def get_manual_fetch_formats(
    config: "AppConfig",
    edl_enabled: bool,
) -> tuple[str, ...]:
    """
    Get export formats for manual fetch.

    CSV is always included. EDL included if edl_enabled=True.
    Config parameter kept for future extensibility.

    Args:
        config: App config (reserved for future use).
        edl_enabled: Whether EDL export is enabled.

    Returns:
        Tuple of format strings ("csv",) or ("csv", "edl").
    """
    return get_export_formats_from_edl_flag(edl_enabled)


# =============================================================================
# Manual Fetch Function
# =============================================================================


def run_manual_fetch(
    http_client: "requests.Session",
    config: "AppConfig",
    state_store: "StateStore",
    oauth: "TwitchOAuth",
    output_dir: Path,
    export_formats: tuple[str, ...],
    logger: logging.Logger,
) -> ManualFetchResult:
    """
    Execute manual marker fetch and export.

    This function:
    1. Gets a valid access token
    2. Fetches the latest video ID
    3. Fetches markers for that video
    4. Exports to the specified formats

    Manual fetch always exports (force=True semantics) - it does NOT
    respect processed_video dedupe since user intent is explicit.

    Args:
        http_client: HTTP session.
        config: App config.
        state_store: State storage.
        oauth: OAuth client for token access.
        output_dir: Export directory.
        export_formats: Formats to export.
        logger: Logger instance.

    Returns:
        ManualFetchResult with success status, message, and paths.
    """
    # Import here to avoid circular imports
    from twitch_marker_agent.core.twitch_oauth import TokenRefreshError
    from twitch_marker_agent.core.markers_api import (
        get_latest_video_id,
        get_video_title_and_date,
        get_stream_markers,
        MarkersAuthError,
        MarkersFetchError,
        MarkersNotFoundError,
    )
    from twitch_marker_agent.core.export_csv import export_markers_csv
    from twitch_marker_agent.core.export_edl import export_markers_edl

    # Step 1: Get valid access token
    try:
        access_token = oauth.get_valid_user_access_token(min_ttl_seconds=60)
    except TokenRefreshError:
        logger.warning("Manual fetch failed: not authenticated")
        return ManualFetchResult(
            success=False,
            message="Not logged in. Run auth-login first.",
        )

    # Step 2: Get latest video ID
    logger.info("Manual fetch: getting latest video ID")
    try:
        video_id = get_latest_video_id(
            http_client=http_client,
            config=config,
            access_token=access_token,
            user_id=config.broadcaster_id,
            logger=logger,
        )
    except Exception as e:
        logger.error(
            "Manual fetch: failed to get video ID: %s: %s",
            type(e).__name__,
            str(e),
        )
        return ManualFetchResult(
            success=False,
            message="Failed to get latest video. Check logs.",
        )

    if not video_id:
        logger.info("Manual fetch: no VOD found for broadcaster")
        return ManualFetchResult(
            success=False,
            message="No VOD found for broadcaster.",
        )

    logger.info("Manual fetch: fetching markers for video")

    # Step 3: Fetch markers
    try:
        marker_videos = get_stream_markers(
            http_client=http_client,
            config=config,
            access_token=access_token,
            user_id=config.broadcaster_id,
            video_id=video_id,
            logger=logger,
        )
    except MarkersNotFoundError:
        logger.info("Manual fetch: no markers found")
        return ManualFetchResult(
            success=False,
            message="No markers found for latest stream.",
        )
    except MarkersAuthError:
        logger.warning("Manual fetch: auth error (token may be expired)")
        return ManualFetchResult(
            success=False,
            message="Re-auth required. Run auth-login.",
        )
    except MarkersFetchError as e:
        logger.error("Manual fetch: failed to fetch markers: %s", type(e).__name__)
        return ManualFetchResult(
            success=False,
            message="Failed to fetch markers. Check logs.",
        )

    # Flatten markers
    all_markers = []
    for mv in marker_videos:
        all_markers.extend(mv.markers)

    if not all_markers:
        logger.info("Manual fetch: video has no markers")
        return ManualFetchResult(
            success=False,
            message="No markers found for latest stream.",
        )

    # Step 4: Export (always - no dedupe check for manual fetch)
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
        logger.warning("Manual fetch: VOD metadata unavailable; using fallback filename (%s)", type(e).__name__)


    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    # CSV export (always included)
    if "csv" in export_formats:
        try:
            csv_path = export_markers_csv(
                markers=all_markers,
                output_path=output_dir,
                config=config,
                video_id=video_id,
                stream_title=stream_title,
                stream_date=stream_date,
                logger=logger,
            )
            export_paths.append(csv_path)
            logger.info("Manual fetch: exported CSV to %s", csv_path.name)
        except Exception as e:
            logger.error("Manual fetch: CSV export failed: %s", type(e).__name__)

    # EDL export (if selected)
    if "edl" in export_formats:
        try:
            # Compute offset from config
            from twitch_marker_agent.core.export_edl import (
                timecode_to_seconds,
                DEFAULT_OFFSET_SECONDS,
            )

            edl_offset_seconds = 0
            if config.resolve_offset_enabled:
                try:
                    edl_offset_seconds = timecode_to_seconds(
                        config.resolve_offset_timecode
                    )
                except (ValueError, AttributeError):
                    logger.warning(
                        "Invalid resolve_offset_timecode, using default offset"
                    )
                    edl_offset_seconds = DEFAULT_OFFSET_SECONDS

            edl_path = export_markers_edl(
                markers=all_markers,
                output_path=output_dir,
                config=config,
                video_id=video_id,
                stream_title=stream_title,
                stream_date=stream_date,
                timecode_offset_seconds=edl_offset_seconds,
                logger=logger,
            )
            export_paths.append(edl_path)
            logger.info("Manual fetch: exported EDL to %s", edl_path.name)
        except Exception as e:
            logger.error("Manual fetch: EDL export failed: %s", type(e).__name__)

    if not export_paths:
        return ManualFetchResult(
            success=False,
            message="Export failed. Check logs.",
        )

    marker_count = len(all_markers)
    format_list = ", ".join(p.suffix.upper().lstrip(".") for p in export_paths)
    message = f"Exported {marker_count} markers ({format_list})"

    logger.info("Manual fetch complete: %d markers exported", marker_count)

    return ManualFetchResult(
        success=True,
        message=message,
        export_paths=export_paths,
        marker_count=marker_count,
    )


# =============================================================================
# Auto Mode Functions
# =============================================================================


def start_auto_mode(
    state: AutoModeState,
    agent: "AgentRunner",
    logger: logging.Logger,
) -> AutoModeState:
    """
    Start the agent runner in a worker thread.

    If already running, this is a no-op.

    Args:
        state: Current auto mode state.
        agent: AgentRunner instance.
        logger: Logger instance.

    Returns:
        Updated AutoModeState.
    """
    if state.is_running:
        logger.debug("Auto mode already running, ignoring start request")
        return state

    def worker() -> None:
        """Worker thread that runs the async agent loop."""
        try:
            asyncio.run(agent.run_async())
        except Exception as e:
            logger.error("Auto mode worker error: %s", type(e).__name__)

    thread = threading.Thread(
        target=worker,
        name="auto_mode_worker",
        daemon=True,
    )
    thread.start()

    logger.info("Auto mode started")

    return AutoModeState(
        is_running=True,
        thread=thread,
        last_error=None,
    )


def stop_auto_mode(
    state: AutoModeState,
    agent: "AgentRunner",
    logger: logging.Logger,
    timeout_seconds: float = 5.0,
) -> AutoModeState:
    """
    Stop the agent runner gracefully.

    If not running, this is a no-op.

    Args:
        state: Current auto mode state.
        agent: AgentRunner instance.
        logger: Logger instance.
        timeout_seconds: Max time to wait for thread to join.

    Returns:
        Updated AutoModeState.
    """
    if not state.is_running:
        logger.debug("Auto mode not running, ignoring stop request")
        return state

    logger.info("Stopping auto mode")

    # Request agent to stop
    agent.request_stop()

    # Wait for thread to finish
    if state.thread is not None:
        state.thread.join(timeout=timeout_seconds)

        if state.thread.is_alive():
            # Thread still running - keep accurate state
            logger.warning(
                "Stop requested, thread still running after timeout"
            )
            # Return state reflecting thread is still running
            return AutoModeState(
                is_running=True,
                thread=state.thread,
                last_error="Stop requested but thread did not exit",
            )
        else:
            logger.info("Auto mode stopped cleanly")

    # Get last error from agent
    last_error = agent.last_error

    return AutoModeState(
        is_running=False,
        thread=None,
        last_error=last_error,
    )


# =============================================================================
# Multi-Fetch Date Range Functions
# =============================================================================


def validate_date_range(
    start_date: date,
    end_date: date,
    max_days_back: int = 60,
) -> tuple[bool, str]:
    """
    Validate date range constraints for multi-fetch.

    Rules:
    - start_date <= end_date
    - end_date <= today
    - start_date >= today - max_days_back

    Args:
        start_date: Range start (inclusive).
        end_date: Range end (inclusive).
        max_days_back: Maximum days back from today (default: 60).

    Returns:
        (is_valid: bool, error_message: str)
        If valid, error_message is empty string.
    """
    today = date.today()
    earliest_allowed = today - timedelta(days=max_days_back)

    if start_date > end_date:
        return False, f"Start date ({start_date}) must be before or equal to end date ({end_date})"

    if end_date > today:
        return False, f"End date ({end_date}) cannot be in the future (today is {today})"

    if start_date < earliest_allowed:
        return False, f"Start date ({start_date}) cannot be more than {max_days_back} days ago (earliest: {earliest_allowed})"

    return True, ""


def run_multi_fetch(
    http_client,
    config,  
    state_store,
    oauth,
    output_dir,
    export_formats,
    start_date,
    end_date,
    logger,
):
    """Fetch and export markers from multiple VODs in date range."""
    from twitch_marker_agent.core.twitch_oauth import TokenRefreshError
    from twitch_marker_agent.core.videos_api import list_videos_in_date_range, VideosFetchError
    from twitch_marker_agent.core.markers_api import get_stream_markers, MarkersAuthError, MarkersFetchError, MarkersNotFoundError
    from twitch_marker_agent.core.export_csv import export_markers_csv
    from twitch_marker_agent.core.export_edl import (
        export_markers_edl,
        timecode_to_seconds,
        DEFAULT_OFFSET_SECONDS,
    )
    
    # Validate date range
    is_valid, error_msg = validate_date_range(start_date, end_date)
    if not is_valid:
        logger.warning("Multi-fetch: invalid date range: %s", error_msg)
        return MultiFetchResult(success=False, message=error_msg)
    
    # Get access token
    try:
        access_token = oauth.get_valid_user_access_token(min_ttl_seconds=60)
    except TokenRefreshError:
        logger.warning("Multi-fetch failed: not authenticated")
        return MultiFetchResult(success=False, message="Not logged in. Run auth-login first.")
    
    # List videos in date range
    logger.info("Multi-fetch: listing videos from %s to %s", start_date.isoformat(), end_date.isoformat())
    try:
        videos = list_videos_in_date_range(http_client=http_client, config=config, access_token=access_token, user_id=config.broadcaster_id, start_date=start_date, end_date=end_date, logger=logger)
    except VideosFetchError as e:
        logger.error("Multi-fetch: failed to list videos: %s", type(e).__name__)
        return MultiFetchResult(success=False, message=f"Failed to list videos: {str(e)}")
    
    if not videos:
        logger.info("Multi-fetch: no VODs found in date range")
        return MultiFetchResult(success=True, message=f"No VODs found between {start_date.isoformat()} and {end_date.isoformat()}.", total_vods=0)
    
    logger.info("Multi-fetch: found %d VODs in range", len(videos))
    
    # Process each VOD
    total_vods = len(videos)
    successful_vods = 0
    skipped_vods = 0
    failed_vods = 0
    all_export_paths = []
    
    output_dir.mkdir(parents=True, exist_ok=True)

    # Compute EDL offset for Resolve (like run_manual_fetch)
    edl_offset_seconds = 0
    if config.resolve_offset_enabled:
        try:
            edl_offset_seconds = timecode_to_seconds(config.resolve_offset_timecode)
        except (ValueError, AttributeError):
            logger.warning("Invalid resolve_offset_timecode, using default offset")
            edl_offset_seconds = DEFAULT_OFFSET_SECONDS
    
    for idx, video in enumerate(videos, start=1):
        logger.info("Multi-fetch: processing VOD %d/%d (id=%s)", idx, total_vods, video.video_id[:8])
        
        try:
            marker_videos = get_stream_markers(
                http_client=http_client,
                config=config,
                access_token=access_token,
                video_id=video.video_id,
                logger=logger,
            )
            
            all_markers = []
            for mv in marker_videos:
                all_markers.extend(mv.markers)
            
            if not all_markers:
                logger.info("Multi-fetch: VOD %s has no markers, skipping", video.video_id[:8])
                skipped_vods += 1
                continue
            
            logger.info("Multi-fetch: VOD %s has %d markers", video.video_id[:8], len(all_markers))
            
            stream_date_str = video.created_at.strftime("%Y-%m-%d")
            unique_title = f"{video.title}" if video.title else f"VOD-{video.video_id[:8]}"
            
            vod_exported_any = False
            
            if "csv" in export_formats:
                try:
                    csv_path = export_markers_csv(
                        markers=all_markers,
                        output_path=output_dir,
                        config=config,
                        video_id=video.video_id,
                        stream_title=unique_title,
                        stream_date=stream_date_str,
                        logger=logger,
                    )
                    all_export_paths.append(csv_path)
                    vod_exported_any = True
                    logger.info("Multi-fetch: exported CSV for VOD %s", video.video_id[:8])
                except Exception as e:
                    logger.error("Multi-fetch: CSV export failed for VOD %s: %s", video.video_id[:8], type(e).__name__)
            
            if "edl" in export_formats:
                try:
                    edl_path = export_markers_edl(
                        markers=all_markers,
                        output_path=output_dir,
                        config=config,
                        video_id=video.video_id,
                        stream_title=unique_title,
                        stream_date=stream_date_str,
                        timecode_offset_seconds=edl_offset_seconds,
                        logger=logger,
                    )
                    all_export_paths.append(edl_path)
                    vod_exported_any = True
                    logger.info("Multi-fetch: exported EDL for VOD %s", video.video_id[:8])
                except Exception as e:
                    logger.error("Multi-fetch: EDL export failed for VOD %s: %s", video.video_id[:8], type(e).__name__)
            
            # Only count as successful if at least one export succeeded
            if vod_exported_any:
                successful_vods += 1
            else:
                failed_vods += 1
        
        except MarkersNotFoundError:
            logger.info("Multi-fetch: no markers found for VOD %s", video.video_id[:8])
            skipped_vods += 1
            continue
        except MarkersAuthError:
            logger.error("Multi-fetch: auth error for VOD %s", video.video_id[:8])
            failed_vods += 1
            continue
        except MarkersFetchError as e:
            logger.error("Multi-fetch: failed to fetch markers for VOD %s: %s", video.video_id[:8], type(e).__name__)
            failed_vods += 1
            continue
        except Exception as e:
            logger.error("Multi-fetch: unexpected error for VOD %s: %s", video.video_id[:8], type(e).__name__)
            failed_vods += 1
            continue
    
    summary_parts = [f"Processed {total_vods} VODs:", f"{successful_vods} successful"]
    if skipped_vods > 0:
        summary_parts.append(f"{skipped_vods} skipped (no markers)")
    if failed_vods > 0:
        summary_parts.append(f"{failed_vods} failed")
    summary_msg = ", ".join(summary_parts) + "."
    logger.info("Multi-fetch complete: %s", summary_msg)
    
    return MultiFetchResult(success=True, message=summary_msg, total_vods=total_vods, successful_vods=successful_vods, skipped_vods=skipped_vods, failed_vods=failed_vods, export_paths=all_export_paths)
