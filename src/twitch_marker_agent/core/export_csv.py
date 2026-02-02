"""
CSV export for stream markers.

Exports markers in Twitch-style CSV format compatible with
spreadsheet applications and other tools.

CSV Format:
- Columns: Marker ID, Description, Position (seconds), Position (timecode), Created At
- UTF-8 encoding with BOM for Excel compatibility
- Comma-separated with quoted strings
"""

from __future__ import annotations

import csv
import logging
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from twitch_marker_agent.core.config import AppConfig
    from twitch_marker_agent.core.markers_api import Marker


def seconds_to_timecode(seconds: int, fps: int = 24) -> str:
    """
    Convert seconds to timecode format HH:MM:SS:FF.

    Args:
        seconds: Position in seconds.
        fps: Frames per second for frame calculation.

    Returns:
        Timecode string in HH:MM:SS:FF format.
    """
    td = timedelta(seconds=seconds)
    hours, remainder = divmod(int(td.total_seconds()), 3600)
    minutes, secs = divmod(remainder, 60)
    # Frame is always 00 since we only have second precision
    frames = 0
    return f"{hours:02d}:{minutes:02d}:{secs:02d}:{frames:02d}"


def seconds_to_timestamp(seconds: int) -> str:
    """
    Convert seconds to human-readable timestamp HH:MM:SS.

    Args:
        seconds: Position in seconds.

    Returns:
        Timestamp string in HH:MM:SS format.
    """
    td = timedelta(seconds=seconds)
    hours, remainder = divmod(int(td.total_seconds()), 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def export_markers_csv(
    markers: list[Marker],
    output_path: Path,
    config: AppConfig,
    video_id: str | None = None,
    logger: logging.Logger | None = None,
) -> Path:
    """
    Export markers to CSV file.

    Creates a Twitch-style CSV with marker details.

    Args:
        markers: List of Marker objects to export.
        output_path: Directory to write CSV file.
        config: Application configuration.
        video_id: Optional video ID for filename.
        logger: Optional logger.

    Returns:
        Path to the created CSV file.
    """
    # Ensure output directory exists
    output_path = Path(output_path)
    output_path.mkdir(parents=True, exist_ok=True)

    # Generate filename
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    video_suffix = f"_{video_id}" if video_id else ""
    filename = f"markers{video_suffix}_{timestamp}.csv"
    file_path = output_path / filename

    if logger:
        logger.info(f"Exporting {len(markers)} markers to CSV: {file_path}")

    # Write CSV with UTF-8 BOM for Excel compatibility
    with file_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_ALL)

        # Header row
        writer.writerow([
            "Marker ID",
            "Description",
            "Position (seconds)",
            "Position (timecode)",
            "Position (HH:MM:SS)",
            "Created At",
        ])

        # Data rows
        for marker in markers:
            writer.writerow([
                marker.id,
                marker.description,
                marker.position_seconds,
                seconds_to_timecode(marker.position_seconds, config.timecode_fps),
                seconds_to_timestamp(marker.position_seconds),
                marker.created_at,
            ])

    if logger:
        logger.info(f"CSV export complete: {file_path}")

    return file_path
