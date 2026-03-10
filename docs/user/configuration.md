# Configuration

This document is the full configuration reference for `config.json`.

## Runtime Path Behavior

Runtime paths are portable-oriented:
- Frozen EXE: base directory is the folder containing `Automatic Twitch Markers.exe`.
- Dev mode (`python -m ...`): base directory is `Path.cwd()`.

Derived defaults:
- Config: `<base_dir>/config.json`
- Logs: `<base_dir>/logs/`
- State DB: `<base_dir>/data/state.db`

Relative values in `config.json` (for example `output_dir` and `state_db_path`) are anchored to the runtime base directory.

## First-Launch Behavior

If `<base_dir>/config.json` is missing, it is created automatically on startup.

Creation order:
1. Bundled bootstrap template (`bootstrap/config.bootstrap.json`) when packaged.
2. Runtime seed via `TWITCH_MARKER_AGENT_CLIENT_ID` when provided.
3. Fallback placeholder value.

Auth is blocked when `client_id` is still a placeholder. Official releases should ship with seeded `client_id` values.

## Config Keys

| Key | Type | Description |
| --- | --- | --- |
| `client_id` | string | Twitch application client ID (required for auth). |
| `client_secret` | string | Optional for tray/device auth; used for confidential OAuth scenarios. |
| `redirect_uri` | string | OAuth redirect URI (default: `http://localhost:3000/callback`). |
| `broadcaster_id` | string | Broadcaster user ID. May begin blank/placeholder and be auto-populated after successful tray auth. |
| `output_dir` | string | Export output directory. Relative paths are anchored to runtime base dir. |
| `export_formats` | array | Export format preference list (`csv`, `edl`). |
| `resolve_offset_enabled` | boolean | Enable Resolve timecode offset behavior for EDL export. |
| `resolve_offset_timecode` | string | Offset in `HH:MM:SS:FF` format. |
| `timecode_fps` | integer | Frame rate used for EDL timecode conversion. |
| `log_level` | string | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`). |
| `state_db_path` | string | SQLite state DB path (relative paths anchored to runtime base dir). |
| `retry.max_attempts` | integer | Maximum retry attempts. |
| `retry.base_delay_seconds` | float | Initial retry delay. |
| `retry.max_delay_seconds` | float | Maximum retry delay. |

## Required OAuth Scope

The app requires:
- `channel:manage:broadcast`

## Multi-Fetch Retention Note

Multi-fetch supports date ranges up to 60 days back. Actual VOD availability depends on Twitch retention policy for your account type.