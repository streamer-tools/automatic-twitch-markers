# RUN 1: EDL Toggle UX Simplification

**Goal:** Simplify tray output format UX by making CSV implicit (always exported) and adding an "Additional Output Format" → "EDL" toggle that persists via StateStore.

---

## Current State Analysis

### Current Menu Structure (`app.py`)
- **Submenu:** "Output Format"
  - **Items:**
    - "CSV (always)" - checked, disabled (greyed out)
    - "EDL" - checkable

### Current State Management
- `TrayState.selected_formats: list[str]` - initialized from `config.export_formats`
- Format toggle callback modifies `selected_formats` list in-place
- `get_manual_fetch_formats(config, selected)` enforces CSV and normalizes
- No StateStore persistence for tray format selection

### Current Behavior
- User can toggle EDL on/off in menu
- CSV is always present but shown as greyed-out menu item
- Selection does NOT persist across restarts (resets to `config.export_formats`)
- Manual fetch passes `selected_formats` to controller

---

## Proposed Changes

### 1. Menu UX Changes (`app.py`)

**Remove:**
- "Output Format" submenu
- `_create_format_toggle()` helper for CSV

**Add:**
- "Additional Output Format" submenu
  - Single item: "EDL" (checkable)
  
**New State:**
- Replace `TrayState.selected_formats: list[str]` with simpler flag (or keep list but use StateStore)
- Menu checkbox reflects StateStore value

### 2. Controller Changes (`tray_controller.py`)

**New StateStore Key:**
```python
TRAY_EDL_ENABLED_KEY = "tray.edl_enabled"
```

**New Helper Functions:**
```python
def get_edl_enabled(state_store: StateStore) -> bool:
    """Get EDL export enabled flag from StateStore. Default: False."""
    ...

def set_edl_enabled(state_store: StateStore, enabled: bool) -> None:
    """Persist EDL export enabled flag to StateStore."""
    ...

def get_export_formats_from_edl_flag(edl_enabled: bool) -> tuple[str, ...]:
    """
    Derive export formats from EDL flag.
    Always includes CSV. If edl_enabled=True, includes EDL.
    """
    ...
```

**Modified Function:**
```python
def get_manual_fetch_formats(
    config: AppConfig,
    edl_enabled: bool,  # Changed from selected: list[str]
) -> tuple[str, ...]:
    """
    Get export formats for manual fetch.
    CSV is always included. EDL included if edl_enabled=True.
    """
    ...
```

**Rationale:** 
- Removes `selected_formats` concept entirely
- Single source of truth: StateStore EDL flag
- Simpler mental model: CSV implicit, EDL optional

### 3. State Initialization Changes (`app.py`)

**Current:**
```python
state = TrayState(
    selected_formats=list(config.export_formats),
)
```

**Proposed:**
```python
# Load EDL state from StateStore
edl_enabled = get_edl_enabled(state_store)

# Option A: Remove selected_formats from TrayState
state = TrayState()

# Option B: Keep selected_formats but populate from StateStore
state = TrayState(
    selected_formats=get_export_formats_from_edl_flag(edl_enabled),
)
```

**Preferred:** Option B (less invasive, keeps TrayState unchanged)

---

## Public API Proposal

### New Functions in `tray_controller.py`

```python
def get_edl_enabled(state_store: StateStore) -> bool:
    """
    Get EDL export enabled flag from StateStore.
    
    Args:
        state_store: State storage.
        
    Returns:
        True if EDL export is enabled, False otherwise (default).
    """
    ...

def set_edl_enabled(state_store: StateStore, enabled: bool) -> None:
    """
    Persist EDL export enabled flag to StateStore.
    
    Args:
        state_store: State storage.
        enabled: Whether EDL export is enabled.
    """
    ...

def get_export_formats_from_edl_flag(edl_enabled: bool) -> tuple[str, ...]:
    """
    Derive export formats list from EDL enabled flag.
    
    CSV is always included. EDL included if edl_enabled=True.
    
    Args:
        edl_enabled: Whether EDL export is enabled.
        
    Returns:
        Tuple of format strings ("csv",) or ("csv", "edl").
    """
    ...
```

### Modified Function Signature

```python
# BEFORE
def get_manual_fetch_formats(
    config: AppConfig,
    selected: list[str] | None = None,
) -> tuple[str, ...]:
    ...

# AFTER
def get_manual_fetch_formats(
    config: AppConfig,
    edl_enabled: bool,
) -> tuple[str, ...]:
    """
    Get export formats for manual fetch.
    
    CSV is always included. EDL included if edl_enabled=True.
    Config is kept for future extensibility (e.g., additional formats).
    
    Args:
        config: App config (reserved for future use).
        edl_enabled: Whether EDL export is enabled.
        
    Returns:
        Tuple of format strings ("csv",) or ("csv", "edl").
    """
    ...
```

**Note:** Keeping `config` parameter for backward compatibility and future extensibility, even though current implementation doesn't use it.

---

## Implementation Plan

### Step 1: Add Controller Helpers
1. Add `TRAY_EDL_ENABLED_KEY = "tray.edl_enabled"` constant
2. Implement `get_edl_enabled(state_store)` - reads StateStore, default False
3. Implement `set_edl_enabled(state_store, enabled)` - writes StateStore
4. Implement `get_export_formats_from_edl_flag(edl_enabled)` - pure function
5. Update `get_manual_fetch_formats()` signature and implementation

