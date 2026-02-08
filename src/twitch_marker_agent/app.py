"""
Tray application entrypoint for Twitch Marker Agent.

This module provides the Windows system tray interface using pystray.
The tray app runs in the background and provides manual marker export.

UI Features:
- Auto Mode: automatic marker export on stream end
- Manual fetch action: "Fetch Latest Stream Markers"
- Output format toggles (CSV/EDL) for manual fetch
- Output folder picker with persistence
- Windows startup toggle
- Exit action
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Callable

import pystray
from PIL import Image, ImageDraw

from twitch_marker_agent.tray_controller import (
    AutoModeState,
    ManualFetchResult,
    TrayState,
    get_edl_enabled,
    get_manual_fetch_formats,
    resolve_output_dir,
    run_manual_fetch,
    set_edl_enabled,
    set_output_dir,
    start_auto_mode,
    stop_auto_mode,
)

if TYPE_CHECKING:
    import requests
    from twitch_marker_agent.core.config import AppConfig
    from twitch_marker_agent.core.state_store import StateStore
    from twitch_marker_agent.core.twitch_oauth import TwitchOAuth


# =============================================================================
# Icon Creation
# =============================================================================


def create_tray_icon() -> Image.Image:
    """
    Create tray icon image via Pillow.

    Returns:
        64x64 RGBA image with Twitch-ish purple circle.
    """
    size = (64, 64)
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Purple circle (Twitch-ish color)
    draw.ellipse([4, 4, 60, 60], fill="#9147ff")

    # Simple "M" for markers in white
    draw.text((22, 18), "M", fill="white")

    return image


# =============================================================================
# Menu Builders
# =============================================================================


def _is_startup_checked(_: pystray.MenuItem) -> bool:
    """
    Check if Windows startup is enabled.

    Returns:
        True if startup entry exists, False otherwise.
        Always False on non-Windows platforms.
    """
    if sys.platform != "win32":
        return False

    from twitch_marker_agent.platform import windows_startup

    try:
        return windows_startup.is_startup_enabled()
    except windows_startup.StartupError:
        return False


def _is_auto_running(auto_state: AutoModeState) -> bool:
    """
    Check if auto mode worker thread is actually running.

    Derives state from thread.is_alive() rather than stale boolean.
    """
    return auto_state.thread is not None and auto_state.thread.is_alive()

def create_tray_menu(
    state: TrayState,
    auto_state: AutoModeState,
    state_store: "StateStore",
    on_fetch: Callable[[], None],
    on_toggle_edl: Callable[[], None],
    on_open_folder: Callable[[], None],
    on_change_folder: Callable[[], None],
    on_start_auto: Callable[[], None],
    on_stop_auto: Callable[[], None],
    on_toggle_startup: Callable[[], None],
    on_exit: Callable[[], None],
) -> pystray.Menu:
    """
    Build tray context menu.

    Args:
        state: Current tray state.
        auto_state: Current auto mode state.
        state_store: State storage for EDL flag.
        on_fetch: Callback for fetch action.
        on_toggle_edl: Callback for EDL toggle.
        on_open_folder: Callback to open output folder.
        on_change_folder: Callback to change output folder.
        on_start_auto: Callback to start auto mode.
        on_stop_auto: Callback to stop auto mode.
        on_toggle_startup: Callback to toggle Windows startup.
        on_exit: Callback to exit app.

    Returns:
        pystray Menu object.
    """

    def get_fetch_text(_: pystray.MenuItem) -> str:
        if state.is_fetching:
            return "Fetching..."
        return "Fetch Latest Stream Markers"

    def is_fetch_enabled(_: pystray.MenuItem) -> bool:
        return not state.is_fetching

    def get_auto_status(_: pystray.MenuItem) -> str:
        # Derive running state from actual thread status
        thread_alive = (
            auto_state.thread is not None and auto_state.thread.is_alive()
        )
        if thread_alive:
            return "Auto: Running"
        if auto_state.last_error:
            return "Auto: Error"
        return "Auto: Stopped"

    def is_auto_stopped(_: pystray.MenuItem) -> bool:
        # Stopped if no thread or thread is dead
        return auto_state.thread is None or not auto_state.thread.is_alive()

    def is_auto_running(_: pystray.MenuItem) -> bool:
        # Running only if thread exists and is alive
        return auto_state.thread is not None and auto_state.thread.is_alive()

    return pystray.Menu(
        # Auto mode section
        pystray.MenuItem(
            "Start Auto Mode",
            on_start_auto,
            visible=is_auto_stopped,
        ),
        pystray.MenuItem(
            "Stop Auto Mode",
            on_stop_auto,
            visible=is_auto_running,
        ),
        pystray.MenuItem(
            get_auto_status,
            None,
            enabled=False,
        ),
        pystray.Menu.SEPARATOR,
        # Manual fetch
        pystray.MenuItem(
            get_fetch_text,
            on_fetch,
            enabled=is_fetch_enabled,
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(
            "Additional Output Format",
            pystray.Menu(
                pystray.MenuItem(
                    "EDL",
                    on_toggle_edl,
                    checked=lambda _: get_edl_enabled(state_store),
                ),
            ),
        ),
        pystray.MenuItem(
            "Output Folder",
            pystray.Menu(
                pystray.MenuItem("Open Folder", on_open_folder),
                pystray.MenuItem("Change Folder...", on_change_folder),
            ),
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(
            "Start on Windows Login",
            on_toggle_startup,
            checked=_is_startup_checked,
            visible=lambda _: sys.platform == "win32",
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Exit", on_exit),
    )


# =============================================================================
# Folder Operations
# =============================================================================


def open_folder(path: Path) -> None:
    """
    Open folder in system file manager.

    Args:
        path: Folder path to open.
    """
    path.mkdir(parents=True, exist_ok=True)

    if sys.platform == "win32":
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
    else:
        subprocess.run(["xdg-open", str(path)], check=False)


def pick_folder(current: Path) -> Path | None:
    """
    Show folder picker dialog.

    Args:
        current: Current folder to start from.

    Returns:
        Selected folder path, or None if cancelled.
    """
    try:
        # Use tkinter for cross-platform folder picker
        import tkinter as tk
        from tkinter import filedialog

        # Create hidden root window
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)

        folder = filedialog.askdirectory(
            initialdir=str(current),
            title="Select Output Folder",
        )

        root.destroy()

        if folder:
            return Path(folder)
        return None

    except Exception:
        return None


# =============================================================================
# Tray Application
# =============================================================================


def run_tray_app(
    config: "AppConfig",
    state_store: "StateStore",
    http_client: "requests.Session",
    oauth: "TwitchOAuth",
    logger: logging.Logger,
) -> None:
    """
    Run the tray application main loop.

    Blocks until user exits.

    Args:
        config: Application configuration.
        state_store: State storage.
        http_client: HTTP client.
        oauth: OAuth client.
        logger: Logger instance.
    """
    # Initialize state
    state = TrayState()
    auto_state = AutoModeState()

    # Create AgentRunner (lazy, but we hold reference for start/stop)
    from twitch_marker_agent.core.agent_runner import AgentRunner

    agent = AgentRunner(
        config=config,
        state_store=state_store,
        http_client=http_client,
        oauth=oauth,
        logger=logger,
    )

    icon: pystray.Icon | None = None

    def update_menu() -> None:
        """Rebuild and update the menu."""
        nonlocal auto_state
        if icon:
            icon.menu = create_tray_menu(
                state=state,
                auto_state=auto_state,
                state_store=state_store,
                on_fetch=on_fetch,
                on_toggle_edl=on_toggle_edl,
                on_open_folder=on_open_folder,
                on_change_folder=on_change_folder,
                on_start_auto=on_start_auto,
                on_stop_auto=on_stop_auto,
                on_toggle_startup=on_toggle_startup,
                on_exit=on_exit,
            )
            icon.update_menu()

    def on_fetch() -> None:
        """Handle fetch action."""
        if state.is_fetching:
            return

        def fetch_worker() -> None:
            state.is_fetching = True
            update_menu()

            try:
                output_dir = resolve_output_dir(config, state_store)
                edl_enabled = get_edl_enabled(state_store)
                export_formats = get_manual_fetch_formats(config, edl_enabled)

                result: ManualFetchResult = run_manual_fetch(
                    http_client=http_client,
                    config=config,
                    state_store=state_store,
                    oauth=oauth,
                    output_dir=output_dir,
                    export_formats=export_formats,
                    logger=logger,
                )

                state.last_fetch_result = (
                    "success" if result.success else f"error:{result.message}"
                )

                # Show notification
                if icon:
                    try:
                        icon.notify(
                            result.message,
                            "Twitch Markers" if result.success else "Fetch Failed",
                        )
                    except Exception:
                        # notify may not be available on all platforms
                        logger.info("Fetch result: %s", result.message)

            except Exception as e:
                logger.error("Fetch failed: %s", type(e).__name__)
                state.last_fetch_result = f"error:{type(e).__name__}"
            finally:
                state.is_fetching = False
                update_menu()

        thread = threading.Thread(target=fetch_worker, daemon=True)
        thread.start()

    def on_toggle_edl() -> None:
        """Handle EDL toggle."""
        current = get_edl_enabled(state_store)
        set_edl_enabled(state_store, not current)
        update_menu()

    def on_open_folder() -> None:
        """Handle open folder action."""
        output_dir = resolve_output_dir(config, state_store)
        open_folder(output_dir)

    def on_change_folder() -> None:
        """Handle change folder action."""
        current = resolve_output_dir(config, state_store)
        new_folder = pick_folder(current)

        if new_folder:
            set_output_dir(state_store, new_folder)
            logger.info("Output folder changed to: %s", new_folder)

    def on_exit() -> None:
        """Handle exit action."""
        nonlocal auto_state
        logger.info("Tray app exiting")

        # Stop auto mode if thread is running
        if _is_auto_running(auto_state):
            auto_state = stop_auto_mode(auto_state, agent, logger)

        if icon:
            icon.stop()

    def on_start_auto() -> None:
        """Handle start auto mode action."""
        nonlocal auto_state
        # Only allow start if thread is not running
        if _is_auto_running(auto_state):
            return

        auto_state = start_auto_mode(auto_state, agent, logger)
        update_menu()

        # Notify user
        if icon:
            try:
                icon.notify("Auto mode started", "Twitch Markers")
            except Exception:
                pass

    def on_stop_auto() -> None:
        """Handle stop auto mode action."""
        nonlocal auto_state
        # Only attempt stop if thread is running
        if not _is_auto_running(auto_state):
            return

        auto_state = stop_auto_mode(auto_state, agent, logger)
        update_menu()

        # Notify user
        message = "Auto mode stopped"
        if auto_state.last_error:
            message = f"Auto mode stopped: {auto_state.last_error}"

        if icon:
            try:
                icon.notify(message, "Twitch Markers")
            except Exception:
                pass

    def on_toggle_startup() -> None:
        """Handle toggle startup on Windows login."""
        if sys.platform != "win32":
            return

        from twitch_marker_agent.platform import windows_startup

        try:
            if windows_startup.is_startup_enabled():
                windows_startup.disable_startup()
                logger.info("Windows startup disabled")
                if icon:
                    try:
                        icon.notify("Startup disabled", "Twitch Markers")
                    except Exception:
                        pass
            else:
                windows_startup.enable_startup()
                logger.info("Windows startup enabled")
                if icon:
                    try:
                        icon.notify("Will start on Windows login", "Twitch Markers")
                    except Exception:
                        pass
        except windows_startup.StartupError as e:
            logger.warning("Startup toggle failed: %s", str(e))
            if icon:
                try:
                    icon.notify(f"Startup toggle failed: {e}", "Twitch Markers")
                except Exception:
                    pass

        update_menu()

    # Create and run icon
    icon = pystray.Icon(
        name="twitch-marker-agent",
        icon=create_tray_icon(),
        title="Twitch Marker Agent",
        menu=create_tray_menu(
            state=state,
            auto_state=auto_state,
            state_store=state_store,
            on_fetch=on_fetch,
            on_toggle_edl=on_toggle_edl,
            on_open_folder=on_open_folder,
            on_change_folder=on_change_folder,
            on_start_auto=on_start_auto,
            on_stop_auto=on_stop_auto,
            on_toggle_startup=on_toggle_startup,
            on_exit=on_exit,
        ),
    )

    logger.info("Starting tray app")
    icon.run()


# =============================================================================
# Main Entrypoint
# =============================================================================


def main() -> None:
    """
    Main entrypoint for tray application.

    Loads configuration, initializes dependencies, and starts the tray app.
    """
    import requests

    from twitch_marker_agent.core.config import load_config
    from twitch_marker_agent.core.logging_setup import setup_logging
    from twitch_marker_agent.core.state_store import StateStore
    from twitch_marker_agent.core.twitch_oauth import TwitchOAuth

    # Load configuration
    config = load_config("local.config.json")

    # Setup logging
    logger = setup_logging(config, logger_name="twitch_marker_agent.tray")

    # Initialize state store
    state_store = StateStore(config.state_db_path)

    # Initialize HTTP client
    http_client = requests.Session()

    # Initialize OAuth
    oauth = TwitchOAuth(
        config=config,
        state_store=state_store,
        logger=logger,
        http_session=http_client,  # requests.Session()
    )


    try:
        run_tray_app(
            config=config,
            state_store=state_store,
            http_client=http_client,
            oauth=oauth,
            logger=logger,
        )
    finally:
        state_store.close()
        http_client.close()


if __name__ == "__main__":
    main()
