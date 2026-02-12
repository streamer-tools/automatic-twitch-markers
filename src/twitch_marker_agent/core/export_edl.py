"""
EDL (Edit Decision List) export for stream markers.

Exports markers in DaVinci Resolve compatible EDL format with
marker metadata lines for proper marker import.

EDL Format:
- EDL preamble lines:
  - EDL
  - Title: Timeline 1
  - FCM: NON-DROP-FRAME
- Each marker as event + Resolve marker metadata line
- Marker duration: 1 frame (start :00, end :01)

Default offset: +3600 seconds (01:00:00:00) for Resolve timeline.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from twitch_marker_agent.core.config import AppConfig
    from twitch_marker_agent.core.markers_api import Marker


# Characters illegal in Windows filenames
ILLEGAL_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|]')

# Default Resolve offset: 1 hour
DEFAULT_OFFSET_SECONDS = 3600
DEFAULT_EDL_TITLE = "Timeline 1"


def timecode_to_seconds(timecode: str) -> int:
    """
    Parse timecode string HH:MM:SS:FF to total seconds.

    Args:
        timecode: Timecode in HH:MM:SS:FF format.

    Returns:
        Total seconds as integer (HH*3600 + MM*60 + SS).

    Raises:
        ValueError: If format is invalid, MM/SS out of bounds, or FF != 00.
    """
    parts = timecode.split(":")
    if len(parts) != 4:
        raise ValueError(f"Invalid timecode format: expected HH:MM:SS:FF, got '{timecode}'")

    # Validate two-digit format
    for i, part in enumerate(parts):
        if len(part) != 2 or not part.isdigit():
            raise ValueError(f"Invalid timecode format: each component must be two digits, got '{timecode}'")

    hours = int(parts[0])
    minutes = int(parts[1])
    seconds = int(parts[2])
    frames = int(parts[3])

    # Validate bounds
    if minutes > 59:
        raise ValueError(f"Invalid timecode: minutes must be 00-59, got {minutes:02d}")
    if seconds > 59:
        raise ValueError(f"Invalid timecode: seconds must be 00-59, got {seconds:02d}")
    if frames != 0:
        raise ValueError(f"Invalid timecode for offset: frames must be 00, got {frames:02d}")

    return hours * 3600 + minutes * 60 + seconds


def seconds_to_timecode(seconds: int, fps: int = 24, offset_seconds: int = 0) -> str:
    """
    Convert seconds to timecode string HH:MM:SS:FF.

    Uses floor behavior (position_seconds is already integer).

    Args:
        seconds: Position in seconds.
        fps: Frames per second (for documentation; frame always 00).
        offset_seconds: Offset to add (default 0).

    Returns:
        Timecode string in HH:MM:SS:FF format.
    """
    total_seconds = max(0, seconds + offset_seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    # Frame is always 00 since we only have second precision
    return f"{hours:02d}:{minutes:02d}:{secs:02d}:00"


def add_one_frame(timecode: str) -> str:
    """
    Add 1 frame to a timecode (change :00 to :01).

    Args:
        timecode: Timecode in HH:MM:SS:FF format ending in :00.

    Returns:
        Timecode with frame changed to :01.
    """
    if timecode.endswith(":00"):
        return timecode[:-2] + "01"
    return timecode


def sanitize_title(title: str) -> str:
    """
    Remove illegal filesystem characters from a title.

    Args:
        title: Original title string.

    Returns:
        Sanitized string safe for use in filenames and EDL.
    """
    sanitized = ILLEGAL_FILENAME_CHARS.sub("", title)
    sanitized = re.sub(r"\s+", " ", sanitized)
    return sanitized.strip()


def generate_edl_filename(
    video_id: str | None = None,
    stream_title: str | None = None,
    stream_date: str | None = None,
) -> str:
    """
    Generate EDL filename following documented conventions.

    Preferred: {YYYY-MM-DD} {Title} - Twitch Markers.edl
    Fallback: {video_id}_{YYYY-MM-DD} - Twitch Markers.edl

    Args:
        video_id: Twitch video ID (for fallback).
        stream_title: Stream title (may be None).
        stream_date: Stream date in YYYY-MM-DD format (may be None).

    Returns:
        Filename string (without path).
    """
    if not stream_date:
        stream_date = datetime.now().strftime("%Y-%m-%d")

    if stream_title:
        safe_title = sanitize_title(stream_title)
        if safe_title:
            return f"{stream_date} {safe_title} - Twitch Markers.edl"

    if video_id:
        return f"{video_id}_{stream_date} - Twitch Markers.edl"

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"markers_{timestamp} - Twitch Markers.edl"


def format_marker_metadata(marker: "Marker") -> str:
    """
    Format Resolve marker metadata line.

    Format: |C:ResolveColorBlue |M:{description} by {username} [{user_type}] |D:1

    Args:
        marker: Marker object with description, username, user_type.

    Returns:
        Formatted metadata line.
    """
    description = marker.description or "Marker"
    # Sanitize description (remove newlines)
    description = description.replace("\n", " ").replace("\r", "")
    
    return f" |C:ResolveColorBlue |M:{description} by {marker.username} [{marker.user_type}] |D:1"


def export_markers_edl(
    markers: list["Marker"],
    output_path: Path,
    config: "AppConfig",
    video_id: str | None = None,
    stream_title: str | None = None,
    stream_date: str | None = None,
    timecode_offset_seconds: int = DEFAULT_OFFSET_SECONDS,
    logger: logging.Logger | None = None,
) -> Path:
    """
    Export markers to DaVinci Resolve compatible EDL.

    Creates an EDL with each marker as an event with Resolve marker metadata.
    Default offset is +3600 seconds (01:00:00:00) for Resolve timeline.

    Args:
        markers: List of Marker objects to export.
        output_path: Directory to write EDL file.
        config: Application configuration (for fps).
        video_id: Optional video ID for filename fallback.
        stream_title: Optional stream title for filename.
        stream_date: Optional stream date (YYYY-MM-DD).
        timecode_offset_seconds: Offset in seconds (default 3600 = +1 hour).
        logger: Optional logger.

    Returns:
        Path to the created EDL file.
    """
    output_path = Path(output_path)
    output_path.mkdir(parents=True, exist_ok=True)

    filename = generate_edl_filename(
        video_id=video_id,
        stream_title=stream_title,
        stream_date=stream_date,
    )
    file_path = output_path / filename

    fps = config.timecode_fps

    if logger:
        logger.info("Exporting %d markers to EDL: %s", len(markers), file_path.name)
        if timecode_offset_seconds > 0:
            offset_tc = seconds_to_timecode(0, fps, timecode_offset_seconds)
            logger.info("Applying timecode offset: +%d seconds (%s)", timecode_offset_seconds, offset_tc)

    # Build EDL content
    lines: list[str] = [
        "EDL",
        f"Title: {DEFAULT_EDL_TITLE}",
        "FCM: NON-DROP-FRAME",
        "",
    ]

    for i, marker in enumerate(markers, start=0):
        # Convert position to timecode with offset
        start_tc = seconds_to_timecode(marker.position_seconds, fps, timecode_offset_seconds)
        end_tc = add_one_frame(start_tc)

        # Event line format:
        # {idx:03}  001      V    C        {startTC} {endTC} {startTC} {endTC}
        event_line = f"{i:03d}  001      V    C        {start_tc} {end_tc} {start_tc} {end_tc}  "
        lines.append(event_line)

        # Resolve marker metadata line
        metadata_line = format_marker_metadata(marker)
        lines.append(metadata_line)
        lines.append("")

    # Write EDL file
    with file_path.open("w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    if logger:
        logger.info("EDL export complete: %s", file_path.name)

    return file_path