### Step 2: Update App.py Menu
1. Remove `_create_format_toggle()` function (no longer needed)
2. Replace "Output Format" submenu with "Additional Output Format"
3. Add single "EDL" menu item with:
   - `checked` predicate reads from StateStore
   - `on_toggle` callback writes to StateStore and updates menu
4. Update menu builder to use new structure

### Step 3: Update App.py State Init
1. Load `edl_enabled` from StateStore on startup
2. Initialize `TrayState.selected_formats` from `get_export_formats_from_edl_flag(edl_enabled)`
3. Update `on_format_toggle` to:
   - Call `set_edl_enabled(state_store, new_value)`
   - Update `state.selected_formats` to match
   - Call `update_menu()`

### Step 4: Update Manual Fetch Call Site
1. Change `on_fetch()` to compute `edl_enabled` from StateStore
2. Pass `edl_enabled` to `get_manual_fetch_formats()` instead of `state.selected_formats`

### Step 5: Tests
1. Update existing `TestGetManualFetchFormats` tests
2. Add tests for `get_edl_enabled()`, `set_edl_enabled()`, `get_export_formats_from_edl_flag()`
3. Add test for default behavior (EDL disabled)
4. Add test for persistence via StateStore

### Step 6: Documentation
1. Update `docs/tray_app.md` to reflect new menu structure
2. Update README if "Output Format" is mentioned

---

## Test Plan

### New Tests (`test_tray_controller.py`)

#### `TestGetEdlEnabled`
- `test_returns_false_by_default` - StateStore empty → False
- `test_returns_stored_true` - StateStore has "true" → True
- `test_returns_stored_false` - StateStore has "false" → False
- `test_handles_invalid_stored_value` - StateStore has garbage → False (fallback)

#### `TestSetEdlEnabled`
- `test_persists_true` - set_edl_enabled(True) → StateStore stores "true"
- `test_persists_false` - set_edl_enabled(False) → StateStore stores "false"

#### `TestGetExportFormatsFromEdlFlag`
- `test_csv_only_when_disabled` - edl_enabled=False → ("csv",)
- `test_csv_and_edl_when_enabled` - edl_enabled=True → ("csv", "edl")

#### Updated Tests
- `TestGetManualFetchFormats.test_returns_selected` - update to use `edl_enabled` param
- `TestGetManualFetchFormats.test_default_from_config` - update to use `edl_enabled` param
- `TestGetManualFetchFormats.test_enforces_csv` - update to use `edl_enabled` param
- All other existing tests - update call sites

---

## Files Modified/Added

| File | Change |
|------|--------|
| `src/twitch_marker_agent/tray_controller.py` | MODIFY - add helpers, update signature |
| `src/twitch_marker_agent/app.py` | MODIFY - simplify menu, update callbacks |
| `tests/test_tray_controller.py` | MODIFY - update + add new tests |
| `docs/tray_app.md` | MODIFY - document new menu structure |

---

## Edge Cases & Validation

### StateStore Value Types
- `None` → default False
- `"true"` → True
- `"false"` → False
- Other values → default False (defensive)

### Migration from Current State
- No migration needed - if user had EDL selected, they toggle it again
- Default (EDL disabled) is safe and matches most users

### Auto Mode
- Auto mode uses `config.export_formats`, NOT tray state
- This is intentional: tray toggle only affects manual fetch
- **Question for user:** Should auto mode also respect EDL toggle?

---

## Documentation Updates

### `docs/tray_app.md` (create if not exists)

```markdown
## Manual Fetch Output Formats

The tray app always exports CSV markers. You can optionally enable EDL export:

**Additional Output Format** → **EDL**
- Checked: Export both CSV and EDL
- Unchecked: Export CSV only (default)

Your EDL preference is saved and persists across restarts.

### Auto Mode Formats
Auto mode always uses the formats configured in `config.json` (`export_formats`).
```

### README.md Updates
- Update tray features list if it mentions "Output Format" toggles
- Clarify CSV is implicit, EDL is optional via toggle

---

## Open Questions for User

1. **Auto mode behavior:** Should auto mode ALSO respect the tray EDL toggle, or continue using `config.export_formats`?
   - **Current behavior:** Auto mode ignores tray state, uses config
   - **Proposed:** Keep current (tray toggle is manual-fetch-only)
   
2. **StateStore value format:** Store as `"true"`/`"false"` strings or `"1"`/`"0"`?
   - **Proposed:** Boolean-like strings `"true"`/`"false"` for clarity

3. **Default EDL state:** Should EDL default to enabled or disabled?
   - **Proposed:** Disabled (CSV-only) matches minimal/safe default

---

## Compliance Checklist

- ✅ No secrets logged
- ✅ No new dependencies
- ✅ No config.json schema changes
- ✅ No StateStore signature changes (uses existing `get_state`/`set_state`)
- ✅ core/ remains DI-friendly (controller is pure functions)
- ✅ Tests use unittest + unittest.mock only
- ✅ Minimal diffs (focused on menu + controller)

---

## STOP

This is RUN 1 (planning only). **Do NOT implement code yet.**

Awaiting user response with exactly: **"Proceed RUN 2"**
