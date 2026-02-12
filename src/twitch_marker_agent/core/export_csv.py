"""
CSV export for stream markers.

Exports markers in Twitch Highlighter-style CSV format compatible with
CSV→EDL converter workflows.

Canonical CSV Format (4 columns):
1. Timestamp (HH:MM:SS)
2. User Type
3. Username
4. Marker Title / Description
"""

from __future__ import annotations

import csv
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


def seconds_to_timestamp(seconds: int) -> str:
    """
    Convert seconds to human-readable timestamp HH:MM:SS.

    Uses floor behavior (no rounding).

    Args:
        seconds: Position in seconds (integer, already floored).

    Returns:
        Timestamp string in HH:MM:SS format.
    """
    # Ensure non-negative
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def sanitize_filename(title: str) -> str:
    """
    Remove illegal filesystem characters from a filename.

    Args:
        title: Original title string.

    Returns:
        Sanitized string safe for use in filenames.
    """
    # Remove illegal characters
    sanitized = ILLEGAL_FILENAME_CHARS.sub("", title)
    # Collapse multiple spaces
    sanitized = re.sub(r"\s+", " ", sanitized)
    # Strip leading/trailing whitespace
    return sanitized.strip()


def generate_csv_filename(
    video_id: str | None = None,
    stream_title: str | None = None,
    stream_date: str | None = None,
) -> str:
    """
    Generate CSV filename following documented conventions.

    Preferred: {YYYY-MM-DD} {Title} - Twitch Markers.csv
    Fallback: {video_id}_{YYYY-MM-DD} - Twitch Markers.csv

    Args:
        video_id: Twitch video ID (for fallback).
        stream_title: Stream title (may be None).
        stream_date: Stream date in YYYY-MM-DD format (may be None).

    Returns:
        Filename string (without path).
    """
    # Use current date as final fallback
    if not stream_date:
        stream_date = datetime.now().strftime("%Y-%m-%d")

    if stream_title:
        # Preferred format
        safe_title = sanitize_filename(stream_title)
        if safe_title:
            return f"{stream_date} {safe_title} - Twitch Markers.csv"

    # Fallback format
    if video_id:
        return f"{video_id}_{stream_date} - Twitch Markers.csv"

    # Ultimate fallback (shouldn't happen)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"markers_{timestamp} - Twitch Markers.csv"


def export_markers_csv(
    markers: list[Marker],
    output_path: Path,
    config: AppConfig,
    video_id: str | None = None,
    stream_title: str | None = None,
    stream_date: str | None = None,
    logger: logging.Logger | None = None,
) -> Path:
    """
    Export markers to canonical Twitch CSV format.

    Creates a 4-column CSV compatible with CSV→EDL converter workflows.

    Columns:
        1. Timestamp (HH:MM:SS)
        2. User Type
        3. Username
        4. Marker Title

    Args:
        markers: List of Marker objects to export.
        output_path: Directory to write CSV file.
        config: Application configuration.
        video_id: Optional video ID for filename fallback.
        stream_title: Optional stream title for filename.
        stream_date: Optional stream date (YYYY-MM-DD) for filename.
        logger: Optional logger.

    Returns:
        Path to the created CSV file.
    """
    # Ensure output directory exists
    output_path = Path(output_path)
    output_path.mkdir(parents=True, exist_ok=True)

    # Generate filename
    filename = generate_csv_filename(
        video_id=video_id,
        stream_title=stream_title,
        stream_date=stream_date,
    )
    file_path = output_path / filename

    if logger:
        logger.info("Exporting %d markers to CSV: %s", len(markers), file_path.name)

    # Write CSV with UTF-8 BOM for Excel compatibility
    with file_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_ALL)

        # Data rows
        for marker in markers:
            writer.writerow([
                seconds_to_timestamp(marker.position_seconds),
                marker.user_type,
                marker.username,
                marker.description,
            ])

    if logger:
        logger.info("CSV export complete: %s", file_path.name)

    return file_path
