# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Changed
- No unreleased entries yet.

## [1.0.0] - 2026-02-13

### Added
- Tray notifications for Auto Mode export outcomes (success and errors; skip outcomes remain silent).

### Changed
- Auth-status checks in tray flow are refresh-aware to reduce unnecessary reauthentication prompts.

### Fixed
- Auto Mode marker attribution regression by passing broadcaster `user_id` in video-specific marker fetch path.
- Refresh payload handling for public/device-flow builds to avoid placeholder `client_secret` usage.

## [0.9.0] - 2026-02-13

### Added
- Runtime path resolver for portable behavior (`config.json`, logs, and relative state paths anchored to EXE directory when frozen, `Path.cwd()` in dev).
- First-launch config bootstrap for missing `config.json`.
- Build-time bootstrap template bundling for EXE (`bootstrap/config.bootstrap.json`).
- Broadcaster identity bootstrap after tray device auth via Helix `/users`.

### Changed
- Local/CI build behavior to fail fast when bootstrap `client_id` remains placeholder (with explicit local dev override).
- Auth error copy in tray/CLI to identify unseeded builds clearly.
- Windows startup command composition to absolute, quoted executable/interpreter paths.
- Broadcaster ID resolution to prioritize persisted state then config fallback.

### Fixed
- Tray auth dialog auto-close on success with deterministic success notification.
- Path resolution issues caused by System32 working-directory launches.

## [0.8.1] - 2026-02-12

### Changed
- EDL output alignment with DaVinci timeline-marker style preamble and event formatting.

## [0.8.0] - 2026-02-12

### Changed
- Marker attribution uses Helix grouping fields (`user_name` fallback `user_login`) instead of placeholders.
- Marker `user_type` inferred as `Broadcaster` or `Editor` per marker row.
- CSV export remains quoted and BOM-encoded while writing marker rows only.

### Fixed
- CSV/EDL export correctness for attribution and no-header CSV behavior.

## [0.7.0] - 2026-02-11

### Added
- ttkbootstrap date range dialog styling hooks and validation helpers for multi-fetch.

### Changed
- Date picker implementation migrated from tkcalendar to ttkbootstrap DateEntry.
- Default multi-fetch date dialog theme set to `superhero`.
- Dialog flow changed to pseudo-modal behavior for DateEntry compatibility.

### Fixed
- Close/reopen Tk bgerror and styling instability by using shared hidden root and canceling pending callbacks.

### Removed
- tkcalendar and babel build dependencies.

## [0.6.0] - 2026-02-10

### Added
- Device Code Flow auth dialog with clipboard and browser-launch UX.
- Auth gating for tray actions requiring tokens.

### Changed
- Tray UX to keep non-auth settings available while fetch/auto actions are gated.

## [0.5.0] - 2026-02-09

### Added
- Multi-fetch tray action with date range picker and preset ranges (7/14/30/60).
- `videos_api.py` for archived VOD listing and date-window filtering.
- Multi-fetch controller flow with per-VOD export handling and summary stats.

### Fixed
- Multi-fetch export wiring to align with CSV/EDL function signatures and offset behavior.

## [0.4.1] - 2026-02-08

### Changed
- Tray output format UX to CSV-always with optional EDL toggle.

### Fixed
- Auto Mode clean shutdown and stop responsiveness issues.
- Async stop scheduling warning during shutdown.

## [0.4.0] - 2026-02-07

### Added
- Windows startup integration via HKCU Run key.
- Local PyInstaller build script and CI release workflow for Windows artifacts.

## [0.3.4] - 2026-02-05

### Added
- Windows tray application entrypoint and manual fetch pipeline wiring.
- Tray controller helpers for output directory persistence and format handling.

## [0.3.3] - 2026-02-05

### Added
- Resolve-compatible EDL export with marker metadata lines.
- Config-driven Resolve offset controls.

### Changed
- CSV export aligned to canonical 4-column Twitch-style schema.

## [0.3.2] - 2026-02-04

### Added
- Stream offline handler with dedupe and retry semantics.
- Helix marker and video retrieval APIs in core module.

## [0.3.1] - 2026-02-04

### Added
- Helix EventSub subscription management module with idempotent ensure logic.

## [0.3.0] - 2026-02-04

### Added
- EventSub WebSocket client implementation with reconnect and message dispatch support.

## [0.2.1] - 2026-02-02

### Added
- Token refresh/validate/get-valid token maintenance methods.

### Fixed
- Locking hardening for direct refresh calls and expiry edge cases.

## [0.2.0] - 2026-02-02

### Added
- OAuth browser login flow and CLI auth command.
- CSRF-protected callback handling with persistent token storage.

## [0.1.0] - 2026-02-01

### Added
- Initial project scaffold (config, state store, retry utility, and baseline tests).
