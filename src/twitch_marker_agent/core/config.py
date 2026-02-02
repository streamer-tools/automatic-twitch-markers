"""
Configuration loading and validation for Twitch Marker Agent.

This module loads config.json and validates all required fields,
exposing the configuration as a typed dataclass.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RetryConfig:
    """Configuration for retry/backoff behavior."""

    max_attempts: int
    base_delay_seconds: float
    max_delay_seconds: float

    def __post_init__(self) -> None:
        """Validate retry configuration values."""
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if self.base_delay_seconds <= 0:
            raise ValueError("base_delay_seconds must be > 0")
        if self.max_delay_seconds < self.base_delay_seconds:
            raise ValueError("max_delay_seconds must be >= base_delay_seconds")


@dataclass(frozen=True)
class AppConfig:
    """
    Application configuration loaded from config.json.

    All fields are validated on construction. Paths are converted
    to pathlib.Path objects for cross-platform compatibility.
    """

    client_id: str
    client_secret: str
    redirect_uri: str
    broadcaster_id: str
    output_dir: Path
    export_formats: tuple[str, ...]
    resolve_offset_enabled: bool
    resolve_offset_timecode: str
    timecode_fps: int
    log_level: str
    state_db_path: Path
    retry: RetryConfig

    def __post_init__(self) -> None:
        """Validate configuration values."""
        # Validate required strings are not empty
        if not self.client_id:
            raise ValueError("client_id is required")
        if not self.broadcaster_id:
            raise ValueError("broadcaster_id is required")

        # Validate export formats
        valid_formats = {"csv", "edl"}
        for fmt in self.export_formats:
            if fmt not in valid_formats:
                raise ValueError(f"Invalid export format: {fmt}. Must be one of {valid_formats}")

        # Validate log level
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if self.log_level.upper() not in valid_levels:
            raise ValueError(f"Invalid log_level: {self.log_level}. Must be one of {valid_levels}")

        # Validate timecode format (HH:MM:SS:FF)
        if self.resolve_offset_enabled:
            parts = self.resolve_offset_timecode.split(":")
            if len(parts) != 4:
                raise ValueError(
                    f"Invalid timecode format: {self.resolve_offset_timecode}. "
                    "Must be HH:MM:SS:FF"
                )

        # Validate timecode_fps
        if self.timecode_fps < 1:
            raise ValueError("timecode_fps must be >= 1")


def load_config(config_path: str | Path) -> AppConfig:
    """
    Load and validate configuration from a JSON file.

    Args:
        config_path: Path to config.json file.

    Returns:
        Validated AppConfig instance.

    Raises:
        FileNotFoundError: If config file doesn't exist.
        json.JSONDecodeError: If config file is not valid JSON.
        KeyError: If required config keys are missing.
        ValueError: If config values are invalid.
    """
    path = Path(config_path)

    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)

    # Extract retry config
    retry_data = data.get("retry", {})
    retry_config = RetryConfig(
        max_attempts=retry_data.get("max_attempts", 5),
        base_delay_seconds=retry_data.get("base_delay_seconds", 1.0),
        max_delay_seconds=retry_data.get("max_delay_seconds", 60.0),
    )

    # Build AppConfig
    return AppConfig(
        client_id=data["client_id"],
        client_secret=data.get("client_secret", ""),
        redirect_uri=data.get("redirect_uri", "http://localhost:3000/callback"),
        broadcaster_id=data["broadcaster_id"],
        output_dir=Path(data.get("output_dir", "./exports")),
        export_formats=tuple(data.get("export_formats", ["csv"])),
        resolve_offset_enabled=data.get("resolve_offset_enabled", False),
        resolve_offset_timecode=data.get("resolve_offset_timecode", "01:00:00:00"),
        timecode_fps=data.get("timecode_fps", 24),
        log_level=data.get("log_level", "INFO"),
        state_db_path=Path(data.get("state_db_path", "./data/state.db")),
        retry=retry_config,
    )


def get_logging_level(config: AppConfig) -> int:
    """
    Convert config log_level string to logging module constant.

    Args:
        config: Application configuration.

    Returns:
        Logging level constant (e.g., logging.INFO).
    """
    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }
    return level_map.get(config.log_level.upper(), logging.INFO)
