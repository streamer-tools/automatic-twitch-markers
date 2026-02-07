# Windows Startup Integration

## Overview

This document describes the Windows startup integration feature, allowing the tray app to optionally launch on user login.

## Startup Mechanism

Uses Windows Registry: `HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run`

- Uses only stdlib `winreg` module (no new dependencies)
- Industry-standard approach for user-level startup apps
- Survives reboots, user-controlled

## Module Location

**File:** `src/twitch_marker_agent/platform/windows_startup.py`

- Lives in `platform/` subpackage (not `core/`) - allowed to be Windows-specific
- Framework-agnostic: no pystray imports
- DI-friendly: functions accept app_name and command strings

## Public API

```python
class StartupError(Exception):
    """Safe error for startup operations (message contains no secrets)."""
    pass

def is_startup_enabled() -> bool:
    """Check if app is set to start on Windows login."""
    ...

def enable_startup(command: str | None = None) -> None:
    """Enable app startup on Windows login.
    
    Args:
        command: Custom command string. If None, auto-generate.
    
    Raises:
        StartupError: If operation fails.
    """
    ...

def disable_startup() -> None:
    """Disable app startup on Windows login (idempotent)."""
    ...

def get_startup_command() -> str:
    """Generate startup command for current execution context."""
    ...
```

## Command Generation

```python
def get_startup_command() -> str:
    if getattr(sys, 'frozen', False):
        # Packaged exe: use executable directly
        return f'"{sys.executable}"'
    else:
        # Running from source: use pythonw.exe to avoid console
        python_dir = Path(sys.executable).parent
        pythonw = python_dir / "pythonw.exe"
        if pythonw.exists():
            return f'"{pythonw}" -m twitch_marker_agent.app'
        else:
            return f'"{sys.executable}" -m twitch_marker_agent.app'
```

## Cross-Platform Behavior

- Menu item hidden on non-Windows platforms
- `winreg` import guarded inside functions
- `disable_startup()` is a no-op on non-Windows

## Tray UI

Menu item placement (after Output Folder, before Exit):

```python
pystray.MenuItem(
    "Start on Windows Login",
    on_toggle_startup,
    checked=lambda _: is_startup_enabled(),
    visible=lambda _: sys.platform == "win32",
)
```

## Testing Strategy

All tests use `unittest.mock.patch` - NO real registry access:

| Test | Coverage |
|------|----------|
| `test_is_startup_enabled_true` | Registry key exists |
| `test_is_startup_enabled_false` | Key missing |
| `test_enable_startup_creates_entry` | SetValueEx called |
| `test_disable_startup_removes_entry` | DeleteValue called |
| `test_disable_startup_noop_missing` | No error when missing |
| `test_get_command_frozen` | Packaged exe path |
| `test_get_command_source` | pythonw.exe -m ... |

**CRITICAL:** No tests trigger system restart/shutdown or touch real registry.
