# Project Context Capsule (Handoff)

## 1. Overview
**Automatic Twitch Markers** is a Windows "set-and-forget" tray agent for Twitch streamers. It automatically exports stream markers to CSV/EDL files when a broadcast ends, solving a limitation of tools like Streamer.bot that typically don't support obtaining/using the `channel:manage:broadcast` user-token scope required for marker fetching in this workflow.

## 2. Current Status
- **Version**: 1.0.0 (Portable release polish)
- **Features Complete**:
  - OAuth 2.0 User Token flow (login, refresh, validate)
  - Device Code Flow auth in tray UI (no runtime client_secret requirement)
  - EventSub WebSocket (offline detection)
  - Helix API integration (Get Stream Markers, Get Videos)
  - Exports: Twitch-format CSV and Resolve-compatible EDL with offsets
  - Tray App: Manual fetch, multi-fetch (date range), config persistence, auto mode start/stop
  - Broadcaster identity bootstrap after auth (`/helix/users` -> persisted in `StateStore`)
  - Portable runtime path anchoring (EXE-relative when frozen, CWD in dev)
  - First-launch config bootstrap (`config.json` auto-created if missing)
  - Build/runtime `client_id` seeding support via `TWITCH_MARKER_AGENT_CLIENT_ID`
  - Build-time fallback seeding from `local.config.json` for local dev
  - Build guard blocks placeholder `client_id` outputs unless explicit local dev override is enabled
  - Windows Startup: Registry-based "Run" key integration
  - Windows startup command uses absolute quoted path (no System32 CWD dependency)
  - Packaging: PyInstaller build script for standalone exe
  - CI/CD: GitHub Actions for automated release builds
- **Limitations**:
  - Single user/channel support (config.json)
  - Local state only (SQLite-backed via `StateStore`; see `core/state_store.py`)
  - Windows-only tray features (uses `pystray` + `Pillow`)

## 3. Non-negotiable Invariants
Derived from `AGENTS.md`:
- **Security**: NEVER log secrets (tokens, client_secret). Commit only placeholder-safe `config.json`. Never paste secrets/tokens into logs, issues, PRs, screenshots, or chat.
- **Scope**: No new dependencies. No config schema changes.
- **Architecture**: `core/` is framework-agnostic. `app.py` contains all UI logic.
- **Testing**: `unittest` + `unittest.mock` ONLY. No network calls in tests.
- **Workflow**: Minimal diffs. Stop if conflict.

## 4. How to Run (Local)

**Prerequisites**:
- `config.json` is auto-created on first run in repo root (dev) or next to `TwitchMarkerAgent.exe` (frozen)
- Official release users should not need to set `client_id` manually
- Local builders should set `TWITCH_MARKER_AGENT_CLIENT_ID` (or `local.config.json` `client_id`) before building
- Leave `broadcaster_id` blank if desired; tray auth will auto-populate it after success
- Virtual environment active (`.venv\Scripts\Activate.ps1`)

**Run Tests**:
```powershell
python -m unittest discover -s tests -v
```

**Run Tray App**:
```powershell
python -m twitch_marker_agent.app
```

**Run CLI (Auth)**:
```powershell
python -m twitch_marker_agent.cli auth-login
```

## 5. Architecture Snapshot
- **`src/twitch_marker_agent/core/`**:
  - `runtime_paths.py`: Runtime base path resolver (portable path anchoring).
  - `auth_identity.py`: Authenticated broadcaster identity fetch/persist/resolve.
  - `agent_runner.py`: Async orchestrator for Auto Mode (EventSub + Markers).
  - `eventsub_ws.py`: WebSocket client handling `stream.offline`.
  - `twitch_oauth.py`: Token management.
  - `videos_api.py`: Archived VOD listing via Helix Get Videos.
  - `export_*.py`: Export definition implementations.
- **`src/twitch_marker_agent/app.py`**:
  - Main entrypoint for System Tray UI.
  - Manages `pystray.Icon`, menus, and threading.
- **`src/twitch_marker_agent/ui/`**:
  - `date_range_dialog.py`: Tkinter date range picker for multi-fetch.
- **`src/twitch_marker_agent/platform/windows_startup.py`**:
  - Windows-specific registry integration (HKCU Run key).

**Deep Dive**: [Auto Mode](auto_mode.md) | [Tray App](tray_app.md) | [Windows Startup](windows_startup.md)

## 6. Operational Playbook
- **Gating**:
  - **RUN 1**: Planning, Q&A, Docs.
  - **RUN 2**: Implementation. **Only proceed if user says exactly "Proceed RUN 2".**
- **Commit Messages**: `type(scope): description`.
  - Provide 3 options (Recommended / Explicit / Detailed).
  - Keep tense present imperative (e.g., "Add feature" not "Added feature").
- **PR Templates**: Include sections:
  - **Summary**: High-level change description.
  - **What changed**: Grouped by component/file.
  - **Testing**: How to verify (commands + manual steps).
  - **Scope/Non-Goals**: What was intentionally excluded.
- **Model Selection** (always start prompts with "Model pick (why)" block):
  - **ChatGPT (GPT-5.2 Thinking)**: RUN 1 prompt crafting, spec tightening, post-RUN 2 review, PR/commit writing
  - **GPR-5.3-Codex**: (Antigravity): Default for most RUN 2 implementations, straightforward debugging, tests, small fixes, docs.
  - **Claude Sonnet 4.5** (Antigravity): Backup for most RUN 2 implementations, straightforward debugging, tests, small fixes, docs. Use when Codex is not available, or if Sonnet is better suited for the task. **Sonnet-safe ✅**
  - **Claude Opus 4.5** (Antigravity): Use for complex tasks with unclear root cause, multi-file interactions, async/race conditions, auth/security, flakiness, or when we need maximum quality. **Opus-worthy 🧠**
  - **Gemini 3 Pro (High)**: Docs-only changes, simple mechanical patches, fallback when Claude quota capped 
  - *Note: Opus and Sonnet share quota pool; prefer Sonnet when sufficient; use Opus when it materially improves quality/saves time.*
- **Testing**: 100% Mock-based. No real registry or network access.

## 7. Active Work / Next Steps
1. Validate portable zip behavior on a clean machine (fresh config, first auth, fetch flows).
2. Confirm Windows startup toggle from packaged exe creates expected HKCU Run command.
3. Prepare release notes and tag for v1.0.0.

## 8. Quick Restart Checklist
1. **Pull latest** and ensure clean git state.
2. **Read** `AGENTS.md` and this file (`docs/handoff.md`).
3. **Run tests** (`python -m unittest discover -s tests -v`) to confirm baseline.
4. **Check** `README.md` changelog and open tasks for active scope.
5. **Generate RUN 1** prompt for planning.
6. **Wait** for "Proceed RUN 2".
7. **Implement**, verifying with tests.
8. **Update Docs** (README/AGENTS) as part of the run.

