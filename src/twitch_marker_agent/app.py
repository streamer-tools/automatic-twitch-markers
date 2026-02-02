"""
Tray application entrypoint for Twitch Marker Agent.

This module provides the Windows system tray interface using pystray.
The tray app runs in the background and manages the MarkerAgent lifecycle.

Future implementation will include:
- System tray icon with status indicator
- Right-click menu for configuration
- Notifications on marker export
- Start/stop controls
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from twitch_marker_agent.core.agent import MarkerAgent
    from twitch_marker_agent.core.config import AppConfig


def create_tray_app(config: AppConfig, agent: MarkerAgent, logger: logging.Logger) -> None:
    """
    Create and run the system tray application.

    Args:
        config: Application configuration.
        agent: The MarkerAgent instance to control.
        logger: Logger for tray app events.

    Raises:
        NotImplementedError: Tray app not yet implemented.
    """
    # TODO: Implement tray app with pystray
    # - Create tray icon from assets/icon.png
    # - Add menu items: Start, Stop, Settings, Exit
    # - Handle icon click events
    # - Show notifications on export completion
    raise NotImplementedError("TODO: Implement tray app with pystray")


def main() -> None:
    """
    Main entrypoint for tray application.

    Loads configuration, initializes the agent, and starts the tray app.
    """
    # TODO: Implement main tray entrypoint
    # 1. Load config
    # 2. Setup logging
    # 3. Initialize state store
    # 4. Create agent with dependencies
    # 5. Start tray app
    raise NotImplementedError("TODO: Implement tray app main entrypoint")


if __name__ == "__main__":
    main()
