"""
EDL (Edit Decision List) export for stream markers.

Exports markers in CMX 3600 EDL format compatible with
DaVinci Resolve, Premiere Pro, and other video editors.

EDL Format Notes:
- CMX 3600 is the industry standard
- Each marker becomes an edit event
- Timecode format: HH:MM:SS:FF (frames, not milliseconds)
- DaVinci Resolve may require +01:00:00:00 offset for certain workflows

TODO: Support seconds-based offset (e.g., "3600") alongside timecode.
      Would require timecode_fps config for frame calculation.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from twitch_marker_agent.core.config import AppConfig
    from twitch_marker_agent.core.markers_api import Marker


def parse_timecode(timecode: str) -> tuple[int, int, int, int]:
    """
    Parse timecode string HH:MM:SS:FF into components.

    Args:
        timecode: Timecode string in HH:MM:SS:FF format.

    Returns:
        Tuple of (hours, minutes, seconds, frames).

    Raises:
        ValueError: If timecode format is invalid.
    """
    parts = timecode.split(":")
    if len(parts) != 4:
        raise ValueError(f"Invalid timecode format: {timecode}. Expected HH:MM:SS:FF")

    try:
        return (int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3]))
    except ValueError as e:
        raise ValueError(f"Invalid timecode values: {timecode}") from e


def timecode_to_frames(timecode: str, fps: int = 24) -> int:
    """
    Convert timecode to total frame count.

    Args:
        timecode: Timecode string in HH:MM:SS:FF format.
        fps: Frames per second.

    Returns:
        Total number of frames.
    """
    hours, minutes, seconds, frames = parse_timecode(timecode)
    total_seconds = hours * 3600 + minutes * 60 + seconds
    return total_seconds * fps + frames


def frames_to_timecode(frames: int, fps: int = 24) -> str:
    """
    Convert frame count to timecode string.

    Args:
        frames: Total number of frames.
        fps: Frames per second.

    Returns:
        Timecode string in HH:MM:SS:FF format.
    """
    total_seconds, frame = divmod(frames, fps)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}:{frame:02d}"


def seconds_to_timecode(seconds: int, fps: int = 24) -> str:
    """
    Convert seconds to timecode string.

    Args:
        seconds: Position in seconds.
        fps: Frames per second.

    Returns:
        Timecode string in HH:MM:SS:FF format.
    """
    return frames_to_timecode(seconds * fps, fps)


def apply_offset(timecode: str, offset: str, fps: int = 24) -> str:
    """
    Add timecode offset to a timecode.

    Used for DaVinci Resolve workflows that require +01:00:00:00 offset.

    Args:
        timecode: Original timecode in HH:MM:SS:FF format.
        offset: Offset timecode to add in HH:MM:SS:FF format.
        fps: Frames per second.

    Returns:
        New timecode with offset applied.
    """
    original_frames = timecode_to_frames(timecode, fps)
    offset_frames = timecode_to_frames(offset, fps)
    return frames_to_timecode(original_frames + offset_frames, fps)


def export_markers_edl(
    markers: list[Marker],
    output_path: Path,
    config: AppConfig,
    video_id: str | None = None,
    title: str | None = None,
    logger: logging.Logger | None = None,
) -> Path:
    """
    Export markers to EDL file.

    Creates a CMX 3600 EDL with each marker as an edit event.
    If resolve_offset_enabled is True in config, applies the
    configured timecode offset.

    Args:
        markers: List of Marker objects to export.
        output_path: Directory to write EDL file.
        config: Application configuration.
        video_id: Optional video ID for filename.
        title: Optional title for EDL header.
        logger: Optional logger.

    Returns:
        Path to the created EDL file.
    """
    # Ensure output directory exists
    output_path = Path(output_path)
    output_path.mkdir(parents=True, exist_ok=True)

    # Generate filename
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    video_suffix = f"_{video_id}" if video_id else ""
    filename = f"markers{video_suffix}_{timestamp}.edl"
    file_path = output_path / filename

    edl_title = title or f"Stream Markers {timestamp}"
    fps = config.timecode_fps

    if logger:
        logger.info(f"Exporting {len(markers)} markers to EDL: {file_path}")
        if config.resolve_offset_enabled:
            logger.info(f"Applying DaVinci Resolve offset: {config.resolve_offset_timecode}")

    # Build EDL content
    lines = [
        f"TITLE: {edl_title}",
        f"FCM: NON-DROP FRAME",  # or DROP FRAME for 29.97fps
        "",
    ]

    for i, marker in enumerate(markers, start=1):
        # Convert position to timecode
        marker_tc = seconds_to_timecode(marker.position_seconds, fps)

        # Apply offset if enabled
        if config.resolve_offset_enabled:
            marker_tc = apply_offset(marker_tc, config.resolve_offset_timecode, fps)

        # EDL event format:
        # [Event#] [Reel] [Track] [Trans] [SrcIn] [SrcOut] [RecIn] [RecOut]
        # * FROM CLIP NAME: [Description]

        # Calculate out point (marker + 1 second)
        out_tc = apply_offset(marker_tc, "00:00:01:00", fps)

        lines.append(f"{i:03d}  AX       V     C        {marker_tc} {out_tc} {marker_tc} {out_tc}")

        # Add marker description as clip name
        description = marker.description or f"Marker {i}"
        # Sanitize description for EDL (remove special chars)
        description = description.replace("\n", " ").replace("\r", "")
        lines.append(f"* FROM CLIP NAME: {description}")
        lines.append("")

    # Write EDL file
    with file_path.open("w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    if logger:
        logger.info(f"EDL export complete: {file_path}")

    return file_path
