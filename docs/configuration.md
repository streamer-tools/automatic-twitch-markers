# Configuration Reference

This document is the complete configuration reference for `config.json`.

## First Launch Behavior
- If `config.json` is missing, the app creates it automatically.
- In official releases, `client_id` should already be seeded.
- In local/dev builds, placeholder `client_id` values block authentication until a seeded build is produced.

## Runtime Path Anchoring
Runtime paths are anchored to a runtime base directory:
- Frozen EXE: base directory is the EXE folder (`Path(sys.executable).parent`).
- Dev mode (`python -m ...`): base directory is `Path.cwd()`.

Derived paths:
- Config: `<base_dir>/config.json`
- Logs: `<base_dir>/logs/`
- State DB default: `<base_dir>/data/state.db`

Relative paths inside `config.json` (for example `output_dir` and `state_db_path`) are resolved relative to the runtime base directory.

## Config Keys

| Key | Type | Description |
| --- | --- | --- |
| `client_id` | string | Twitch application client ID (required; placeholder values are treated as invalid for auth). |
| `client_secret` | string | Optional for tray + Device Code Flow; used only for confidential OAuth flows. |
| `redirect_uri` | string | Redirect URI used by browser OAuth flows (default: `http://localhost:3000/callback`). |
| `broadcaster_id` | string | Broadcaster user ID. May start blank/placeholder and be auto-populated after successful tray auth. |
| `output_dir` | string | Export output directory. Relative paths are anchored to runtime base dir. |
| `export_formats` | array[string] | Allowed values: `csv`, `edl`. CSV is always exported by tray workflows. |
| `resolve_offset_enabled` | boolean | Enables EDL timeline offset behavior. |
| `resolve_offset_timecode` | string | Offset timecode in `HH:MM:SS:FF` format. |
| `timecode_fps` | integer | Frame rate used for EDL timecode math. Must be `>= 1`. |
| `log_level` | string | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`). |
| `state_db_path` | string | SQLite state DB path. Relative paths are anchored to runtime base dir. |
| `retry.max_attempts` | integer | Maximum retry attempts for retry-enabled operations. |
| `retry.base_delay_seconds` | float | Initial retry backoff delay in seconds. |
| `retry.max_delay_seconds` | float | Maximum retry backoff delay in seconds. |

## OAuth Scope
Required Twitch scope:
- `channel:manage:broadcast`

## Notes
- Do not commit real secrets/tokens.
- Keep `config.json` in release artifacts placeholder-safe except for seeded `client_id`.