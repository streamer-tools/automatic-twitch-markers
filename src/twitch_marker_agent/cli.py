"""
CLI entrypoint for Twitch Marker Agent.

This module provides command-line interface for running the agent
without the system tray. Useful for debugging and server deployments.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import NoReturn


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    """
    Parse command line arguments.

    Args:
        args: Arguments to parse. Defaults to sys.argv[1:].

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

    # Subcommands
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # auth-login subcommand
    auth_login_parser = subparsers.add_parser(
        "auth-login",
        help="Authenticate with Twitch via browser OAuth flow",
    )
    auth_login_parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Timeout in seconds for OAuth callback (default: 120)",
    )

    return parser.parse_args(args)


def cmd_auth_login(args: argparse.Namespace) -> int:
    """
    Handle the auth-login command.

    Args:
        args: Parsed arguments.

    Returns:
        Exit code (0 for success, non-zero for error).
    """
    from twitch_marker_agent.core.config import load_config
    from twitch_marker_agent.core.logging_setup import setup_logging
    from twitch_marker_agent.core.state_store import StateStore
    from twitch_marker_agent.core.twitch_oauth import (
        OAuthCancelledError,
        OAuthTimeoutError,
        TokenExchangeError,
        TwitchOAuth,
    )

    # Load configuration
    try:
        config = load_config(args.config)
    except FileNotFoundError:
        print(f"Error: Configuration file not found: {args.config}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error loading configuration: {e}", file=sys.stderr)
        return 1

    # Setup logging
    logger = setup_logging(config)
    if args.verbose:
        import logging
        logger.setLevel(logging.DEBUG)

    # Initialize state store
    state_store = StateStore(config.state_db_path)

    try:
        # Create OAuth client
        oauth = TwitchOAuth(
            config=config,
            state_store=state_store,
            logger=logger,
        )

        # Run interactive login
        print("Starting Twitch OAuth login...")
        print("A browser window will open for authorization.")
        print()

        oauth.interactive_login(timeout_seconds=args.timeout)

        print()
        print("✓ Authentication successful!")
        print("  Tokens have been securely stored.")
        print("  You can now run the marker agent.")

        return 0

    except OAuthCancelledError as e:
        print(f"\nAuthentication cancelled: {e}", file=sys.stderr)
        return 1

    except OAuthTimeoutError as e:
        print(f"\n{e}", file=sys.stderr)
        return 1

    except TokenExchangeError as e:
        print(f"\nToken exchange failed: {e}", file=sys.stderr)
        return 1

    except KeyboardInterrupt:
        print("\n\nAuthentication cancelled by user.", file=sys.stderr)
        return 130

    finally:
        state_store.close()


def main() -> NoReturn:
    """
    Main CLI entrypoint.

    Parses arguments and dispatches to appropriate command handler.
    """
    args = parse_args()

    if args.command == "auth-login":
        exit_code = cmd_auth_login(args)
        sys.exit(exit_code)

    elif args.command is None:
        # No subcommand - show help for now
        # TODO: In future, this will start the agent
        print("Twitch Marker Agent v0.1.0")
        print()
        print("Usage:")
        print("  twitch-marker-agent auth-login   Authenticate with Twitch")
        print("  twitch-marker-agent --help       Show all options")
        print()
        print("Run 'auth-login' first to authenticate, then start the agent.")
        sys.exit(0)

    else:
        print(f"Unknown command: {args.command}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
