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

During scaffold development:
- All Twitch API calls: `raise NotImplementedError("TODO: Implement Twitch API call")`
- All OAuth flows: `raise NotImplementedError("TODO: Implement OAuth flow")`
- All WebSocket connections: `raise NotImplementedError("TODO: Implement WebSocket")`
- No real HTTP requests, no browser automation, no network connections

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
| `twitch_oauth.py` | Browser OAuth + token refresh (stubbed) |
| `eventsub_ws.py` | EventSub WebSocket client (stubbed) |
| `markers_api.py` | Helix Get Stream Markers (stubbed) |
| `export_csv.py` | Twitch-style CSV export |
| `export_edl.py` | EDL export with timecode offset |
| `agent.py` | Main orchestrator, coordinates all modules |

## Runtime Artifacts (Local Only)

These files are runtime-only and must never be committed:
- SQLite state DB (contains processing state and may contain refresh tokens)
- `logs/` output
- local caches / temp files

Recommended locations:
- `data/state.db`
- `logs/app.log`

These must be in `.gitignore`.
