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

## Default Behavior

- EDL export: **Disabled** (CSV-only)
- Output folder: Value from `config.json`
- Auto mode: **Stopped** (start manually when needed)

## Configuration

The tray app loads settings from `local.config.json`. See the main README for configuration details.

## Tips

- The tray icon shows "M" for markers
- Right-click the icon to access all features
- Notifications appear for fetch results and auto mode status changes
- Check the logs if exports fail (see README for log location)
