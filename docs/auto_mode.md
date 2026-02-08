# Auto Mode Design

This document describes the Auto Mode feature for automatic marker export.

## Overview

Auto Mode provides automatic marker export when streams end:
- Connects to Twitch EventSub WebSocket
- Listens for `stream.offline` events
- Automatically exports markers to configured formats

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        app.py                               │
│              (pystray UI - main thread)                     │
│  • Start Auto Mode / Stop Auto Mode menu items              │
│  • Status indicator                                         │
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
│  • AgentRunner.run_async()                                  │
│  • Connects → ensures subscription → consumes notifications │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                      core/*                                 │
│    (eventsub_ws, eventsub_subscriptions, offline_handler)   │
└─────────────────────────────────────────────────────────────┘
```

## Concurrency Model

1. **Main thread:** pystray UI loop (cannot block)
2. **Worker thread:** Dedicated thread running `asyncio.run(agent.run_async())`
3. **Stop signal:** Thread-safe via `request_stop()` → `asyncio.Event`

## Menu Structure

```
Twitch Marker Agent
├─ Start Auto Mode        (visible when stopped)
├─ Stop Auto Mode         (visible when running)
├─ Auto: Running          (status indicator)
├─ ───────────────────────────
├─ Fetch Latest Stream Markers
├─ Output Format
│   ├─ ☑ CSV
│   └─ ☐ EDL
├─ Output Folder
│   ├─ Open Folder
│   └─ Change Folder...
├─ ───────────────────────────
└─ Exit
```

## Subscription Management

- `ensure_stream_offline_subscription()` called once on `session_welcome`
- Reconnects via `session_reconnect` preserve subscriptions (no action needed)
- Token refresh handled by `TwitchOAuth.get_valid_user_access_token(min_ttl_seconds=60)`

## Error Handling

| Error | Behavior |
|-------|----------|
| `TokenRefreshError` | Stop agent, set `last_error`, notify user |
| `SubscriptionAuthError` | Retry with fresh token, then stop if still failing |
| `EventSubConnectionLost` | Automatically reconnect (handled by WS client) |

## State Management

- **Running state:** In-memory only (no persistence)
- **Dedupe:** Existing `handle_stream_offline` + StateStore

## Configuration

No config.json changes. Uses existing values:
- `broadcaster_id` - which channel to monitor
- `export_formats` - CSV/EDL selection
- `output_dir` - export location
- `resolve_offset_*` - EDL offset settings
