"""
Configuration loading and validation for Twitch Marker Agent.

This module loads config.json and validates all required fields,
exposing the configuration as a typed dataclass.
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_CLIENT_ID_PLACEHOLDER = "YOUR_TWITCH_CLIENT_ID"
DEFAULT_BROADCASTER_ID_PLACEHOLDER = "YOUR_BROADCASTER_USER_ID"
_PLACEHOLDER_CLIENT_IDS = {
    DEFAULT_CLIENT_ID_PLACEHOLDER.lower(),
    "your_client_id_here",
    "your_client_id",
    "your_client_id_here...",
}


def _default_bootstrap_template() -> dict[str, Any]:
    """Build an in-code fallback config template."""
    return {
        "client_id": DEFAULT_CLIENT_ID_PLACEHOLDER,
        "client_secret": "YOUR_TWITCH_CLIENT_SECRET",
        "redirect_uri": "http://localhost:3000/callback",
        "broadcaster_id": DEFAULT_BROADCASTER_ID_PLACEHOLDER,
        "output_dir": "./exports",
        "export_formats": ["csv", "edl"],
        "resolve_offset_enabled": True,
        "resolve_offset_timecode": "01:00:00:00",
        "timecode_fps": 60,
        "log_level": "INFO",
        "state_db_path": "./data/state.db",
        "retry": {
            "max_attempts": 5,
            "base_delay_seconds": 1.0,
            "max_delay_seconds": 60.0,
        },
    }


def _normalize_client_id(value: str | None) -> str:
    """Normalize client_id-like values for placeholder checks."""
    if value is None:
        return ""
    return str(value).strip().lower()


def is_placeholder_client_id(client_id: str) -> bool:
    """
    Check whether client_id is blank or a known placeholder value.

    Args:
        client_id: Candidate Twitch client_id value.

    Returns:
        True when value is blank or placeholder.
    """
    normalized = _normalize_client_id(client_id)
    if not normalized:
        return True
    if normalized in _PLACEHOLDER_CLIENT_IDS:
        return True
    return normalized.startswith("your_client_id_here")


def resolve_client_id_seed(
    client_id_seed: str | None,
    *,
    local_config_path: Path | None = None,
) -> str | None:
    """
    Resolve a usable client_id seed from explicit input or local config fallback.

    Resolution order:
    1. Provided ``client_id_seed`` if non-placeholder.
    2. ``local_config_path`` JSON ``client_id`` if present and non-placeholder.
    3. None

    Args:
        client_id_seed: Optional explicit seed value.
        local_config_path: Optional fallback config file path.

    Returns:
        Resolved non-placeholder client_id, otherwise None.
    """
    if client_id_seed:
        candidate = client_id_seed.strip()
        if candidate and not is_placeholder_client_id(candidate):
            return candidate

    if local_config_path is None:
        return None

    try:
        path = Path(local_config_path)
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return None
        client_id = str(data.get("client_id", "")).strip()
        if not client_id or is_placeholder_client_id(client_id):
            return None
        return client_id
    except Exception:
        return None


def _merge_template_data(
    base_template: dict[str, Any],
    override: dict[str, Any],
) -> dict[str, Any]:
    """Merge override template values into base template safely."""
    merged = dict(base_template)
    for key, value in override.items():
        if key == "retry" and isinstance(value, dict):
            retry_base = dict(base_template.get("retry", {}))
            retry_base.update(value)
            merged["retry"] = retry_base
            continue
        merged[key] = value
    return merged


def _load_frozen_bootstrap_template() -> dict[str, Any] | None:
    """Load bundled bootstrap template from frozen PyInstaller data if present."""
    if not getattr(sys, "frozen", False):
        return None

    meipass = getattr(sys, "_MEIPASS", None)
    if not meipass:
        return None

    bootstrap_path = Path(meipass) / "bootstrap" / "config.bootstrap.json"
    if not bootstrap_path.exists():
        return None

    try:
        with bootstrap_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception:
        return None
    return None


def _get_bootstrap_template_data(client_id_seed: str | None = None) -> dict[str, Any]:
    """Resolve config template data from bundled source with fallback defaults."""
    template = _default_bootstrap_template()
    frozen_template = _load_frozen_bootstrap_template()
    if frozen_template:
        template = _merge_template_data(template, frozen_template)

    if client_id_seed and not is_placeholder_client_id(client_id_seed):
        template["client_id"] = client_id_seed.strip()
    else:
        candidate = str(template.get("client_id", "")).strip()
        if is_placeholder_client_id(candidate):
            template["client_id"] = DEFAULT_CLIENT_ID_PLACEHOLDER
        else:
            template["client_id"] = candidate

    broadcaster_id = str(template.get("broadcaster_id", "")).strip()
    if not broadcaster_id:
        template["broadcaster_id"] = DEFAULT_BROADCASTER_ID_PLACEHOLDER

    return template


def write_bootstrap_template(output_path: Path, *, client_id_seed: str | None = None) -> None:
    """
    Write a bootstrap config template file used during packaging.

    Args:
        output_path: Destination file path.
        client_id_seed: Optional seeded client_id.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    data = _get_bootstrap_template_data(client_id_seed)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def ensure_config_exists(config_path: Path, *, client_id_seed: str | None = None) -> bool:
    """
    Ensure config.json exists, creating from bootstrap template when missing.

    Args:
        config_path: Target config path.
        client_id_seed: Optional seeded client_id.

    Returns:
        True when file was created, False when already present.
    """
    path = Path(config_path)
    if path.exists():
        return False

    path.parent.mkdir(parents=True, exist_ok=True)
    data = _get_bootstrap_template_data(client_id_seed)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")

    return True


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


