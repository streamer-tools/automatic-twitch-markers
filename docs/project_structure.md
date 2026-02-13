# Project Structure and Architecture

This document captures the current repository structure and runtime architecture.

## High-Level Architecture

```text
+--------------------------------+
| Entry Points                   |
| app.py (tray), cli.py          |
+----------------+---------------+
                 |
                 v
+--------------------------------+
| tray_controller.py             |
| UI-triggered orchestration     |
+----------------+---------------+
                 |
                 v
+--------------------------------+
| core/agent_runner.py           |
| Auto Mode async orchestrator   |
+----------------+---------------+
                 |
                 v
+--------------------------------+
| Core Modules                   |
| config.py, runtime_paths.py    |
| state_store.py, twitch_oauth.py|
| device_auth.py, auth_identity.py|
| eventsub_ws.py,                |
| eventsub_subscriptions.py      |
| offline_handler.py             |
| markers_api.py, videos_api.py  |
| export_csv.py, export_edl.py   |
+--------------------------------+
```

## Import Direction (Invariant)

```text
Entry points (app.py, cli.py)
  -> tray_controller.py
  -> core/agent_runner.py
  -> core/* modules
```

Core modules stay framework-agnostic and must not import tray UI code.

## Repository Structure (Current)

```text
automatic-twitch-markers/
+-- README.md
+-- CHANGELOG.md
+-- AGENTS.md
+-- CONTRIBUTING.md
+-- SECURITY.md
+-- LICENSE
+-- pyproject.toml
+-- docs/
|   +-- README.md
|   +-- tray_app.md
|   +-- auto_mode.md
|   +-- export_formats.md
|   +-- windows_startup.md
|   +-- packaging.md
|   +-- configuration.md
|   +-- project_structure.md
|   +-- dev/
|       +-- README.md
|       +-- handoff.md
|       +-- public_repo_polish.md
|       +-- archive/
+-- scripts/
|   +-- build_exe.ps1
+-- src/
|   +-- twitch_marker_agent/
|       +-- __init__.py
|       +-- app.py
|       +-- cli.py
|       +-- tray_controller.py
|       +-- core/
|       |   +-- agent_runner.py
|       |   +-- auth_identity.py
|       |   +-- config.py
|       |   +-- device_auth.py
|       |   +-- eventsub_subscriptions.py
|       |   +-- eventsub_ws.py
|       |   +-- export_csv.py
|       |   +-- export_edl.py
|       |   +-- logging_setup.py
|       |   +-- markers_api.py
|       |   +-- offline_handler.py
|       |   +-- retry.py
|       |   +-- runtime_paths.py
|       |   +-- state_store.py
|       |   +-- twitch_oauth.py
|       |   +-- videos_api.py
|       +-- ui/
|       |   +-- date_range_dialog.py
|       |   +-- device_auth_dialog.py
|       +-- platform/
|           +-- windows_startup.py
+-- tests/
|   +-- ...
+-- .github/
    +-- workflows/
        +-- release.yml
```

## Related Docs
- Runtime behavior: `docs/tray_app.md`
- Auto Mode flow: `docs/auto_mode.md`
- Export details: `docs/export_formats.md`
- Packaging details: `docs/packaging.md`
- Configuration details: `docs/configuration.md`