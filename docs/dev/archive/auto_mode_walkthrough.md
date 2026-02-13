# Auto Mode Implementation Walkthrough

## Summary

Implemented Auto Mode for automatic marker export when streams end. The tray app now has Start/Stop controls that run an EventSub agent in a background thread.

## Changes Made

### Core Agent Runner (`core/agent_runner.py` - NEW)

Async EventSub orchestrator that:
- Connects to Twitch EventSub WebSocket
- Ensures `stream.offline` subscription on session_welcome
- Consumes notifications and dispatches to offline handler
- Provides thread-safe `request_stop()` for graceful shutdown

Key classes/functions:
- `AgentRunner` - DI-friendly orchestrator
- `AgentStatus` - status dataclass
- `run_async()` - main async entrypoint
- `request_stop()` - thread-safe stop

---

### Tray Controller (`tray_controller.py` - MODIFIED)

Added auto mode management functions:
- `AutoModeState` dataclass
- `start_auto_mode()` - spawns worker thread
- `stop_auto_mode()` - joins with timeout

---

### App.py (`app.py` - MODIFIED)

Menu additions:
- Start Auto Mode (visible when stopped)
- Stop Auto Mode (visible when running)
- Status indicator (Auto: Running/Stopped/Error)

---

## Architecture

```
+-------------------------------------------------------------+
|                        app.py                               |
|              (pystray UI - main thread)                     |
|  - Start Auto Mode / Stop Auto Mode menu items              |
|  - Status indicator                                         |
+-------------------------------------------------------------+
                           |
                           v
+-------------------------------------------------------------+
|                   tray_controller.py                        |
|        (Pure functions + AutoModeState dataclass)           |
|  - start_auto_mode() / stop_auto_mode()                     |
|  - Thread management                                        |
+-------------------------------------------------------------+
                           |
                           v
+-------------------------------------------------------------+
|                   Worker Thread                             |
|              (runs asyncio event loop)                      |
|              asyncio.run(agent.run_async())                 |
+-------------------------------------------------------------+
                           |
                           v
+-------------------------------------------------------------+
|                 core/agent_runner.py                        |
|        (Async EventSub orchestrator - DI-friendly)          |
|  - AgentRunner.run_async()                                  |
|  - Connects -> ensures subscription -> consumes notifications |
+-------------------------------------------------------------+
```

## Test Results

```
Ran 272 tests in 4.372s
OK
```

### Tests Added

| Test File | Tests Added | Coverage |
|-----------|-------------|----------|
| `test_agent_runner.py` | 8 | Subscription ensure, notification dispatch, stop, errors |
| `test_tray_controller.py` | 7 | Start/stop auto mode, thread management |

---

## Files Changed/Added

| File | Change |
|------|--------|
| `src/twitch_marker_agent/core/agent_runner.py` | **NEW** |
| `src/twitch_marker_agent/tray_controller.py` | **MODIFIED** |
| `src/twitch_marker_agent/app.py` | **MODIFIED** |
| `tests/test_agent_runner.py` | **NEW** |
| `tests/test_tray_controller.py` | **MODIFIED** |
| `docs/auto_mode.md` | **NEW** |
| `README.md` | **MODIFIED** |
| `AGENTS.md` | **MODIFIED** |

## Manual Verification

```powershell
# Verify imports work
python -c "from twitch_marker_agent.core.agent_runner import AgentRunner; print('OK')"

# Verify tray module loads
python -c "from twitch_marker_agent.app import run_tray_app; print('OK')"

# Run tests
python -m unittest discover -s tests -v
```
