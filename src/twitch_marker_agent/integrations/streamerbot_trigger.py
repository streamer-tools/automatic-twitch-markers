"""
Streamer.bot integration trigger for Twitch Marker Agent.

Provides a trigger interface that can be called from Streamer.bot
to initiate marker export manually or on stream events.

Streamer.bot Integration Options:
1. Execute Python script action
2. HTTP webhook (if agent runs a local server)
3. File-based trigger (watch a file for changes)

This module provides the Python script approach.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from twitch_marker_agent.core.agent import MarkerAgent
    from twitch_marker_agent.core.config import AppConfig


class StreamerbotTrigger:
    """
    Trigger interface for Streamer.bot integration.

    Allows Streamer.bot to trigger marker exports via:
    - Direct Python calls (if running in same process)
    - File-based signaling (write trigger file, agent watches)
    - Future: HTTP endpoint
    """

    def __init__(
        self,
        agent: MarkerAgent,
        config: AppConfig,
        logger: logging.Logger,
    ) -> None:
        """
        Initialize Streamer.bot trigger.

        Args:
            agent: MarkerAgent instance to control.
            config: Application configuration.
            logger: Logger instance.
        """
        self._agent = agent
        self._config = config
        self._logger = logger

    def trigger_export(self, video_id: str | None = None) -> dict[str, Any]:
        """
        Trigger marker export from Streamer.bot.

        Args:
            video_id: Optional specific video ID. If None, exports
                     from the most recent VOD.

        Returns:
            Result dictionary with status and export paths.

        Raises:
            NotImplementedError: Trigger not yet implemented.
        """
        # TODO: Implement Streamer.bot trigger
        # 1. If video_id not provided, get latest video
        # 2. Call agent.export_markers(video_id)
        # 3. Return result with paths
        self._logger.info(f"Streamer.bot trigger received: video_id={video_id}")
        raise NotImplementedError("TODO: Implement Streamer.bot trigger")

    def get_status(self) -> dict[str, Any]:
        """
        Get agent status for Streamer.bot display.

        Returns:
            Status dictionary.
        """
        return self._agent.get_status()


def create_trigger_file(trigger_dir: Path, video_id: str | None = None) -> Path:
    """
    Create a trigger file for file-based integration.

    Streamer.bot can call this to signal the agent to export.
    The agent watches trigger_dir for new files.

    Args:
        trigger_dir: Directory watched by the agent.
        video_id: Optional video ID to export.

    Returns:
        Path to created trigger file.
    """
    import json
    from datetime import datetime

    trigger_dir = Path(trigger_dir)
    trigger_dir.mkdir(parents=True, exist_ok=True)

    filename = f"trigger_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    trigger_path = trigger_dir / filename

    trigger_data = {
        "action": "export_markers",
        "video_id": video_id,
        "timestamp": datetime.now().isoformat(),
    }

    with trigger_path.open("w", encoding="utf-8") as f:
        json.dump(trigger_data, f, indent=2)

    return trigger_path


# Standalone script entry point for Streamer.bot Execute action
def main() -> None:
    """
    Entry point for Streamer.bot Execute Python Script action.

    Usage in Streamer.bot:
    1. Add "Execute Python Script" action
    2. Point to this file
    3. Agent will export latest markers

    Raises:
        NotImplementedError: Standalone trigger not yet implemented.
    """
    # TODO: Implement standalone trigger
    # 1. Load config
    # 2. Connect to running agent (or start new one)
    # 3. Trigger export
    # 4. Print result for Streamer.bot logging
    print("Streamer.bot trigger - Not yet implemented")
    raise NotImplementedError("TODO: Implement standalone Streamer.bot trigger")


if __name__ == "__main__":
    main()
