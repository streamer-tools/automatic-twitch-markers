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
   - `config.json` is auto-created on first launch if missing
   - Official release users should not need to edit `client_id` manually
   - For local builds, set `TWITCH_MARKER_AGENT_CLIENT_ID` (or set `client_id` in `local.config.json`) before building
   - `client_secret` is optional for tray/device auth flow

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
- **Fetch Multiple Stream Markers** - export markers from multiple VODs within a date range (up to 60 days back) using a calendar date picker with preset buttons
- **Additional Output Format** → **EDL** - toggle EDL export (CSV always exported)
- **Output Folder** - open or change export directory
- **Start on Windows Login** - toggle automatic startup (Windows only)
- **Authenticate with Twitch** - device flow auto-detects your broadcaster identity and stores it after success

> **Note:** Fetch and Auto Mode actions are disabled until you authenticate with Twitch. Other settings (output folder, EDL toggle, startup) remain accessible.
> Access tokens are short-lived (~4 hours), but the tray app refreshes them automatically; you should only need to re-authenticate if refresh tokens are revoked/expired.

**Building executable**: See [docs/packaging.md](docs/packaging.md) for instructions on creating a standalone Windows exe.
Local builds require seeded `client_id` (`TWITCH_MARKER_AGENT_CLIENT_ID` or `local.config.json` fallback) and intentionally fail if placeholder remains, unless an explicit dev-only override is used.

## Configuration

Runtime paths are portable-only in 1.0:
- Frozen exe: base directory is the folder containing `TwitchMarkerAgent.exe`
- Dev mode (`python -m ...`): base directory is `Path.cwd()`
- `config.json` is loaded from `<base_dir>/config.json`
- Logs are written under `<base_dir>/logs/`
- Default state DB path is `<base_dir>/data/state.db`

If `<base_dir>/config.json` is missing, it is created automatically on startup:
1. Start with bundled `bootstrap/config.bootstrap.json` (when packaged)
2. Apply runtime `TWITCH_MARKER_AGENT_CLIENT_ID` override if provided
3. Fall back to a non-empty placeholder client ID

Auth is blocked while `client_id` is still a placeholder value.
Official releases should ship with seeded `client_id`; placeholder values indicate a bad/unseeded build.
Local build script enforces this by default and fails when placeholder remains (dev-only override exists for testing).

| Key | Type | Description |
|-----|------|-------------|
| `client_id` | string | Twitch application client ID |
| `client_secret` | string | Twitch application client secret (not required for tray/device auth flow) |
| `redirect_uri` | string | OAuth redirect URI (default: `http://localhost:3000/callback`) |
| `broadcaster_id` | string | Broadcaster user ID; may be blank/placeholder and auto-populated after successful tray device auth |
| `output_dir` | string | Directory for exported files |
| `export_formats` | array | List of formats: `["csv", "edl"]` |
| `resolve_offset_enabled` | boolean | Apply timecode offset for DaVinci Resolve |
| `resolve_offset_timecode` | string | Offset in `HH:MM:SS:FF` format |
| `timecode_fps` | integer | Frame rate for EDL timecode (e.g., `24`, `30`) |
| `log_level` | string | Logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `state_db_path` | string | Path to SQLite state database (relative paths are anchored to runtime base dir) |
| `retry.max_attempts` | integer | Max retry attempts for API calls |
| `retry.base_delay_seconds` | float | Initial backoff delay |
| `retry.max_delay_seconds` | float | Maximum backoff delay |

### Required OAuth Scopes

The agent will request these scopes during OAuth:
- `channel:manage:broadcast` - Required to read stream markers and manage broadcast settings (future-proofed for additional features)

