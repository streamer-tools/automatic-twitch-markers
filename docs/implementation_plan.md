# Twitch Marker Agent - Scaffold Implementation Plan

## Overview

Scaffold a Windows-friendly "set-and-forget" Twitch Marker Agent with a framework-agnostic core that can later power both a tray app and a web/SaaS backend.

---

## A) Architecture Alternatives & Tradeoffs

| Alternative                    | Pros                                                              | Cons                                                                        |
| ------------------------------ | ----------------------------------------------------------------- | --------------------------------------------------------------------------- |
| **.NET WinForms/WPF Tray App** | Native Windows tray, strong typing, single binary                 | Harder to port to SaaS, different language for web backend                  |
| **Node.js + Electron**         | Cross-platform, JS ecosystem, easy web reuse                      | Heavy runtime, overkill for a tray agent                                    |
| **Python + twitchAPI library** | Pre-built OAuth/EventSub, faster initial dev                      | Less control, library coupling, harder to understand internals for learning |
| **Python Pure (chosen)**       | Full control, lightweight, learning-focused, easy SaaS extraction | More boilerplate for OAuth/WS                                               |

**Decision**: Python pure implementation maximizes learning and SaaS portability.

---

## B) Reasoning Check: Failure Points & Mitigations

| #   | Failure Point                            | Mitigation in Structure                                                                         |
| --- | ---------------------------------------- | ----------------------------------------------------------------------------------------------- |
| 1   | **OAuth scopes/token expiry**            | `twitch_oauth.py` handles refresh; token store injected; scopes documented                      |
| 2   | **EventSub reconnects**                  | `eventsub_ws.py` includes `shutdown()` and reconnect logic placeholder; retry utility available |
| 3   | **Rate limits**                          | `retry.py` provides exponential backoff; all API calls go through it                            |
| 4   | **Processing delay (markers not ready)** | Agent waits/retries after stream.offline before fetching markers                                |
| 5   | **Duplicate exports**                    | SQLite state store tracks last processed VOD/stream ID                                          |
| 6   | **Graceful WS shutdown**                 | Explicit `shutdown()` method in `eventsub_ws.py`; agent calls it on exit                        |

---

## C) Tech Stack Verification

| Requirement      | Solution                                                | Status |
| ---------------- | ------------------------------------------------------- | ------ |
| Python 3.12+     | ✓ Type hints, modern syntax                             | ✓      |
| HTTP client      | `requests` (stubbed)                                    | ✓      |
| WebSocket        | `websockets` (stubbed)                                  | ✓      |
| Tray             | `pystray` + `Pillow` (in requirements, not implemented) | ✓      |
| Persistent state | `sqlite3` stdlib                                        | ✓      |
| Logging          | `logging` stdlib                                        | ✓      |
| Testing          | `unittest` stdlib                                       | ✓      |
| Config           | JSON file, validated in code                            | ✓      |

---

## Repository Tree

```
twitch-marker-agent/
├── README.md
├── AGENTS.md
├── pyproject.toml
├── requirements.txt
├── config.json
├── docs/
│   └── implementation_plan.md
├── src/
│   └── twitch_marker_agent/
│       ├── __init__.py
│       ├── app.py
│       ├── cli.py
│       └── core/
│           ├── __init__.py
│           ├── agent.py
│           ├── config.py
│           ├── logging_setup.py
│           ├── state_store.py
│           ├── retry.py
│           ├── twitch_oauth.py
│           ├── eventsub_ws.py
│           ├── markers_api.py
│           ├── export_csv.py
│           └── export_edl.py
│       └── integrations/
│           ├── __init__.py
│           └── streamerbot_trigger.py
├── tests/
│   ├── __init__.py
│   ├── test_config.py
│   ├── test_state_store.py
│   └── test_retry.py
└── assets/
    └── README.txt
```

---

