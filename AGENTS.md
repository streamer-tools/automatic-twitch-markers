# AGENTS.md - AI Coding Assistant Rules

This file contains rules and invariants for AI coding assistants working on this repository.

## How to Use This File With Any AI Assistant

When prompting any AI (Antigravity / Gemini / Claude / ChatGPT), start your prompt with:

> Follow all invariants and workflow rules in AGENTS.md. If there is a conflict, stop and ask before proceeding.

This file is the source of truth for architecture boundaries, security rules, and workflow.

## Security & Secrets (Non-Negotiable)

Never commit secrets or sensitive runtime artifacts to git.

**Do NOT commit:**
- Twitch `client_secret`
- OAuth refresh tokens / access tokens
- Any SQLite DB files that may contain tokens or user state
- `.env` files (if used later)
- Any logs that might include tokens or auth headers

**How we handle secrets:**
- Commit `config.json` with safe placeholders only (no real secrets).
- Put real secrets in one of:
  - `config.local.json` (gitignored - preferred for local development), OR
  - Environment variables (preferred for SaaS / CI later).

**NEVER log secrets in code:**
- Do NOT log tokens (access_token, refresh_token)
- Do NOT log client_secret
- Do NOT log Authorization headers
- Do NOT log OAuth callback parameters (code, state)
- Do NOT log raw token API payloads

If a secret is ever committed by mistake:
1) Assume it is compromised
2) Rotate/revoke it immediately (Twitch dev console / token revocation)
3) Remove it from git history (do not just delete in a new commit)

## Repository Invariants

### Architecture Boundaries

1. **Core Independence**: `src/twitch_marker_agent/core/` MUST NOT import from:
   - `app.py` (tray UI)
   - `cli.py` (CLI entrypoint)
   - Any web framework (Flask, FastAPI, etc.)
   - Any tray library (pystray, etc.)

2. **Import Direction** (one-way only):
   ```
   Entry points (app.py, cli.py)
         ->
   core/agent_runner.py (async orchestrator for tray Auto Mode)
         ->
   core/* modules (config, state_store, twitch_oauth, etc.)
   ```

3. **Dependency Injection**: Core modules receive dependencies via constructor/function parameters:
   - `config: AppConfig`
   - `http_client: requests.Session`
   - `state_store: StateStore`
   - `logger: logging.Logger`

### Implemented Components

- OAuth login flow (`twitch_oauth.py` - `interactive_login`, `auth-login` CLI)
- Device Code Flow auth (`core/device_auth.py`, `ui/device_auth_dialog.py`)
- Auth identity bootstrap (`core/auth_identity.py` - fetch/persist/resolve broadcaster identity)
- Token maintenance (`twitch_oauth.py` - `refresh_access_token`, `validate_access_token`, `get_valid_user_access_token`)
- Configuration loading/bootstrap (`config.py`)
- Runtime path resolution (`runtime_paths.py`)
- State storage (`state_store.py`)
- Retry utility (`retry.py`)
- EventSub WebSocket (`eventsub_ws.py`)
- EventSub subscriptions (`eventsub_subscriptions.py`)
- Helix markers/videos APIs (`markers_api.py`, `videos_api.py`)
- Offline handler (`offline_handler.py`)
- CSV/EDL export (`export_csv.py`, `export_edl.py`)
- Tray UI/controller (`app.py`, `tray_controller.py`)
- Async auto mode orchestrator (`agent_runner.py`)
- Date/device dialogs (`ui/date_range_dialog.py`, `ui/device_auth_dialog.py`)

**Architecture Invariant:** `core/*` must not import pystray or any UI libraries. Tray UI code lives in `app.py` only.

### Code Standards

1. **Type Hints**: All functions must have complete type annotations
2. **Docstrings**: All public classes/functions need docstrings
3. **Paths**: Use `pathlib.Path` for all file system paths
   - Runtime entrypoints must resolve paths from EXE directory when frozen (`sys.executable`), or `Path.cwd()` in dev mode.
4. **Logging**: Use `logging` stdlib, inject logger instances
5. **Testing**: Use `unittest` stdlib only (no pytest)

### Approved Dependencies

Minimize dependencies. Only add new dependencies when explicitly approved.

**Currently Approved:**
- `requests` - HTTP client
- `websockets` - EventSub WebSocket
- `pystray` - System tray integration
- `Pillow` - Tray icon image support
- `ttkbootstrap` - ttk themes and DateEntry widget for multi-fetch dialog

## Commands

### Setup
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

### Run Tests
```powershell
python -m unittest discover -s tests -v
```

### Import Check
```powershell
python -c "from twitch_marker_agent.core.config import load_config"
```

## Architecture Map

```text
+------------------------------+
|         ENTRY POINTS         |
|     cli.py  |  app.py        |
+------------------------------+
               |
               v
+------------------------------+
|     core/agent_runner.py     |
| Async orchestrator for tray  |
| OAuth -> EventSub -> Export  |
+------------------------------+
               |
               v
+------------------------------+
|         CORE MODULES         |
| config | state_store | retry |
| twitch_oauth | eventsub_ws   |
| markers_api | export_*       |
+------------------------------+
```

## File Purposes

| File | Purpose |
|------|---------|
| `config.py` | Load/validate config and bootstrap template helpers |
| `runtime_paths.py` | Resolve runtime base/config/log/state paths |
| `auth_identity.py` | Fetch/persist authenticated broadcaster identity |
| `state_store.py` | SQLite wrapper for state + token storage |
| `retry.py` | Sync exponential backoff utility |
| `twitch_oauth.py` | OAuth login/refresh/validate/token lifecycle |
| `eventsub_ws.py` | EventSub WebSocket client |
| `eventsub_subscriptions.py` | Helix EventSub subscription management |
| `markers_api.py` | Helix stream marker + latest video APIs |
| `offline_handler.py` | Stream offline notification handling |
| `export_csv.py` | Twitch-style CSV export |
| `export_edl.py` | Resolve-compatible EDL export |
| `agent_runner.py` | Async EventSub orchestrator for Auto Mode |

### Platform-Specific Modules

| File | Purpose |
|------|---------|
| `platform/windows_startup.py` | Windows startup registry integration (HKCU Run key) |

## Runtime Artifacts (Local Only)

These files are runtime-only and must never be committed:
- SQLite state DB (contains processing state and may contain refresh tokens)
- `logs/` output
- local caches / temp files

Recommended locations:
- `data/state.db`
- `logs/app.log`

These must be in `.gitignore`.
