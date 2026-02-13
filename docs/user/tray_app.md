# Tray Application

The tray app is the primary way to run Automatic Twitch Markers on Windows.

## Features

### Auto Mode
When enabled, Auto Mode:
- Monitors your stream via Twitch EventSub.
- Detects `stream.offline` events.
- Fetches markers from the relevant VOD.
- Exports markers automatically.

Tray notifications:
- Success and error notifications are shown for real Auto Mode processing outcomes.
- Skipped outcomes (already processed, no markers) stay silent.

### Manual Fetch
**Fetch Latest Stream Markers** runs the same marker export pipeline on demand.

### Multi-Stream Fetch
**Fetch Multiple Stream Markers** lets you choose a date range (up to 60 days) and export markers across matching VODs.

### Additional Output Format
CSV is always exported.

Optional EDL toggle:
- **Additional Output Format -> EDL**
- Checked: CSV + EDL
- Unchecked: CSV only

### Output Folder
- **Open Folder** opens the active export directory.
- **Change Folder** updates the export directory and persists the selection.

### Windows Startup
Use **Start on Windows Login** to launch the tray app after sign-in.

### Authentication
- Tray auth uses Device Code Flow.
- After success, the app resolves and stores broadcaster identity from Helix `/users`.
- The auth dialog closes automatically on success.

### Token Lifecycle
- Access tokens are short-lived (typically around 4 hours).
- The app refreshes tokens silently when refresh tokens are still valid.
- Re-authentication is only needed when refresh tokens are invalid/revoked/expired.

## Default Behavior
- EDL export: off (CSV only)
- Auto Mode: stopped
- Output folder: from state/config resolution

## Related Docs
- [Configuration](configuration.md)
- [Auto Mode](auto_mode.md)
- [Export Formats](export_formats.md)