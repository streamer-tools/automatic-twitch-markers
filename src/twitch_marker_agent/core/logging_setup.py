"""
Logging setup for Twitch Marker Agent.

Configures file and console handlers with appropriate formatting.
Logs are written to the logs/ directory.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from twitch_marker_agent.core.config import AppConfig


def setup_logging(
    config: AppConfig,
    log_dir: Path | None = None,
    logger_name: str = "twitch_marker_agent",
) -> logging.Logger:
    """
    Configure and return a logger with file and console handlers.

    Args:
        config: Application configuration (for log level).
        log_dir: Directory for log files. Defaults to ./logs.
        logger_name: Name for the logger instance.

    Returns:
        Configured Logger instance.
    """
    from twitch_marker_agent.core.config import get_logging_level

    # Create logger
    logger = logging.getLogger(logger_name)
    logger.setLevel(get_logging_level(config))

    # Avoid adding duplicate handlers
    if logger.handlers:
        return logger

    # Log format
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(get_logging_level(config))
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler
    if log_dir is None:
        log_dir = Path("./logs")

    log_dir.mkdir(parents=True, exist_ok=True)

    # Log file with date
    log_filename = f"agent_{datetime.now().strftime('%Y%m%d')}.log"
    log_path = log_dir / log_filename

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)  # File always gets DEBUG
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    logger.debug(f"Logging initialized. File: {log_path}")

    return logger


def get_child_logger(parent: logging.Logger, name: str) -> logging.Logger:
    """
    Get a child logger that inherits parent's handlers.

    Args:
        parent: Parent logger instance.
        name: Child logger name suffix.

    Returns:
        Child logger instance.
    """
    return parent.getChild(name)
