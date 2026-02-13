# Infrastructure

This document captures the current runtime architecture and flow used by the tray app.

## Runtime Architecture

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                            ENTRY POINTS                                     │
│      ┌──────────────────────┐   ┌──────────────────────┐                    │
│      │ app.py (Tray UI)     │   │ cli.py (CLI)         │                    │
│      └───────────┬──────────┘   └───────────┬──────────┘                    │
│                  └───────────────┬──────────┘                               │
│                                  ▼                                          │
│                  ┌───────────────────────────────┐                          │
│                  │ tray_controller.py            │                          │
│                  │ Menu actions + orchestration  │                          │
│                  └───────────────┬───────────────┘                          │
│                                  ▼                                          │
│                  ┌───────────────────────────────┐                          │
│                  │ core/agent_runner.py          │                          │
│                  │ Auto Mode async orchestrator  │                          │
│                  └───────────────┬───────────────┘                          │
│                                  ▼                                          │
│   ┌──────────────────────────────────────────────────────────────────────┐  │
│   │ core/* modules                                                       │  │
│   │ config, runtime_paths, state_store, twitch_oauth, device_auth,       │  │
│   │ auth_identity, eventsub_ws, eventsub_subscriptions, offline_handler  │  │
│   │ markers_api, videos_api, export_csv, export_edl, retry               │  │
│   └──────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Data Flow
1. Entry point loads config and runtime paths.
2. Auth establishes/refreshes Twitch user tokens.
3. EventSub stream.offline signal triggers marker fetch workflow.
4. Offline handler resolves target VOD and markers.
5. Exporters write CSV (always) and optional EDL.
6. State store tracks processing state and token metadata.

## Architectural Invariants
- `core/` remains UI/framework agnostic.
- UI behavior stays in `app.py` and `tray_controller.py`.
- No secrets in logs.
- Runtime file paths are anchored to EXE directory (frozen) or `Path.cwd()` (dev).

## Related Docs
- [Project Structure](project_structure.md)
- [User Tray Guide](../user/tray_app.md)
- [User Auto Mode Guide](../user/auto_mode.md)
- [User Configuration](../user/configuration.md)