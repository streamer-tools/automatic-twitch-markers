# Auto Mode Stabilization Patch

## Overview

This document describes the stabilization patch for the Auto Mode feature, focusing on reliable cross-thread stop signaling, restart behavior, and accurate UI status display.

## Issues Addressed

### 1. Stop Signaling Correctness

**Problem:**
`request_stop()` called `asyncio.get_running_loop()` from the tray thread, which raises `RuntimeError` because there's no event loop in that thread. The stop event was never set.

**Solution:**
- Store `self._loop = asyncio.get_running_loop()` at start of `run_async()`
- Use stored loop in `request_stop()`: `self._loop.call_soon_threadsafe(self._stop_event.set)`
- Clear `self._loop = None` on exit

### 2. Restart Behavior (Stop → Start)

**Problem:**
After `run_async()` completes, the closed client, already-set event, and old queue were reused on restart.

**Solution:**
Add `_reset_state()` method called at the START of `run_async()`:
```python
def _reset_state(self) -> None:
    """Reset internal state for fresh run."""
    self._stop_event = None
    self._notification_queue = None
    self._eventsub_client = None  # Only if not injected
    self._loop = None
    self._seen_message_ids.clear()
```

### 3. Reconnect/Session_id Resubscription

**Assessment:**
Per Twitch docs, reconnect preserves subscriptions. No re-ensure needed on reconnect.

**Decision:** No changes required.

### 4. Tray Status Correctness

**Problem:**
`AutoModeState.is_running` was a boolean set explicitly, which could become stale if the worker thread crashed.

**Solution:**
Derive running state from `thread.is_alive()` when building menus:
```python
def is_auto_stopped(_: pystray.MenuItem) -> bool:
    return auto_state.thread is None or not auto_state.thread.is_alive()

def is_auto_running(_: pystray.MenuItem) -> bool:
    return auto_state.thread is not None and auto_state.thread.is_alive()
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        app.py                               │
│              (pystray UI - main thread)                     │
│  • Start Auto Mode / Stop Auto Mode menu items              │
│  • Status derived from thread.is_alive()                    │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                   tray_controller.py                        │
│        (Pure functions + AutoModeState dataclass)           │
│  • start_auto_mode() / stop_auto_mode()                     │
│  • Thread management                                        │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                   Worker Thread                             │
│              (runs asyncio event loop)                      │
│              asyncio.run(agent.run_async())                 │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                 core/agent_runner.py                        │
│        (Async EventSub orchestrator - DI-friendly)          │
│  • Stores self._loop for thread-safe stop                   │
│  • _reset_state() for restart reliability                   │
└─────────────────────────────────────────────────────────────┘
```

## Thread-Safe Stop Signaling

```
Tray Thread                         Worker Thread (asyncio loop)
     │                                        │
     │  agent.request_stop()                  │
     │  ─────────────────────►                │
     │                                        │
     │  self._loop.call_soon_threadsafe(      │
     │      self._stop_event.set              │
     │  )                                     │
     │  ──────────────────────────────────►   │
     │                                        │
     │                              _stop_event.is_set() = True
     │                                        │
     │  eventsub_client.stop()                │
     │  (sets _stop_event sync)               │
     │                                        │
     │                              run_async() exits
     │                                        │
     │  thread.join(timeout)         ◄────────┘
     │
```

## Test Coverage

| Test | Coverage |
|------|----------|
| `test_request_stop_uses_stored_loop` | Thread-safe stop signaling |
| `test_restart_resets_state` | Fresh client/event on restart |
| `test_status_checks_thread_is_alive` | Derive running from thread |
| `test_dead_thread_shows_stopped` | Stale flag detection |

## Files Modified

| File | Change |
|------|--------|
| `core/agent_runner.py` | Store loop, add `_reset_state()` |
| `app.py` | Derive running from `thread.is_alive()` |
| `tests/test_agent_runner.py` | 2 new tests |
| `tests/test_tray_controller.py` | 2 new tests |
| `AGENTS.md` | Fix architecture references |
| `README.md` | Fix file tree reference |
