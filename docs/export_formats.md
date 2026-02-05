# Export Formats

This document describes the export format contracts for Automatic Twitch Markers.

## File Naming Convention

**Preferred format:**
```
{Stream Date (YYYY-MM-DD)} {Stream Title} - Twitch Markers.{ext}
```

**Example:** `2026-02-04 Epic Gaming Session - Twitch Markers.csv`

**Rules:**
- Stream date in `YYYY-MM-DD` format
- Stream title with illegal filesystem characters removed (`\ / : * ? " < > |`)
- Extension matches format (`.csv` or `.edl`)

**Fallback (when title/date unavailable):**
```
{video_id}_{created_at date} - Twitch Markers.{ext}
```

**Example:** `1234567890_2026-02-04 - Twitch Markers.csv`

When:
- Stream title is unavailable → use `video_id`
- Stream date is unavailable → derive from `created_at` timestamp

---

## Twitch CSV (Canonical Format)

**Status:** ✅ Implemented (`export_csv.py`)

The canonical CSV format matches Twitch Highlighter-style output for compatibility with CSV→EDL converter workflows (e.g., [twitch-markers-to-edl](https://github.com/CodeWezus/twitch-markers-to-edl)).

### Columns (4, in order)

| # | Column | Description |
|---|--------|-------------|
| 1 | Timestamp | Position in `HH:MM:SS` format (floor, not rounded) |
| 2 | User Type | User type identifier (e.g., "broadcaster") |
| 3 | Username | Twitch username who created the marker |
| 4 | Marker Title | User-provided marker description |

### Format Details

- **Header row:** First cell is `Timestamp`
- **Encoding:** UTF-8 with BOM (for Excel compatibility)
- **Delimiter:** Comma-separated
- **Quoting:** All fields quoted
- **Timestamp:** Derived from `position_seconds` using floor (not rounded)

### Example Output

```csv
"Timestamp","User Type","Username","Marker Title"
"01:30:00","broadcaster","myusername","Boss fight starts"
"02:15:45","broadcaster","myusername","Epic win moment"
```

---

## Detailed CSV (Planned / Future)

> **Note:** This extended format is non-canonical and not required for CSV→EDL workflows.
> It may be offered as an optional "verbose" export in a future version.

| Column | Description |
|--------|-------------|
| Marker ID | Unique marker identifier |
| Description | User-provided marker description |
| Position (seconds) | Position in video (integer) |
| Position (timecode) | Timecode HH:MM:SS:FF format |
| Position (HH:MM:SS) | Human-readable timestamp |
| Created At | ISO 8601 timestamp |

---

## DaVinci Resolve EDL (Planned)

**Status:** ⏳ Pending Implementation

EDL (Edit Decision List) export for DaVinci Resolve-compatible marker import.

### EDL Format

**Header:**
```
TITLE: {Timeline Title}
FCM: NON-DROP FRAME
```

**Event + Marker metadata (per marker):**
```
{idx:03}  001      V     C        {startTC} {endTC} {startTC} {endTC}
 |C:ResolveColorBlue |M:{description} by {username} [{user_type}] |D:1
```

### Example Output

```edl
TITLE: 2026-02-04 Epic Gaming Session
FCM: NON-DROP FRAME

001  001      V     C        01:30:00:00 01:30:00:01 01:30:00:00 01:30:00:01
 |C:ResolveColorBlue |M:Boss fight starts by streamer [broadcaster] |D:1

002  001      V     C        02:15:45:00 02:15:45:01 02:15:45:00 02:15:45:01
 |C:ResolveColorBlue |M:Epic win moment by streamer [broadcaster] |D:1
```

### Timecode Rules

- **Format:** `HH:MM:SS:FF`
- **FPS:** Configurable via `timecode_fps` (default: 24)
- **Duration:** 1 frame (start `:00` → end `:01`)
- **Default offset:** +3600 seconds (01:00:00:00) for Resolve timeline
- **Offset disable:** Set to 0 seconds for raw timecodes

### Configuration

| Setting | Description |
|---------|-------------|
| `resolve_offset_enabled` | Enable/disable offset |
| `resolve_offset_timecode` | Offset in HH:MM:SS:FF format |
| `timecode_fps` | Frame rate (24, 30, etc.) |

---

## Output Directory

All exports are written to the configured output directory.

**Configuration options:**
- `config.json` → `output_dir` setting (for automated exports)
- Tray app → Output folder selector (planned, for user convenience)

The tray app will provide a folder picker so users can change the export destination without manually editing JSON files.

---

## Future: SaaS Storage

A future version will optionally store automatic exports on the Twitch Marker Agent website for:
- Cloud backup of marker archives
- Access from multiple devices
- Integration with other streaming tools

This feature is not yet implemented. Local exports remain the primary storage method.
