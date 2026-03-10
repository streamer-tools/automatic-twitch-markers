"""
Windows startup integration for Twitch Marker Agent.

Provides functions to manage Windows startup registry entry so the
tray app can optionally launch on user login.

Uses HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run
for user-level startup (no admin required).

This module is Windows-specific. On non-Windows platforms, functions
return safe defaults or no-op.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Registry constants (Windows-only, used inside functions)
_RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
_APP_NAME = "AutomaticTwitchMarkers"


class StartupError(Exception):
    """
    Safe error for startup operations.

    Message contains no secrets or sensitive paths.
    """

    pass


def _quote_command_path(path: str | Path) -> str:
    """Quote a command path for registry command strings."""
    return f'"{str(path)}"'


def is_startup_enabled() -> bool:
    """
    Check if app is set to start on Windows login.

    Returns:
        True if startup entry exists, False otherwise.
        Always returns False on non-Windows platforms.
    """
    if sys.platform != "win32":
        return False

    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            _RUN_KEY_PATH,
            0,
            winreg.KEY_READ,
        ) as key:
            winreg.QueryValueEx(key, _APP_NAME)
            return True
    except FileNotFoundError:
        return False
    except OSError as e:
        # Unexpected registry error
        raise StartupError(f"Failed to check startup status: {type(e).__name__}") from e


def enable_startup(command: str | None = None) -> None:
    """
    Enable app startup on Windows login.

    Creates or updates the registry entry with the startup command.

    Args:
        command: Custom command string. If None, auto-generate using
            get_startup_command().

    Raises:
        StartupError: If operation fails or not on Windows.
    """
    if sys.platform != "win32":
        raise StartupError("Windows startup not available on this platform")

    import winreg

    cmd = command if command is not None else get_startup_command()

    try:
        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER,
            _RUN_KEY_PATH,
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            winreg.SetValueEx(key, _APP_NAME, 0, winreg.REG_SZ, cmd)
    except OSError as e:
        raise StartupError(f"Failed to enable startup: {type(e).__name__}") from e


def disable_startup() -> None:
    """
    Disable app startup on Windows login.

    Removes the registry entry. Idempotent: no error if entry doesn't exist.

    On non-Windows platforms, this is a no-op.

    Raises:
        StartupError: If operation fails unexpectedly.
    """
    if sys.platform != "win32":
        return  # No-op on non-Windows

    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            _RUN_KEY_PATH,
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            winreg.DeleteValue(key, _APP_NAME)
    except FileNotFoundError:
        # Value doesn't exist, treat as success (idempotent)
        pass
    except OSError as e:
        raise StartupError(f"Failed to disable startup: {type(e).__name__}") from e


def get_startup_command() -> str:
    """
    Generate startup command for current execution context.

    Returns:
        Command string with proper quoting for paths with spaces.
        - Frozen exe: returns quoted sys.executable
        - Source: returns pythonw.exe (or python.exe) -m twitch_marker_agent.app
    """
    if getattr(sys, "frozen", False):
        # Packaged exe: use executable directly
        exe_path = Path(sys.executable).resolve()
        return _quote_command_path(exe_path)

    # Running from source: prefer pythonw.exe to avoid console window
    python_dir = Path(sys.executable).parent
    pythonw = python_dir / "pythonw.exe"

    if pythonw.exists():
        interpreter = pythonw.resolve()
    else:
        interpreter = Path(sys.executable).resolve()

    return f'{_quote_command_path(interpreter)} -m twitch_marker_agent.app'
