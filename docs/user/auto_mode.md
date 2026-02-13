# Auto Mode

Auto Mode provides automatic marker export when your stream ends.

## Overview

Auto Mode flow:
1. Connect to Twitch EventSub websocket.
2. Listen for `stream.offline` notifications.
3. Resolve target VOD and fetch markers.
4. Export CSV (and optional EDL).

## Architecture

```text
┌─────────────────────────────────────────────────────────────┐
│                        app.py                               │
│              (pystray UI - main thread)                    │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                   tray_controller.py                       │
│         start/stop wiring + state management               │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                   core/agent_runner.py                     │
│       async orchestration for EventSub + export flow       │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│      core modules (eventsub_ws, subscriptions, handler)    │
└─────────────────────────────────────────────────────────────┘
```

## Concurrency Model
- Main thread: tray UI.
- Worker thread: dedicated asyncio loop for Auto Mode.
- Stop signaling: thread-safe stop request into async loop.

## Error Behavior
- Token/auth errors stop Auto Mode and surface actionable messaging.
- Connection interruptions follow websocket reconnection behavior.
- Duplicate/offline replay prevention uses state + dedupe checks.

## Related Docs
- [Tray Application](tray_app.md)
- [Infrastructure (Developer)](../dev/infrastructure.md)