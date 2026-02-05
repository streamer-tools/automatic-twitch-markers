# Tray App Design

This document describes the Windows system tray application for Automatic Twitch Markers.

## Overview

The tray app provides a "set-and-forget" UI for the marker exporter agent:
- Runs in the Windows system tray
- Manual fetch action for on-demand marker export
- Runtime format selection (CSV/EDL)
- Output folder picker with persistence

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                        app.py                           │
│              (pystray UI layer - Windows tray)          │
└─────────────────────────┬───────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│                   tray_controller.py                    │
│        (Pure functions - UI-agnostic, testable)         │
│  • resolve_output_dir()                                 │
│  • set_output_dir()                                     │
│  • get_manual_fetch_formats()                           │
│  • run_manual_fetch()                                   │
└─────────────────────────┬───────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│                      core/*                             │
│    (Framework-agnostic: offline_handler, oauth, etc)    │
└─────────────────────────────────────────────────────────┘
```

**Key principle:** `core/` must not import pystray. All UI dependencies stay in `app.py`.

## Menu Structure

```
Twitch Marker Agent
├─ Fetch Latest Markers (Now)
├─ ───────────────────────────
├─ Output Format
│   ├─ ☑ CSV
│   └─ ☐ EDL
├─ Output Folder
│   ├─ Open Folder
│   └─ Change Folder...
├─ ───────────────────────────
└─ Exit
```

## Manual Fetch Behavior

**Trigger:** User clicks "Fetch Latest Markers (Now)"

**Pipeline:**
1. Get valid access token via `TwitchOAuth.get_valid_user_access_token()`
2. Fetch latest video ID for broadcaster
3. Fetch markers for that video
4. Export to selected formats (CSV/EDL)
5. Show notification with result

**Dedupe:** Manual fetch uses `force=True` to always export, ignoring processed_video dedupe. User intent is explicit.

**Threading:** Fetch runs in worker thread to keep UI responsive.

## Output Directory

**Precedence:**
1. User-selected via folder picker (persisted in StateStore)
2. Fallback to `config.output_dir`

**StateStore key:** `tray.output_dir`

## Format Selection

**V1 behavior:** In-memory only
- Defaults to `config.export_formats` on startup
- User toggles are session-only
- Future: persist to StateStore

## Icon

Generated at runtime via Pillow (no asset file):
```python
# 64x64 purple circle (Twitch-ish color)
draw.ellipse([4, 4, 60, 60], fill="#9147ff")
```

## Error Handling

| Error | User Message |
|-------|--------------|
| `TokenRefreshError` | "Not logged in. Run auth-login first." |
| `MarkersAuthError` | "Re-auth required. Run auth-login." |
| `MarkersFetchError` | "Failed to fetch markers. Check logs." |
| No markers found | "No markers found for latest stream." |

## Configuration

No config.json changes. Tray uses existing config values:
- `broadcaster_id` - which channel to fetch
- `export_formats` - default format selection
- `output_dir` - fallback export location
- `resolve_offset_enabled` / `resolve_offset_timecode` - EDL offset
