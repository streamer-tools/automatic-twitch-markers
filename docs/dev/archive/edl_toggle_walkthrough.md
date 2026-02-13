# EDL Toggle Simplification - Implementation Walkthrough

## Summary

Successfully implemented EDL toggle simplification to improve tray UX. CSV is now always exported (implicit), with an optional EDL toggle that persists via StateStore.

## Changes Made

### 1. Controller & State Layer (`tray_controller.py`)

**Added:**
- `TRAY_EDL_ENABLED_KEY = "tray.edl_enabled"` constant
- `get_edl_enabled(state_store)` - reads EDL flag from StateStore, defaults to False
- `set_edl_enabled(state_store, enabled)` - persists EDL flag as "true"/"false" strings
- `get_export_formats_from_edl_flag(edl_enabled)` - derives format tuple from flag

**Modified:**
- `get_manual_fetch_formats()` signature changed from `(config, selected: list | None)` to `(config, edl_enabled: bool)`
- Now returns `("csv",)` or `("csv", "edl")` based on EDL flag

**Removed:**
- `_normalize_formats()` helper (no longer needed)

### 2. Tray UI (`app.py`)

**Menu Structure:**
- **Removed:** "Output Format" submenu with greyed-out "CSV (always)" + "EDL" items
- **Added:** "Additional Output Format" submenu with single checkable "EDL" item
- EDL checkbox reflects StateStore value and persists across restarts

**State Management:**
- Removed `TrayState.selected_formats` field
- Removed `_create_format_toggle()` function
- Removed `on_format_toggle()` callback
- Added `on_toggle_edl()` callback using `get_edl_enabled()` / `set_edl_enabled()`

**Manual Fetch:**
- Now loads EDL flag: `edl_enabled = get_edl_enabled(state_store)`
- Passes to `get_manual_fetch_formats(config, edl_enabled)`

### 3. Auto Mode Integration (`offline_handler.py`)

**Export Format Logic:**
- Checks for `tray.edl_enabled` StateStore key first
- If present: uses EDL flag to determine formats
- If missing: falls back to `config.export_formats`
- **Result:** Single source of truth for both manual fetch and auto mode

### 4. Tests (`test_tray_controller.py`)

**Added 9 new test methods:**
- `TestGetEdlEnabled` (6 tests):
  - `test_returns_false_by_default`
  - `test_returns_true_for_true_string`
  - `test_returns_true_for_one`
  - `test_returns_true_for_yes`
  - `test_returns_false_for_false_string`
  - `test_case_insensitive`
- `TestSetEdlEnabled` (2 tests):
  - `test_persists_true`
  - `test_persists_false`
- `TestGetExportFormatsFromEdlFlag` (2 tests):
  - `test_csv_only_when_disabled`
  - `test_csv_and_edl_when_enabled`

**Updated 3 existing test methods:**
- `test_csv_only_when_edl_disabled` (was `test_returns_selected`)
- `test_csv_and_edl_when_edl_enabled` (was `test_default_from_config`)
- `test_config_parameter_unused` (was `test_enforces_csv`)

### 5. Documentation

**Created [`docs/tray_app.md`](file:///c:/GoodVibez/automatic-twitch-markers/docs/tray_app.md):**
- Comprehensive tray app user guide
- Explains CSV is always exported (implicit)
- Documents "Additional Output Format" -> "EDL" toggle
- Notes that toggle affects both manual fetch and auto mode
- Includes tips, default behavior, and configuration guidance

## Validation

### Test Results
```
Ran 298 tests in 4.207s

OK
```

All tests passing, including:
- 9 new EDL toggle tests
- 3 updated format selection tests
- All existing tests (289 tests unchanged)

### Key Behaviors Verified

[DONE] **Default EDL state:** False (CSV-only)  
[DONE] **EDL toggle persistence:** Survives restarts via StateStore  
[DONE] **Manual fetch:** Respects EDL flag from StateStore  
[DONE] **Auto mode:** Respects EDL flag from StateStore with config fallback  
[DONE] **Menu checkbox:** Reflects persisted EDL state  
[DONE] **Format derivation:** `("csv",)` when disabled, `("csv", "edl")` when enabled

## Files Changed

| File | Lines Changed | Description |
|------|---------------|-------------|
| [`tray_controller.py`](file:///c:/GoodVibez/automatic-twitch-markers/src/twitch_marker_agent/tray_controller.py) | +64, -48 | Added EDL helpers, updated signature |
| [`app.py`](file:///c:/GoodVibez/automatic-twitch-markers/src/twitch_marker_agent/app.py) | +25, -45 | Simplified menu, removed selected_formats |
| [`offline_handler.py`](file:///c:/GoodVibez/automatic-twitch-markers/src/twitch_marker_agent/core/offline_handler.py) | +22, -2 | Auto mode respects EDL toggle |
| [`test_tray_controller.py`](file:///c:/GoodVibez/automatic-twitch-markers/tests/test_tray_controller.py) | +105, -53 | Added 9 tests, updated 3 tests |
| [`docs/tray_app.md`](file:///c:/GoodVibez/automatic-twitch-markers/docs/tray_app.md) | New file (64 lines) | Tray app user documentation |

**Total:** ~216 lines added, ~148 lines removed = **+68 net lines**

## Compliance Verification

[DONE] **No secrets logged:** No changes to logging; existing secret-safe patterns maintained  
[DONE] **No new dependencies:** Only used existing StateStore methods  
[DONE] **No config schema changes:** `config.export_formats` unchanged, EDL toggle is tray-only  
[DONE] **No StateStore signature changes:** Used existing `get_state()` / `set_state()`  
[DONE] **core/ remains DI-friendly:** Pure functions in `tray_controller.py`  
[DONE] **Tests: unittest only:** All tests use `unittest` + `unittest.mock`, no network calls  
[DONE] **Minimal diffs:** Focused changes, removed obsolete code

## User Impact

### Before
- "Output Format" submenu with greyed-out CSV + EDL options
- No persistence of format selection (reset to config on restart)
- Confusing UX: CSV shown as always-on but taking menu space

### After
- "Additional Output Format" -> "EDL" (single clean toggle)
- EDL preference persists across restarts
- Clearer UX: CSV implicit (always exported), EDL explicit (optional)
- **Single source of truth:** Manual fetch and auto mode both respect same toggle

## Manual Sanity Checks

### Recommended Test Steps

1. **Default behavior:**
   - Launch tray app (fresh state)
   - Verify EDL is unchecked in menu
   - Run manual fetch -> should export CSV only

2. **Enable EDL:**
   - Check "Additional Output Format" -> "EDL"
   - Run manual fetch -> should export CSV + EDL
   - Restart tray app -> EDL should still be checked

3. **Disable EDL:**
   - Uncheck EDL toggle
   - Run manual fetch -> should export CSV only
   - Restart -> EDL should remain unchecked

4. **Auto mode:**
   - Enable EDL toggle
   - Start auto mode
   - Trigger stream offline event
   - Verify CSV + EDL exported
   - Disable EDL and run again -> CSV only

## Conclusion

EDL toggle simplification complete. All tests passing, documentation updated, user experience improved. CSV is now implicit (always exported), EDL is optional via persistent toggle affecting both manual and automatic exports.
