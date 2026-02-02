"""
CLI entrypoint for Twitch Marker Agent.

This module provides command-line interface for running the agent
without the system tray. Useful for debugging and server deployments.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import NoReturn


def parse_args() -> argparse.Namespace:
    """
    Parse command line arguments.

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        prog="twitch-marker-agent",
        description="Automatically export Twitch stream markers after broadcasts end.",
    )
    parser.add_argument(
        "-c", "--config",
        type=Path,
        default=Path("config.json"),
        help="Path to configuration file (default: config.json)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose (DEBUG) logging",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 0.1.0",
    )
    return parser.parse_args()


def main() -> NoReturn:
    """
    Main CLI entrypoint.

    Parses arguments, loads configuration, initializes dependencies,
    and starts the agent. Runs until interrupted.

    Raises:
        NotImplementedError: CLI not yet implemented.
    """
    args = parse_args()

    # TODO: Implement CLI main
    # 1. Load config from args.config
    # 2. Setup logging (DEBUG if args.verbose)
    # 3. Initialize state store
    # 4. Initialize HTTP client (requests.Session)
    # 5. Create agent with injected dependencies
    # 6. Run agent.start() in a loop
    # 7. Handle SIGINT/SIGTERM for graceful shutdown

    print(f"Twitch Marker Agent v0.1.0")
    print(f"Config: {args.config}")
    print(f"Verbose: {args.verbose}")
    print()
    print("CLI not yet implemented. See README.md for next steps.")

    raise NotImplementedError("TODO: Implement CLI main entrypoint")


if __name__ == "__main__":
    main()
