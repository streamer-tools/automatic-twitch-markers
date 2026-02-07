# Polish Patch

## Overview

This document describes the polish patch for reliability and documentation cleanup.

## Changes

### 1) windows_startup.py Robustness

**File:** `platform/windows_startup.py`

Replace `OpenKey` with `CreateKeyEx` in `enable_startup()` for robustness:
- `CreateKeyEx` creates the key if missing OR opens if exists
- Handles unusual Windows registry states gracefully

### 2) Auto Mode State Guards

**File:** `app.py`

Replace stale `is_running` boolean guards with thread-derived state:

```python
def _is_auto_running(auto_state: AutoModeState) -> bool:
    """Check if auto mode worker thread is actually running."""
    return auto_state.thread is not None and auto_state.thread.is_alive()
```

Locations updated:
- `on_exit()`: Stop only if thread alive
- `on_start_auto()`: Allow start if thread dead
- `on_stop_auto()`: Allow stop only if thread alive

### 3) Documentation Fixes

**README.md:**
- Remove "(stub)" from app.py entry
- Remove duplicate agent_runner.py entry
- Mark Windows startup checkbox as complete

**docs/windows_startup.md:**
- Fix claim about "accept app_name" - uses module constant

## Testing

All tests use mocks - no real registry or OS operations:
- `test_enable_startup_creates_entry`: Verify `CreateKeyEx` called
- `test_start_auto_uses_thread_is_alive`: Verify dead thread allows restart
