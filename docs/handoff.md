# Project Context Capsule (Handoff)

## 1. Overview
**Automatic Twitch Markers** is a Windows "set-and-forget" tray agent for Twitch streamers. It automatically exports stream markers to CSV/EDL files when a broadcast ends, solving a limitation of tools like Streamer.bot that typically don't support obtaining/using the `channel:manage:broadcast` user-token scope required for marker fetching in this workflow.

## 2. Current Status
- **Version**: 0.4.0 (Pre-Alpha)
- **Features Complete**:
  - OAuth 2.0 User Token flow (login, refresh, validate)
  - EventSub WebSocket (offline detection)
  - Helix API integration (Get Stream Markers)
  - Exports: Twitch-format CSV and Resolve-compatible EDL with offsets
  - Tray App: Manual fetch, config persistence, auto mode start/stop
  - Windows Startup: Registry-based "Run" key integration
  - Packaging: PyInstaller build script for standalone exe
  - CI/CD: GitHub Actions for automated release builds
- **Limitations**:
  - Single user/channel support (config.json)
  - Local state only (SQLite-backed via `StateStore`; see `core/state_store.py`)
  - Windows-only tray features (uses `pystray` + `Pillow`)

## 3. Non-negotiable Invariants
Derived from `AGENTS.md`:
- **Security**: NEVER log secrets (tokens, client_secret). **Never commit `local.config.json` containing secrets.** Commit only `config.json` with placeholders. Never paste secrets/tokens into logs, issues, PRs, screenshots, or chat.
- **Scope**: No new dependencies. No config schema changes.
- **Architecture**: `core/` is framework-agnostic. `app.py` contains all UI logic.
- **Testing**: `unittest` + `unittest.mock` ONLY. No network calls in tests.
- **Workflow**: Minimal diffs. Stop if conflict.

## 4. How to Run (Local)

**Prerequisites**:
- Copy `config.json` → `local.config.json`
- Fill in real `CLIENT_ID` / `CLIENT_SECRET` in `local.config.json`
- Confirm `local.config.json` is gitignored before committing
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
  - `agent_runner.py`: Async orchestrator for Auto Mode (EventSub + Markers).
  - `eventsub_ws.py`: WebSocket client handling `stream.offline`.
  - `twitch_oauth.py`: Token management.
  - `export_*.py`: Export definition implementations.
- **`src/twitch_marker_agent/app.py`**:
  - Main entrypoint for System Tray UI.
  - Manages `pystray.Icon`, menus, and threading.
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
  - **Claude Sonnet 4.5** (Antigravity): Default for most RUN 2 implementations, straightforward debugging, tests, small fixes, docs. **Sonnet-safe ✅**
  - **Claude Opus 4.5** (Antigravity): Complex tasks with unclear root cause, multi-file interactions, async/race conditions, auth/security, flakiness, or when Sonnet attempt failed. **Opus-worthy 🧠**
  - **Gemini 3 Pro (High)**: Docs-only changes, simple mechanical patches, fallback when Claude quota capped 
  - **Codex/other**: When applicable based on task/quota
  - *Note: Opus and Sonnet share quota pool; prefer Sonnet when sufficient; use Opus when it materially improves quality/saves time.*
- **Testing**: 100% Mock-based. No real registry or network access.

## 7. Active Work / Next Steps
Towards v1.0 Release:
- [x] Auto Mode (EventSub)
- [x] Tray App UI
- [x] Windows Startup Integration
- [x] Packaging (PyInstaller to .exe)
- [x] CI/CD (GitHub Actions for release builds)

## 8. Quick Restart Checklist
1. **Pull latest** and ensure clean git state.
2. **Read** `AGENTS.md` and this file (`docs/handoff.md`).
3. **Run tests** (`python -m unittest discover -s tests -v`) to confirm baseline.
4. **Check** `README.md` "Next Implementation Steps" for active task.
5. **Generate RUN 1** prompt for planning.
6. **Wait** for "Proceed RUN 2".
7. **Implement**, verifying with tests.
8. **Update Docs** (README/AGENTS) as part of the run.
