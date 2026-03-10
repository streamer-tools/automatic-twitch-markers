# Automatic Twitch Markers

A Windows-focused tray app that automatically exports Twitch stream markers after your stream ends.

Made with ❤️ by [Poisonslash](https://twitch.tv/Poisonslash) / [CodeWezus](https://github.com/CodeWezus)

## Why This Tool

As of now there is no way to automatically retrieve stream markers from Twitch after the broadcast ends.

Even Streamer.bot cannot directly fetch stream markers because Twitch's `Get Stream Markers` endpoint requires a broadcaster OAuth user token with `channel:manage:broadcast` scope.

Automatic Twitch Markers solves that by:
1. Running a one-time Twitch authentication flow.
2. Maintaining token validity automatically.
3. Listening for `stream.offline` events.
4. Exporting markers to editor-friendly files after each stream.

## Goals

**Local MVP (v1):**
- Windows tray app that runs quietly in the background.
- Automatic CSV/EDL marker export after each stream.
- SQLite-backed state to prevent duplicate exports.
- Clear logging and predictable recovery behavior.

**Product Direction:**
- Keep the core modules framework-agnostic so the same logic can power future integrations.

Final outcome: a reliable, low-maintenance marker export workflow that users can set once and trust.

## Quick Start (Portable Release)
1. Download the latest Windows zip from [GitHub Releases](https://github.com/streamer-tools/automatic-twitch-markers/releases).
2. Extract the zip to a folder you control.
3. Run `Automatic Twitch Markers.exe`.
4. Click **Authenticate with Twitch** in the tray menu.
5. Use **Fetch Latest Stream Markers** or start **Auto Mode**.

`config.json` is auto-created on first launch if missing. Official releases should include a seeded `client_id`, so end users should not need to edit auth fields.

## Features
- Auto Mode: listens for `stream.offline` and exports markers automatically.
- Auto Mode remembers your preference across app restarts and PC reboots.
- Manual fetch: export markers from the latest VOD on demand.
- Multi-fetch: export markers across a date range (up to 60 days).
- Export formats: Twitch-style CSV (always) and optional Resolve-compatible EDL.
- Windows startup toggle from tray menu.

## Documentation
- [Documentation Index](docs/README.md)
- [User Documentation](docs/user/README.md)
- [Developer Documentation](docs/dev/README.md)

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

Full configuration reference: [docs/user/configuration.md](docs/user/configuration.md).

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