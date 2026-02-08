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
