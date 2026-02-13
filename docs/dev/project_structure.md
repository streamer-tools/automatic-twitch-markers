# Project Structure

This document describes the current repository structure and where each major component lives.

## Repository Tree

```text
automatic-twitch-markers/
├── README.md
├── CHANGELOG.md
├── AGENTS.md
├── CONTRIBUTING.md
├── SECURITY.md
├── LICENSE
├── pyproject.toml
├── docs/
│   ├── README.md
│   ├── user/
│   │   ├── README.md
│   │   ├── tray_app.md
│   │   ├── auto_mode.md
│   │   ├── export_formats.md
│   │   ├── configuration.md
│   │   ├── windows_startup.md
│   │   └── packaging.md
│   └── dev/
│       ├── README.md
│       ├── handoff.md
│       ├── infrastructure.md
│       ├── project_structure.md
│       ├── public_repo_polish.md
│       └── archive/
├── scripts/
│   └── build_exe.ps1
├── src/
│   └── twitch_marker_agent/
│       ├── __init__.py
│       ├── app.py
│       ├── cli.py
│       ├── tray_controller.py
│       ├── core/
│       │   ├── agent_runner.py
│       │   ├── auth_identity.py
│       │   ├── config.py
│       │   ├── device_auth.py
│       │   ├── eventsub_subscriptions.py
│       │   ├── eventsub_ws.py
│       │   ├── export_csv.py
│       │   ├── export_edl.py
│       │   ├── logging_setup.py
│       │   ├── markers_api.py
│       │   ├── offline_handler.py
│       │   ├── retry.py
│       │   ├── runtime_paths.py
│       │   ├── state_store.py
│       │   ├── twitch_oauth.py
│       │   └── videos_api.py
│       ├── ui/
│       │   ├── date_range_dialog.py
│       │   └── device_auth_dialog.py
│       └── platform/
│           └── windows_startup.py
└── tests/
    └── ...
```

## Core Module Responsibilities

| Module | Responsibility |
| --- | --- |
| `config.py` | Load/validate `config.json` and expose typed config objects. |
| `runtime_paths.py` | Resolve portable runtime base/config/log/state paths. |
| `state_store.py` | Persist token and workflow state in SQLite. |
| `twitch_oauth.py` | OAuth token validate/refresh and token lifecycle management. |
| `device_auth.py` | Device Code Flow primitives for tray auth UX. |
| `eventsub_ws.py` | EventSub websocket client and message handling. |
| `eventsub_subscriptions.py` | Create/list/delete/ensure EventSub subscriptions. |
| `offline_handler.py` | Stream-offline export workflow with dedupe/retry behavior. |
| `markers_api.py` | Helix marker APIs and marker parsing. |
| `videos_api.py` | Archived VOD listing and date-range filtering. |
| `export_csv.py` | Twitch-style CSV export implementation. |
| `export_edl.py` | Resolve-compatible EDL export implementation. |
| `agent_runner.py` | Async orchestrator for Auto Mode lifecycle. |

## Import Direction Rule

```text
Entry points (app.py, cli.py)
  -> tray_controller.py
  -> core/agent_runner.py
  -> core/* modules
```

Core modules must not import tray/UI modules.

## Related Docs
- [Infrastructure](infrastructure.md)
- [User Configuration](../user/configuration.md)
- [User Tray Guide](../user/tray_app.md)