def load_config(
    config_path: str | Path,
    *,
    base_dir: Path | None = None,
    allow_empty_broadcaster_id: bool = False,
) -> AppConfig:
    """
    Load and validate configuration from a JSON file.

    Args:
        config_path: Path to config.json file.
        base_dir: Base directory for resolving relative paths. If None, uses
            the config file's parent directory.
        allow_empty_broadcaster_id: If True, permits empty broadcaster_id.

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

    anchor_dir = Path(base_dir) if base_dir is not None else path.parent

    def _anchor_path(value: str, default: str) -> Path:
        raw_path = Path(value or default)
        if raw_path.is_absolute():
            return raw_path
        return anchor_dir / raw_path

    broadcaster_id = str(data["broadcaster_id"]).strip()
    if not allow_empty_broadcaster_id and not broadcaster_id:
        raise ValueError("broadcaster_id is required")

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
        broadcaster_id=broadcaster_id,
        output_dir=_anchor_path(str(data.get("output_dir", "./exports")), "./exports"),
        export_formats=tuple(data.get("export_formats", ["csv"])),
        resolve_offset_enabled=data.get("resolve_offset_enabled", False),
        resolve_offset_timecode=data.get("resolve_offset_timecode", "01:00:00:00"),
        timecode_fps=data.get("timecode_fps", 24),
        log_level=data.get("log_level", "INFO"),
        state_db_path=_anchor_path(
            str(data.get("state_db_path", "./data/state.db")),
            "./data/state.db",
        ),
        retry=retry_config,
    )


def write_broadcaster_id_if_empty(config_path: Path, broadcaster_id: str) -> bool:
    """
    Persist broadcaster_id to config.json only when currently empty.

    Args:
        config_path: Path to config.json.
        broadcaster_id: Broadcaster user ID to write.

    Returns:
        True if file was updated, False if unchanged.
    """
    path = Path(config_path)
    with path.open("r", encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)

    current = str(data.get("broadcaster_id", "")).strip()
    if current and current != DEFAULT_BROADCASTER_ID_PLACEHOLDER:
        return False

    data["broadcaster_id"] = str(broadcaster_id).strip()
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")

    return True


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
