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
  - `config.local.json` (gitignored), OR
  - Environment variables (preferred for SaaS / CI later).

If a secret is ever committed by mistake:
1) Assume it is compromised
2) Rotate/revoke it immediately (Twitch dev console / token revocation)
3) Remove it from git history (do not just delete in a new commit)

## Repository Invariants

### Architecture Boundaries

1. **Core Independence**: `src/twitch_marker_agent/core/` MUST NOT import from:
   - `app.py` (tray UI)
   - `cli.py` (CLI entrypoint)
   - `integrations/*` (external integrations)
   - Any web framework (Flask, FastAPI, etc.)
   - Any tray library (pystray, etc.)

2. **Import Direction** (one-way only):
   ```
   Entry points (app.py, cli.py, integrations/*)
         ↓
   core/agent.py (orchestrator)
         ↓
   core/* modules (config, state_store, twitch_oauth, etc.)
   ```

3. **Dependency Injection**: Core modules receive dependencies via constructor/function parameters:
   - `config: AppConfig`
   - `http_client: requests.Session`
   - `state_store: StateStore`
   - `logger: logging.Logger`

### Stubbing Rules (Scaffold Phase)

During scaffold development, modules are implemented incrementally:

**Implemented:**
- OAuth login flow (`twitch_oauth.py` - `interactive_login`, `auth-login` CLI)
- Token maintenance (`twitch_oauth.py` - `refresh_access_token`, `validate_access_token`, `get_valid_user_access_token`)
- Configuration loading (`config.py`)
- State storage (`state_store.py`)
- Retry utility (`retry.py`)
- EventSub WebSocket (`eventsub_ws.py` - `connect`, `run_until_stopped`, message dispatch)
- EventSub Subscriptions (`eventsub_subscriptions.py` - `ensure_stream_offline_subscription`, create/list/delete)
- Helix Markers API (`markers_api.py` - `get_stream_markers`, `get_latest_video_id`)
- Stream Offline Handler (`offline_handler.py` - `handle_stream_offline`, `should_handle_notification`)
- CSV Export (`export_csv.py` - `export_markers_csv`)
- EDL Export (`export_edl.py` - `export_markers_edl`, `timecode_to_seconds`, config-driven offset)
- Tray App UI (`app.py` - `run_tray_app`, manual fetch, format toggles, folder picker, auto mode start/stop)
- Tray Controller (`tray_controller.py` - `resolve_output_dir`, `set_output_dir`, `run_manual_fetch`, `start_auto_mode`, `stop_auto_mode`)
- Agent Runner (`agent_runner.py` - async EventSub orchestrator with connect/subscribe/dispatch)

**Still Stubbed:**
- Legacy orchestrator (`core/agent.py`): Superseded by `agent_runner.py`

**Architecture Invariant:** `core/*` must not import pystray or any UI libraries. Tray UI code lives in `app.py` only.

### Code Standards

1. **Type Hints**: All functions must have complete type annotations
2. **Docstrings**: All public classes/functions need docstrings
3. **Paths**: Use `pathlib.Path` for all file system paths
4. **Logging**: Use `logging` stdlib, inject logger instances
5. **Testing**: Use `unittest` stdlib only (no pytest)

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
python -c "from twitch_marker_agent.core import agent"
```

## Architecture Map

```
┌─────────────────────────────────────────────────┐
│              ENTRY POINTS                       │
│  cli.py  |  app.py  |  integrations/*           │
└─────────────────┬───────────────────────────────┘
                  ▼
┌─────────────────────────────────────────────────┐
│              core/agent.py                      │
│  Orchestrates: OAuth → EventSub → Export        │
└─────────────────┬───────────────────────────────┘
                  ▼
┌─────────────────────────────────────────────────┐
│              CORE MODULES                       │
│  config | state_store | retry | logging_setup   │
│  twitch_oauth | eventsub_ws | markers_api       │
│  export_csv | export_edl                        │
└─────────────────────────────────────────────────┘
```

## File Purposes

| File | Purpose |
|------|---------|
| `config.py` | Load/validate config.json, expose `AppConfig` dataclass |
| `state_store.py` | SQLite wrapper for state + token storage |
| `retry.py` | Sync exponential backoff (async TODO) |
| `twitch_oauth.py` | Browser OAuth + token refresh/validate |
| `eventsub_ws.py` | EventSub WebSocket client (connect, message dispatch) |
| `eventsub_subscriptions.py` | Helix EventSub subscription management (ensure, create, list, delete) |
| `markers_api.py` | Helix Get Stream Markers + Get Videos (latest VOD) |
| `offline_handler.py` | Stream offline notification handling with retry/dedupe |
| `export_csv.py` | Twitch-style CSV export |
| `export_edl.py` | EDL export with timecode offset (stub) |
| `agent.py` | Main orchestrator, coordinates all modules (stub) |

## Runtime Artifacts (Local Only)

These files are runtime-only and must never be committed:
- SQLite state DB (contains processing state and may contain refresh tokens)
- `logs/` output
- local caches / temp files

Recommended locations:
- `data/state.db`
- `logs/app.log`

These must be in `.gitignore`.
