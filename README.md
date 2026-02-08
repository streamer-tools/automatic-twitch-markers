# Automatic Twitch Markers

A Windows-friendly "set-and-forget" agent that automatically exports Twitch stream markers after a broadcast ends.

> **Context for AI Agents**: Please read [docs/handoff.md](docs/handoff.md) for a <2 minute project sync.

## Overview

This tool monitors your Twitch channel via EventSub WebSocket, detects when your stream goes offline, fetches the stream markers from the VOD, and exports them to CSV (Twitch-style) and/or EDL format for video editors like DaVinci Resolve.

### Why This Tool?

**Streamer.bot Limitation**: Streamer.bot cannot directly fetch stream markers because the Twitch API's "Get Stream Markers" endpoint requires a `channel:manage:broadcast` scope OAuth token from the broadcaster. Streamer.bot's built-in Twitch integration doesn't support this scope for marker retrieval.

This agent solves that by:
1. Running a one-time OAuth flow to get the necessary scopes
2. Maintaining the access token via refresh
3. Listening for stream.offline events
4. Automatically exporting markers when streams end

### Goals

**Local MVP (v1)**:
- Windows tray app that runs silently
- Auto-export markers to CSV/EDL after each stream
- SQLite-backed state to prevent duplicate exports
- Log everything for debugging

**Future SaaS**:
- Web dashboard for configuration
- Multi-user support
- Webhook integrations
- The `core/` module is framework-agnostic to enable this transition

## Setup

### Prerequisites

