# Automatic Twitch Markers

A Windows-focused tray app that automatically exports Twitch stream markers after your stream ends.

## Quick Start (Portable Release)
1. Download the latest Windows zip from [GitHub Releases](https://github.com/streamer-tools/automatic-twitch-markers/releases).
2. Extract the zip to a folder you control.
3. Run `TwitchMarkerAgent.exe`.
4. Click **Authenticate with Twitch** in the tray menu.
5. Use **Fetch Latest Stream Markers** or start **Auto Mode**.

`config.json` is auto-created on first launch if missing. Official releases should already include a seeded `client_id` so end users do not need to edit auth fields.

## Features
- Auto Mode: listens for `stream.offline` and exports markers automatically.
- Manual fetch: export markers from the latest VOD on demand.
- Multi-fetch: export markers across a date range (up to 60 days).
- Export formats: Twitch-style CSV (always) and optional Resolve-compatible EDL.
- Windows startup toggle from tray menu.

## Infrastructure Diagram
```text
+------------------------------+
| Entry Points                 |
| app.py (tray) | cli.py       |
+--------------+---------------+
               |
               v
+------------------------------+
| tray_controller.py           |
| UI-triggered orchestration   |
+--------------+---------------+
               |
               v
+------------------------------+
| core/agent_runner.py         |
| Async Auto Mode orchestrator |
+--------------+---------------+
               |
               v
+------------------------------+
| Core Modules                 |
| config.py                    |
| state_store.py               |
| twitch_oauth.py              |
| device_auth.py               |
| eventsub_ws.py               |
| eventsub_subscriptions.py    |
| offline_handler.py           |
| markers_api.py               |
| videos_api.py                |
| export_csv.py / export_edl.py|
+------------------------------+
```

## Documentation
- [Documentation Index](docs/README.md)
- [Tray App Guide](docs/tray_app.md)
- [Auto Mode Guide](docs/auto_mode.md)
- [Export Formats](docs/export_formats.md)
- [Configuration Reference](docs/configuration.md)
- [Project Structure and Architecture](docs/project_structure.md)
- [Windows Startup](docs/windows_startup.md)
- [Packaging Guide](docs/packaging.md)

## Configuration
Runtime paths are portable-oriented:
- Frozen EXE: base directory is the EXE folder.
- Dev mode (`python -m ...`): base directory is `Path.cwd()`.
- Config path: `<base_dir>/config.json`
- Logs path: `<base_dir>/logs/`
- Default state DB path: `<base_dir>/data/state.db`

If `client_id` is still a placeholder, auth is blocked. This indicates an unseeded local/dev build.

Required OAuth scope:
- `channel:manage:broadcast`

Full configuration key reference: [docs/configuration.md](docs/configuration.md).

## Project Structure
See the full current repository tree and architecture notes in [docs/project_structure.md](docs/project_structure.md).

## Developers (From Source)
1. Clone:
   ```powershell
   git clone https://github.com/streamer-tools/automatic-twitch-markers.git
   cd automatic-twitch-markers
   ```
2. Setup:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -e .
   ```
3. Run tests:
   ```powershell
   python -m unittest discover -s tests -v
   ```

See:
- [Contributing Guide](CONTRIBUTING.md)
- [Developer Docs](docs/dev/README.md)

## Changelog
See [CHANGELOG.md](CHANGELOG.md).

## License
MIT License. See [LICENSE](LICENSE).