**Note:** Multi-stream fetch allows selecting dates within the past 60 days from today (inclusive). The actual availability of VODs depends on your channel's VOD retention settings (7-14 days for standard accounts, up to 60 days for channels with Turbo subscribers).

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
│   │   ├── auth_identity.py   # Authenticated user identity bootstrap/resolution
│   │   ├── eventsub_ws.py     # EventSub WebSocket client
│   │   ├── eventsub_subscriptions.py # Helix subscription management
│   │   ├── export_csv.py      # CSV export (Twitch-style)
│   │   ├── export_edl.py      # EDL export (DaVinci Resolve)
│   │   ├── logging_setup.py   # Logging configuration
│   │   ├── markers_api.py     # Helix Get Stream Markers
│   │   ├── offline_handler.py # Stream offline notification handler
│   │   ├── retry.py           # Exponential backoff utility
│   │   ├── runtime_paths.py   # Runtime base dir + config/log/state path resolution
│   │   ├── state_store.py     # SQLite state + token storage
│   │   └── twitch_oauth.py    # OAuth login/refresh/validate
│   ├── platform/              # Platform-specific features
│   │   └── windows_startup.py # Windows startup integration (HKCU Run key)
│   └── integrations/          # External tool integrations (future)
└── tests/                     # Unit tests (stdlib unittest)
```

## Core Implementation Steps (Completed)

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

### Newly Added Features
13. [x] Add a "Fetch Multiple Stream Markers" button to the tray app
14. [x] Implement OAuth Device Code Grant Flow (get rid of secret requirement)
15. [x] Refactor "Fetch Multiple Stream Markers" button to use ttkbootstrap for date selection
16. [x] Add quick select options for last 7, 14, 30, 60 days

## Export Formats

See [docs/export_formats.md](docs/export_formats.md) for detailed format specifications.

| Format | Status | Description |
|--------|--------|-------------|
| Twitch CSV | Implemented | Canonical 4-column format (no header row), compatible with CSV->EDL converters |
| Resolve EDL | Implemented | CMX 3600 event + metadata format with DaVinci timeline preamble (`EDL`, `Title`, `FCM`) and configurable offset |

Marker attribution fields are populated from Helix marker grouping data (`user_name`/`user_login`) with inferred user type (`Broadcaster`/`Editor`) instead of static placeholders.

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

The tray includes a folder picker to set the export destination:
- Browse button opens native folder picker dialog
- Selection persisted via StateStore (no need to edit config.json manually)
- Default falls back to `output_dir` from config.json

## Changelog

### v1.0.0 (2026-02-13)
- **Fixed Auto Mode marker attribution regression** by passing broadcaster `user_id` during video-specific marker fetches (prevents broadcaster markers from being mislabeled as `Editor`)
- **Stabilized tray auth session continuity** by making auth-status checks refresh-aware and skipping placeholder `client_secret` in refresh payloads for public/device-flow builds
- **Added tray notifications for Auto Mode** - users will now receive notifications when Auto Mode exports markers, including success and failure cases (skip cases stay silent)

### v0.9.0 (2026-02-13)
- **Portable Runtime + Auth Polish:**
  - Runtime paths are now deterministic and portable-only: `config.json`, logs, and relative state paths resolve from the exe directory (frozen) or `Path.cwd()` (dev)
  - First-launch bootstrap now auto-creates `config.json` when missing (no startup failure on fresh portable folders)
  - EXE packaging now bundles `bootstrap/config.bootstrap.json`; build seeding resolves `client_id` from `TWITCH_MARKER_AGENT_CLIENT_ID` first, then `local.config.json` fallback for local builds
  - Local/CI builds now fail fast when bootstrap `client_id` is placeholder (unless local dev override is explicitly enabled)
  - Tray/CLI auth gating copy now explicitly identifies unseeded builds and directs users to official seeded releases (or rebuild with `TWITCH_MARKER_AGENT_CLIENT_ID`)
  - Windows startup command now stores an absolute, quoted executable/interpreter path to avoid System32 working-directory path issues
  - Tray device auth now auto-detects authenticated broadcaster identity via Helix `/users`, persists identity in `StateStore`, and writes `broadcaster_id` into `config.json` when blank/placeholder
  - Tray auth dialog now auto-closes reliably on successful authentication and shows `Authenticated as <display_name>` notification
  - Manual fetch, multi-fetch, and auto-mode subscription flow resolve broadcaster ID from persisted state first, then config fallback, with clear re-auth guidance when missing
  - Tray device code flow does not require `client_secret` at runtime

### v0.8.1 (2026-02-12)
- **EDL Format Alignment Patch:**
  - Restored DaVinci-style preamble lines: `EDL`, `Title: Timeline 1`, `FCM: NON-DROP-FRAME`
  - Event numbering now starts at `000` to match timeline marker EDL output style
  - Event line spacing updated to match expected `V    C` layout

### v0.8.0 (2026-02-12)
- **Export Correctness Patch:**
  - Marker export attribution now uses Helix marker response grouping data (`user_name` fallback `user_login`) for `username`
  - Marker `user_type` is now inferred per export row (`Broadcaster` when marker user matches fetched broadcaster ID, otherwise `Editor`)
  - CSV export now writes marker rows only (removed header row) while preserving UTF-8 BOM and quoted-field behavior
  - EDL export now starts at the first event line (removed `TITLE`/`FCM` preamble)
- **Tests:** Added/updated unittest coverage for parser attribution, CSV no-header behavior, comma-safe CSV parsing, and EDL no-preamble output

### v0.7.0 (2026-02-11)
- **Date Picker Migration:**
  - Replaced tkcalendar with ttkbootstrap DateEntry to fix month navigation bugs
  - Default date range dialog theme set to "superhero" for multi-fetch (via `DateRangeDialogStyle` in `app.py`)
  - Implemented custom validation helpers (no mindate/maxdate in ttkbootstrap)
  - Pure validation functions: `compute_allowed_window()`, `validate_date_in_range()`, `validate_date_range_order()`
  - Switched date range dialog to pseudo-modal behavior to avoid DateEntry popup grab/focus conflicts
  - Added `DateRangeDialogStyle` hooks for dialog-level theme and widget bootstyle customization
  - Fixed close/reopen bgerror ("application has been destroyed") and styling break by reusing a shared hidden Tk root and canceling pending idle callbacks
  - Removed tkcalendar and babel build dependencies
- **Dependency:** Added `ttkbootstrap>=1.5.0,<2.0` for modern ttk themes and DateEntry widget
- **Tests:** All tests passing (stdlib unittest)

### v0.6.0 (2026-02-10)
- **Device Code Flow Authentication:**
  - New auth dialog: auto-copies code to clipboard on open
  - Auto-opens browser to Twitch authorization page
  - Uses `verification_uri_complete` when available (pre-fills user code)
  - Success notification when authentication completes
- **Menu Gating:**
  - Fetch and Auto Mode actions disabled when unauthenticated
  - Clear visual feedback for auth-required actions
  - Output folder, EDL toggle, Windows login remain always accessible
- **Tests:** All tests passing (stdlib unittest)

### v0.5.0 (2026-02-09)
- **Multi-Stream Fetch Feature:**
  - New tray menu item: "Fetch Multiple Stream Markers"
  - Modern calendar date picker (ttkbootstrap.DateEntry) with styled appearance
  - Custom date range validation (last 60 days from today)
  - Preset buttons: Last 7 / 14 / 30 / 60 days for quick selection
  - New core module: `videos_api.py` for listing archived VODs via Helix Get Videos API
  - `list_videos_in_date_range()` - cursor pagination with early-stop optimization for videos older than range
  - `ArchivedVideo` dataclass with video_id, title, created_at, url
  - New controller functions: `validate_date_range()` and `run_multi_fetch()`
  - `MultiFetchResult` dataclass tracks total, successful, skipped, and failed VOD counts
  - Multi-fetch exports one CSV/EDL set per VOD with unique filenames (appends video_id)
  - Continues processing on individual failures, returns comprehensive summary
  - UI package: `ui/date_range_dialog.py` with DateRangeDialog class
  - Date validation: start ≤ end, end ≤ today, start ≥ today-60 days
  - VOD retention note in README (7-14 days standard, up to 60 days with Turbo)
  - Patch fix: aligned export function signatures with `export_csv.py`/`export_edl.py`
  - Patch fix: uses same Resolve offset computation as manual fetch
- **Tests:** All tests passing (stdlib unittest)

### v0.4.1 (2026-02-08)
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
- **Tests:** All tests passing

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