## ASCII Architecture Sketch

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              ENTRY POINTS                                   │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────────────────────────┐   │
│  │   cli.py    │   │   app.py    │   │  integrations/streamerbot_...  │   │
│  │ (CLI stub)  │   │(Tray stub)  │   │        (trigger stub)          │   │
│  └──────┬──────┘   └──────┬──────┘   └─────────────┬───────────────────┘   │
│         │                 │                        │                        │
│         └─────────────────┼────────────────────────┘                        │
│                           ▼                                                 │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         core/agent.py                               │   │
│  │   Orchestrator: owns lifecycle, coordinates all core modules        │   │
│  │   Injected: config, http_client, token_store, state_store, logger   │   │
│  └──────────────────────────────┬──────────────────────────────────────┘   │
│                                 │                                           │
│    ┌───────────┬───────────┬────┴────┬───────────┬───────────┐             │
│    ▼           ▼           ▼         ▼           ▼           ▼             │
│ ┌───────┐ ┌─────────┐ ┌─────────┐ ┌───────┐ ┌─────────┐ ┌─────────┐       │
│ │config │ │twitch   │ │eventsub │ │markers│ │export   │ │export   │       │
│ │.py    │ │_oauth.py│ │_ws.py   │ │_api.py│ │_csv.py  │ │_edl.py  │       │
│ └───────┘ └─────────┘ └────┬────┘ └───────┘ └─────────┘ └─────────┘       │
│                            │                                               │
│              ┌─────────────┴─────────────┐                                 │
│              ▼                           ▼                                 │
│       ┌───────────┐               ┌───────────┐                            │
│       │state_store│               │  retry.py │                            │
│       │.py (SQLite)│              │ (backoff) │                            │
│       └───────────┘               └───────────┘                            │
└─────────────────────────────────────────────────────────────────────────────┘

DATA FLOW:
  1. Entry point loads config, injects dependencies into Agent
  2. Agent initializes OAuth, connects EventSub WS
  3. EventSub WS receives session_welcome → creates stream.offline subscription
  4. On stream.offline → Agent waits/retries → calls markers_api
  5. markers_api returns markers → export_csv / export_edl writes files
  6. state_store logs processed VOD ID to prevent duplicates
```

---

## Import-Direction Rules (Avoid Circular Imports)

```
config.py        →  (imports nothing from project)
logging_setup.py →  (imports nothing from project)
retry.py         →  (imports nothing from project)
state_store.py   →  config (types only)
twitch_oauth.py  →  config, retry
eventsub_ws.py   →  config, retry
markers_api.py   →  config, retry
export_csv.py    →  config
export_edl.py    →  config
agent.py         →  config, state_store, twitch_oauth, eventsub_ws, markers_api, export_csv, export_edl, retry

RULE: core/* MUST NOT import from app.py, cli.py, or integrations/*
```

---

## Core Interfaces

| Module             | Key Interfaces                                                                   |
| ------------------ | -------------------------------------------------------------------------------- |
| `config.py`        | `AppConfig` (dataclass), `load_config(path) → AppConfig`                         |
| `logging_setup.py` | `setup_logging(config) → Logger`                                                 |
| `state_store.py`   | `StateStore` class: `__init__`, `mark_processed`, `is_processed`, `close`        |
| `retry.py`         | `retry_with_backoff(fn, max_attempts, base_delay, max_delay)`                    |
| `twitch_oauth.py`  | `TwitchOAuth` class: `login_browser`, `refresh_token`, `get_access_token`        |
| `eventsub_ws.py`   | `EventSubClient` class: `connect`, `subscribe_stream_offline`, `run`, `shutdown` |
| `markers_api.py`   | `get_stream_markers(http_client, config, access_token, video_id) → list[Marker]` |
| `export_csv.py`    | `export_markers_csv(markers, output_path, config)`                               |
| `export_edl.py`    | `export_markers_edl(markers, output_path, config)`                               |
| `agent.py`         | `MarkerAgent` class: `__init__`, `start`, `stop`, `on_stream_offline`            |

---

## User Decisions

| Question              | Decision                                                                            |
| --------------------- | ----------------------------------------------------------------------------------- |
| **Token storage**     | SQLite state DB with `TokenStore`-style abstraction (swappable later)               |
| **Retry scope**       | Sync-only `retry_with_backoff` for v1; TODO notes for async variant                 |
| **EDL offset format** | Timecode-only `"HH:MM:SS:FF"` for v1; TODO for seconds support + `timecode_fps`     |

---

## PHASE 2 Requirements

- All Twitch/OAuth/WS/HTTP logic must be **stub-only** with `raise NotImplementedError`
- `timecode_fps` added to config.json for future EDL frame-rate support
- `pyproject.toml` with `requires-python >= 3.12`, dependencies, src layout, CLI entry point
