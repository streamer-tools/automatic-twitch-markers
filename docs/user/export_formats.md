# Export Formats

This document defines CSV and EDL export behavior.

## File Naming

Preferred:
```text
{YYYY-MM-DD} {Stream Title} - Twitch Markers.{ext}
```

Fallback:
```text
{video_id}_{date} - Twitch Markers.{ext}
```

## Twitch CSV (Canonical)

Status: Implemented (`export_csv.py`)

Columns (in order):
1. Timestamp (`HH:MM:SS`)
2. User Type (`Broadcaster` or `Editor`)
3. Username
4. Marker Title

Behavior:
- No header row.
- UTF-8 with BOM.
- Comma-separated, all fields quoted.
- Timestamp derived from marker position (floor behavior).

## DaVinci Resolve EDL

Status: Implemented (`export_edl.py`)

Preamble:
```text
EDL
Title: Timeline 1
FCM: NON-DROP-FRAME
```

Event + metadata:
```text
{idx:03}  001      V    C        {startTC} {endTC} {startTC} {endTC}
 |C:ResolveColorBlue |M:{description} by {username} [{user_type}] |D:1
```

Timecode notes:
- Format: `HH:MM:SS:FF`
- Duration: 1 frame
- Offset behavior controlled by `resolve_offset_enabled` and `resolve_offset_timecode`

## Output Directory
Exports are written to the configured output directory (`output_dir`, or tray-selected folder).

## Related Docs
- [Configuration](configuration.md)
- [Tray Application](tray_app.md)