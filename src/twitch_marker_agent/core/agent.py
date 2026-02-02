"""
Main orchestrator agent for Twitch Marker Agent.

Coordinates all core modules to:
1. Authenticate with Twitch OAuth
2. Connect to EventSub WebSocket
3. Subscribe to stream.offline events
4. Fetch and export markers when streams end
5. Track processed streams to prevent duplicates

Dependencies are injected via constructor for testability
and to maintain framework-agnostic design.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import requests
    from twitch_marker_agent.core.config import AppConfig
    from twitch_marker_agent.core.state_store import StateStore


class MarkerAgent:
    """
    Main orchestrator for the Twitch Marker Agent.

    Coordinates OAuth, EventSub, marker fetching, and export.
    Designed to be controlled by CLI, tray app, or web backend.
    """

    def __init__(
        self,
        config: AppConfig,
        state_store: StateStore,
        http_client: requests.Session,
        logger: logging.Logger,
    ) -> None:
        """
        Initialize the MarkerAgent with injected dependencies.

        Args:
            config: Application configuration.
            state_store: Persistent state storage.
            http_client: HTTP client for API requests.
            logger: Logger instance.
        """
        self._config = config
        self._state_store = state_store
        self._http_client = http_client
        self._logger = logger

        self._is_running: bool = False
        self._eventsub_client: Any = None  # Will be EventSubClient
        self._oauth: Any = None  # Will be TwitchOAuth

    @property
    def is_running(self) -> bool:
        """Check if agent is currently running."""
        return self._is_running

    def start(self) -> None:
        """
        Start the marker agent.

        Initializes OAuth, connects to EventSub, and begins
        listening for stream.offline events.

        Raises:
            NotImplementedError: Agent start not yet implemented.
        """
        # TODO: Implement agent start
        # 1. Initialize TwitchOAuth with state_store
        # 2. Check for existing refresh token
        #    - If missing, trigger browser login
        #    - If present, refresh access token
        # 3. Initialize EventSubClient
        # 4. Connect to EventSub WebSocket
        # 5. Subscribe to stream.offline for broadcaster_id
        # 6. Set self._is_running = True
        # 7. Run event loop
        self._logger.info("Starting Marker Agent...")
        raise NotImplementedError("TODO: Implement agent start")

    def stop(self) -> None:
        """
        Stop the marker agent gracefully.

        Disconnects from EventSub and cleans up resources.

        Raises:
            NotImplementedError: Agent stop not yet implemented.
        """
        # TODO: Implement agent stop
        # 1. Set self._is_running = False
        # 2. Call eventsub_client.shutdown()
        # 3. Close state_store
        # 4. Log shutdown complete
        self._logger.info("Stopping Marker Agent...")
        raise NotImplementedError("TODO: Implement agent stop")

    def on_stream_offline(self, event_data: dict[str, Any]) -> None:
        """
        Handle stream.offline event from EventSub.

        Waits briefly for Twitch to process the VOD, then fetches
        markers and exports them.

        Args:
            event_data: EventSub notification payload.

        Raises:
            NotImplementedError: Event handling not yet implemented.
        """
        # TODO: Implement stream.offline handler
        # 1. Extract broadcaster info from event_data
        # 2. Wait/retry for VOD to be available (Twitch processing delay)
        # 3. Get latest video ID
        # 4. Check if already processed (via state_store)
        # 5. Fetch markers from API
        # 6. Export to configured formats (CSV, EDL)
        # 7. Mark as processed in state_store
        # 8. Log success
        self._logger.info(f"Stream offline event received: {event_data}")
        raise NotImplementedError("TODO: Implement stream.offline handler")

    def export_markers(
        self,
        video_id: str,
        force: bool = False,
    ) -> list[Path]:
        """
        Fetch and export markers for a specific video.

        Args:
            video_id: Twitch VOD ID to export markers from.
            force: If True, export even if already processed.

        Returns:
            List of paths to exported files.

        Raises:
            NotImplementedError: Export not yet implemented.
        """
        # TODO: Implement marker export
        # 1. Check if already processed (skip if not force)
        # 2. Get access token
        # 3. Fetch markers via markers_api
        # 4. Export to CSV if configured
        # 5. Export to EDL if configured
        # 6. Mark as processed
        # 7. Return list of export paths
        self._logger.info(f"Exporting markers for video: {video_id}")
        raise NotImplementedError("TODO: Implement marker export")

    def trigger_oauth_login(self) -> bool:
        """
        Trigger OAuth browser login flow.

        Used by UI to initiate authentication.

        Returns:
            True if login succeeded, False otherwise.

        Raises:
            NotImplementedError: OAuth trigger not yet implemented.
        """
        # TODO: Implement OAuth login trigger
        # 1. Initialize TwitchOAuth if not already
        # 2. Call oauth.login_browser()
        # 3. Return success status
        raise NotImplementedError("TODO: Implement OAuth login trigger")

    def get_status(self) -> dict[str, Any]:
        """
        Get current agent status for UI display.

        Returns:
            Dictionary with status information.
        """
        return {
            "is_running": self._is_running,
            "has_oauth_token": self._oauth.has_refresh_token() if self._oauth else False,
            "eventsub_connected": (
                self._eventsub_client.is_connected if self._eventsub_client else False
            ),
            "processed_streams": self._state_store.get_processed_count(),
        }
