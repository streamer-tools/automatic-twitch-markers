# Automatic Twitch Markers

A Windows-friendly "set-and-forget" agent that automatically exports Twitch stream markers after a broadcast ends.

## Overview

This tool monitors your Twitch channel via EventSub WebSocket, detects when your stream goes offline, fetches the stream markers from the VOD, and exports them to CSV (Twitch-style) and/or EDL format for video editors like DaVinci Resolve.

### Why This Tool?

**Streamer.bot Limitation**: Streamer.bot cannot directly fetch stream markers because the Twitch API's "Get Stream Markers" endpoint requires a `user:read:broadcast` scope OAuth token from the broadcaster. Streamer.bot's built-in Twitch integration doesn't support this scope for marker retrieval.

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

**CLI mode** (future):
```powershell
automatic-twitch-markers
# or
python -m twitch_marker_agent.cli
```

**Tray app** (future):
```powershell
python -m twitch_marker_agent.app
```

## Configuration

Edit `config.json` in the project root:

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
- `user:read:broadcast` - Required to read stream markers

## Project Structure

```
src/twitch_marker_agent/
├── app.py              # Tray app entrypoint (stub)
├── cli.py              # CLI entrypoint (stub)
└── core/               # Framework-agnostic core logic
    ├── agent.py        # Main orchestrator
    ├── config.py       # Configuration loading/validation
    ├── eventsub_ws.py  # EventSub WebSocket client
    ├── export_csv.py   # CSV export (Twitch-style)
    ├── export_edl.py   # EDL export for editors
    ├── logging_setup.py# Logging configuration
    ├── markers_api.py  # Helix Get Stream Markers
    ├── retry.py        # Exponential backoff utility
    ├── state_store.py  # SQLite state + token storage
    └── twitch_oauth.py # OAuth login/refresh
```

## Next Implementation Steps

1. [x] Implement OAuth browser flow in `twitch_oauth.py`
2. [x] Implement token refresh logic
3. [ ] Connect EventSub WebSocket in `eventsub_ws.py`
4. [ ] Handle `session_welcome` and create subscription
5. [ ] Implement `stream.offline` event handler
6. [ ] Implement Helix Get Stream Markers API call
7. [ ] Implement CSV export (Twitch format)
8. [ ] Implement EDL export with timecode offset
9. [ ] Build tray app UI with pystray
10. [ ] Add Windows startup integration

## Changelog

### v0.2.1 (2026-02-02)
- **Phase C Token Maintenance:**
  - `refresh_access_token()` - refresh tokens using stored refresh_token
  - `validate_access_token(token)` - validate token with Twitch API
  - `get_valid_user_access_token(min_ttl_seconds=300)` - get valid token, auto-refresh if near expiry
  - Concurrency-safe using `threading.RLock()` (re-entrant lock)
  - Expiry hardening for missing/invalid/naive datetime values
- **Phase C Patch:**
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
