# Tray Application

The Twitch Marker Agent system tray application provides a simple interface for managing marker exports.

## Features

### Auto Mode
Auto mode automatically exports markers when your stream ends. When enabled, the agent:
- Monitors your stream status via Twitch EventSub WebSocket
- Detects when your stream goes offline
- Fetches markers from your latest VOD
- Exports to configured formats automatically

To start auto mode, right-click the tray icon and select **"Start Auto Mode"**. To stop, select **"Stop Auto Mode"**.

### Manual Fetch
The **"Fetch Latest Stream Markers"** action allows you to manually export markers from your latest VOD on demand. This is useful for:
- One-off marker exports
- Testing your setup
- Exporting markers without running auto mode

### Multi-Stream Fetch
The **"Fetch Multiple Stream Markers"** action lets you export markers from multiple VODs within a date range:
- Opens a date range dialog where you can select start and end dates
- Fetches all archived VODs in the specified range (up to 60 days back)
- Exports markers for each VOD that has them
- Creates unique filenames by appending the video ID

**Note:** Standard Twitch VOD retention is 7-14 days. Turbo/Partner accounts may have up to 60 days.

### Output Format Selection

CSV markers are **always exported** (implicit, not shown in menu). You can optionally enable EDL export:

**Additional Output Format** → **EDL**
- ✅ Checked: Export both CSV and EDL
- ☐ Unchecked: Export CSV only (default)

Your EDL preference is saved and persists across restarts.

**Important:**  This toggle affects **both** manual fetch and auto mode exports. When EDL is enabled, both features will export CSV + EDL files.

### Output Folder
- **Open Folder**: Opens the current output folder in your file manager
- **Change Folder**: Select a different output folder (persists across restarts)

### Windows Startup
Enable **"Start on Windows Login"** to automatically launch the tray app when you sign in to Windows.

### Authentication Bootstrap
- Tray auth uses Twitch Device Code Flow.
- After successful auth, the app fetches the authenticated user via Helix `/users`.
- Broadcaster identity is persisted in `StateStore`; `config.json` is updated when `broadcaster_id` is blank/placeholder.
- The auth dialog auto-closes on success and a tray notification shows `Authenticated as <display_name>`.

## Default Behavior

- EDL export: **Disabled** (CSV-only)
- Output folder: Value from `config.json`
- Auto mode: **Stopped** (start manually when needed)

## Configuration

The tray app loads settings from `config.json` in the runtime base directory:
- Frozen exe: directory containing `TwitchMarkerAgent.exe`
- Dev mode: current working directory (`Path.cwd()`)
- If missing, `config.json` is auto-created on startup from bootstrap template data.
- Official releases should include seeded `client_id`; end users should not need to edit it.
- If `client_id` remains placeholder, tray auth is blocked and treated as an unseeded build.
- Local builders can seed with `TWITCH_MARKER_AGENT_CLIENT_ID`; local builds also fallback to `local.config.json` `client_id`.

See the main README for configuration details.

## Tips

- The tray icon shows "M" for markers
- Right-click the icon to access all features
- Notifications appear for fetch results and auto mode status changes
- Check the logs if exports fail (see README for log location)