- Python 3.12 or higher
- A Twitch Developer Application ([Create one here](https://dev.twitch.tv/console/apps))

### Installation

1. **Clone the repository**:
   ```powershell
   git clone https://github.com/yourusername/automatic-twitch-markers.git
   cd automatic-twitch-markers
   ```

2. **Create a virtual environment**:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. **Install in editable mode**:
   ```powershell
   pip install -e .
   ```

4. **Configure** (see Configuration section below):
   - Edit `config.json` with your Twitch app credentials

5. **Run tests** to verify installation:
   ```powershell
   python -m unittest discover -s tests -v
   ```

### Running

**Authenticate with Twitch** (one-time setup):
```powershell
python -m twitch_marker_agent.cli auth-login
# or after install:
auto-twitch-markers auth-login
```

**CLI mode** (agent runtime - future):
```powershell
auto-twitch-markers
# or
python -m twitch_marker_agent.cli
```

**Tray app** (system tray with manual fetch):
```powershell
python -m twitch_marker_agent.app
```

The tray app provides:
- **Auto Mode** - automatically export markers when your stream ends
- **Fetch Latest Stream Markers** - manually fetch and export markers
- **Additional Output Format** → **EDL** - toggle EDL export (CSV always exported)
- **Output Folder** - open or change export directory
- **Start on Windows Login** - toggle automatic startup (Windows only)

**Building executable**: See [docs/packaging.md](docs/packaging.md) for instructions on creating a standalone Windows exe.

## Configuration

For local development, copy `config.json` to `config.local.json` (gitignored) and edit with your Twitch app credentials. The app will load `config.local.json` if present, otherwise falls back to `config.json`.

| Key | Type | Description |
|-----|------|-------------|
| `client_id` | string | Twitch application client ID |
| `client_secret` | string | Twitch application client secret |
| `redirect_uri` | string | OAuth redirect URI (default: `http://localhost:3000/callback`) |
| `broadcaster_id` | string | Your Twitch user ID (numeric) |
| `output_dir` | string | Directory for exported files |
| `export_formats` | array | List of formats: `["csv", "edl"]` |
| `resolve_offset_enabled` | boolean | Apply timecode offset for DaVinci Resolve |
| `resolve_offset_timecode` | string | Offset in `HH:MM:SS:FF` format |
| `timecode_fps` | integer | Frame rate for EDL timecode (e.g., `24`, `30`) |
| `log_level` | string | Logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `state_db_path` | string | Path to SQLite state database |
| `retry.max_attempts` | integer | Max retry attempts for API calls |
| `retry.base_delay_seconds` | float | Initial backoff delay |
| `retry.max_delay_seconds` | float | Maximum backoff delay |

### Required OAuth Scopes

The agent will request these scopes during OAuth:
- `channel:manage:broadcast` - Required to read stream markers and manage broadcast settings (future-proofed for additional features)

## Project Structure

```
automatic-twitch-markers/
├── .github/
│   └── workflows/
│       └── release.yml         # CI/CD: automated builds on v* tags
├── docs/                       # Documentation
│   ├── packaging.md           # Build instructions (PyInstaller)
│   └── ...
├── scripts/
│   └── build_exe.ps1          # Local Windows exe build script
├── src/twitch_marker_agent/
│   ├── app.py                 # Tray app entrypoint (implemented)
│   ├── cli.py                 # CLI entrypoint (auth-login)
│   ├── tray_controller.py     # Tray UI logic (pure functions)
│   ├── core/                  # Framework-agnostic core logic
│   │   ├── agent.py           # Manual fetch orchestrator
│   │   ├── agent_runner.py    # Async EventSub + auto mode orchestrator
│   │   ├── config.py          # Configuration loading/validation
│   │   ├── eventsub_ws.py     # EventSub WebSocket client
│   │   ├── eventsub_subscriptions.py # Helix subscription management
│   │   ├── export_csv.py      # CSV export (Twitch-style)
│   │   ├── export_edl.py      # EDL export (DaVinci Resolve)
│   │   ├── logging_setup.py   # Logging configuration
│   │   ├── markers_api.py     # Helix Get Stream Markers
│   │   ├── offline_handler.py # Stream offline notification handler
│   │   ├── retry.py           # Exponential backoff utility
│   │   ├── state_store.py     # SQLite state + token storage
│   │   └── twitch_oauth.py    # OAuth login/refresh/validate
│   ├── platform/              # Platform-specific features
│   │   └── windows_startup.py # Windows startup integration (HKCU Run key)
│   └── integrations/          # External tool integrations (future)
└── tests/                     # Unit tests (290 tests, all passing)
```

## Next Implementation Steps

1. [x] Implement OAuth browser flow in `twitch_oauth.py`
2. [x] Implement token refresh logic
3. [x] Connect EventSub WebSocket in `eventsub_ws.py`
4. [x] Handle `session_welcome` and create subscription (Helix API)
5. [x] Implement `stream.offline` event handler
6. [x] Implement Helix Get Stream Markers API call
7. [x] Implement CSV export (Twitch format)
8. [x] Implement EDL export with timecode offset
9. [x] Build tray app UI with pystray (v0.4.0)
10. [x] Add Windows startup integration
11. [x] Package as Windows exe (PyInstaller)
12. [x] Setup CI/CD for releases (GitHub Actions)

## Export Formats

See [docs/export_formats.md](docs/export_formats.md) for detailed format specifications.

| Format | Status | Description |
|--------|--------|-------------|
| Twitch CSV | ✅ Implemented | Canonical 4-column format, compatible with CSV→EDL converters |
| Resolve EDL | ✅ Implemented | CMX 3600 format with marker metadata and configurable offset |

## Tray App

The Windows tray app provides automatic and manual marker export:

### Auto Mode

**Start/Stop Auto Mode** monitors your channel via EventSub:
- Connects to Twitch EventSub WebSocket
- Listens for `stream.offline` events
- Automatically exports markers when streams end
- Runs in background without blocking UI

### Manual Fetch Action

**"Fetch Latest Stream Markers"**
- Runs the same fetch + export pipeline as the automatic `stream.offline` trigger
- Writes output to the same folder with the same naming conventions
- Useful for testing or fetching markers before stream ends

### Additional Output Format

**CSV is always exported** (implicit). Optionally enable **EDL** export:
- Navigate to **Additional Output Format** → **EDL**
- Toggle checked to export both CSV and EDL
- Your preference is saved and persists across restarts
- Applies to both manual fetch and auto mode

### Output Folder Picker

The tray will include a folder picker to set the export destination:
- Browse button opens native folder picker dialog
- Selection persisted via StateStore (no need to edit config.json manually)
- Default falls back to `output_dir` from config.json

## Changelog

### v0.4.1 (Unreleased)
- **Auto Mode Clean Shutdown:**
  - Fixed shutdown hang by adding stop-aware wait in `AgentRunner.run_async()`
  - Added stop_task to wait list for immediate response to stop requests
  - Bounded cleanup timeout (2s max) to prevent indefinite hang
  - Fixed RuntimeWarning: scheduled async `EventSubWebSocketClient.stop()` using `asyncio.run_coroutine_threadsafe()`
  - Updated `stop_auto_mode()` to accurately report state when thread doesn't exit within timeout
- **Tray UX Improvements:**
  - Simplified output format UX: CSV export is now implicit (always exported)
  - Replaced "Output Format" submenu with "Additional Output Format" → "EDL" toggle
  - EDL toggle persists via StateStore and affects both manual fetch and auto mode
  - Updated tray menu labels: "Fetch Latest Markers (Now)" → "Fetch Latest Stream Markers"
- **Tests:** All 298 tests passing

### v0.4.0 (2026-02-07) - Release Readiness
- **Windows Startup Integration (`platform/windows_startup.py`):**
  - Registry-based "Run on Windows login" functionality (HKCU Run key)
  - `enable_startup()`, `disable_startup()`, `is_startup_enabled()`
  - `get_startup_command()` - handles frozen exe vs source code execution
  - Tray app "Start on Windows Login" toggle with checked state
- **Packaging (`scripts/build_exe.ps1`):**
  - PyInstaller build script for Windows exe
  - Single-file, windowed executable (`--onefile`, `--noconsole`)
  - Bundles pystray/Pillow with `--collect-submodules`
  - Output: `dist/TwitchMarkerAgent.exe`
- **CI/CD (`.github/workflows/release.yml`):**
  - Automated builds on `v*` tags and `workflow_dispatch`
  - Full test suite run before build
  - Workflow artifacts (always) + GitHub Release attachments (tags)
  - Windows exe packaged as `TwitchMarkerAgent-windows.zip`
- **Documentation:**
  - `docs/packaging.md` - Local build, CI behavior, troubleshooting
  - `docs/handoff.md` - Updated for release readiness milestone
  - README - Packaging link, updated checklist
- Comprehensive tests: 290 tests passing (fixed CreateKeyEx mock)

### v0.3.4 (2026-02-05)
- **Tray App UI (`app.py`):**
  - Windows system tray application with pystray
  - Manual fetch action: "Fetch Latest Stream Markers"
  - Output format toggles (CSV/EDL) for runtime override
  - Output folder picker with persistence via StateStore
  - Threaded fetch keeps UI responsive
- **Tray Controller (`tray_controller.py`):**
  - UI-agnostic pure functions for testability
  - `resolve_output_dir()` - StateStore or config fallback
  - `set_output_dir()` - persist user selection
  - `get_manual_fetch_formats()` - format selection with CSV enforcement
  - `run_manual_fetch()` - token → markers → export pipeline
- **StateStore additions:**
  - `get_state()`/`set_state()` for generic key-value persistence
- Comprehensive tests: 13 new tests (252 total)

### v0.3.3 (2026-02-05)
- **EDL Export (`export_edl.py`):**
  - DaVinci Resolve compatible format with marker metadata lines
  - Event format: `{idx:03}  001      V     C        {startTC} {endTC}`
  - Metadata format: `|C:ResolveColorBlue |M:{desc} by {user} [{type}] |D:1`
  - Marker duration: 1 frame (start :00, end :01)
  - Default offset: +3600 seconds (01:00:00:00) for Resolve timeline
  - Added `timecode_to_seconds()` helper for config parsing
- **Config-driven EDL offset wiring:**
  - `resolve_offset_enabled: false` → offset = 0 (raw timecodes)
  - `resolve_offset_enabled: true` → offset parsed from `resolve_offset_timecode`
  - Invalid timecode falls back to 3600s with warning
- **CSV Export aligned to canonical 4-column format:**
  - Columns: Timestamp, User Type, Username, Marker Title
  - File naming: `{YYYY-MM-DD} {Title} - Twitch Markers.csv` with fallback
  - Added `user_type`, `username` fields to Marker dataclass
- **Offline handler** now exports both CSV and EDL when configured
- Comprehensive tests: 73 new tests (239 total)

### v0.3.2 (2026-02-04)
- **Stream Offline Handler & Markers API:**
  - New module: `offline_handler.py`
  - `handle_stream_offline()` - fetch markers with retry, export to CSV
  - `should_handle_notification()` - filter/dedupe notifications
  - Two-layer dedupe: in-memory message_id + StateStore video_id
  - Retry with exponential backoff for 404/429 (VOD not ready)
  - Exceptions: `MarkersFetchError`, `MarkersAuthError`, `MarkersNotFoundError`, `MarkersRateLimitError`
- **Markers API (`markers_api.py`):**
  - `get_stream_markers()` - GET /helix/streams/markers
  - `get_latest_video_id()` - GET /helix/videos (most recent VOD)
- **OAuth scope:** Uses `channel:manage:broadcast` for Get Stream Markers endpoint and future broadcast management
- Comprehensive tests: 33 new tests (166 total)

### v0.3.1 (2026-02-04)
- **Helix EventSub Subscription Management:**
  - New module: `eventsub_subscriptions.py`
  - `create_eventsub_subscription()` - create subscription with websocket transport
  - `list_eventsub_subscriptions()` - list with mutually-exclusive filter enforcement
  - `delete_eventsub_subscription()` - delete by subscription ID
  - `ensure_stream_offline_subscription()` - idempotent subscription setup (list → delete stale → create)
  - Pure helpers: `build_subscription_request()`, `parse_subscription_response()`
  - Robust condition parsing (dict or JSON string)
- Comprehensive tests: 25 new tests (133 total)

### v0.3.0 (2026-02-04)
- **EventSub WebSocket Client:**
  - `EventSubWebSocketClient` class with full message handling
  - `connect()` - connect and receive session_welcome with session_id
  - `run_until_stopped()` - message loop with keepalive timeout detection
  - `stop()` / `close()` - graceful shutdown
  - Reconnect handling per Twitch docs (new session_id from new welcome)
  - Notification dispatch via `asyncio.Queue`
  - Revocation callback support
  - Pure helpers: `parse_eventsub_message()`, `classify_message_type()`
- Comprehensive tests: 28 new tests (108 total)
- Uses `ping_interval=None` to avoid client-initiated pings

### v0.2.1 (2026-02-02)
- **Token Maintenance:**
  - `refresh_access_token()` - refresh tokens using stored refresh_token
  - `validate_access_token(token)` - validate token with Twitch API
  - `get_valid_user_access_token(min_ttl_seconds=300)` - get valid token, auto-refresh if near expiry
  - Concurrency-safe using `threading.RLock()` (re-entrant lock)
  - Expiry hardening for missing/invalid/naive datetime values
- **Token Maintenance Patch:**
  - Direct calls to `refresh_access_token()` now also protected by lock
  - Added tests for refresh payload fields and timeout tuple verification
  - Updated documentation to reflect Phase C completion
- Unit tests: 80 total (was 62)

### v0.2.0 (2026-02-02)
- Implemented OAuth browser login flow in `twitch_oauth.py`
- Added `auth-login` CLI command for Twitch authentication
- Pure helper functions for unit testing (build_authorize_url, parse_redirect_uri, etc.)
- Dependency injection for HTTP session and browser opener
- Secure token storage in SQLite (access token, refresh token, expiry)
- CSRF protection with state parameter validation
- Comprehensive unit tests for OAuth module (20 new tests)

### v0.1.0 (2026-02-01)
- Initial scaffold created
- Project structure with src/ layout
- Configuration system with validation
- SQLite state store with token storage abstraction
- Retry utility with exponential backoff
- Stub implementations for all core modules
- Unit tests for config, state store, and retry

## License

MIT License - See LICENSE file for details
