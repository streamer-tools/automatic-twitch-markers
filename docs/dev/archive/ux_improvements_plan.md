# Implementation Plan: Tray App UX Improvements

## Overview

This plan covers two areas of UX improvement:
1. **Device Code Flow Auth Dialog** - Auto-copy code, auto-open browser, use `verification_uri_complete`
2. **Multi-Fetch Date Range Dialog** - Replace text inputs with `tkcalendar.DateEntry`, add preset buttons, fix focus

---

## Preflight Questions & Decisions

### Q1: Menu Gating When Unauthenticated
**Question:** When unauthenticated, should Output Folder / Start on Login remain enabled?

**Decision:** [DONE] Keep them enabled (they don't require Twitch auth)

| Menu Item | Unauthenticated | Authenticated |
|-----------|-----------------|---------------|
| Auth status display | Enabled (shows "[WARN] Not authenticated") | Enabled (shows "[OK] Connected as X") |
| Authenticate with Twitch... | Enabled + Visible | Hidden |
| Disconnect Twitch | Hidden | Enabled + Visible |
| Start/Stop Auto Mode | **Disabled** | Enabled |
| Fetch Latest Stream Markers | **Disabled** | Enabled |
| Fetch Multiple Stream Markers | **Disabled** | Enabled |
| Additional Output Format (EDL) | Enabled | Enabled |
| Output Folder | Enabled | Enabled |
| Start on Windows Login | Enabled | Enabled |
| Exit | Enabled | Enabled |

### Q2: Multi-Fetch Preset Behavior
**Question:** Should preset buttons set `end_date=today` or preserve current end_date?

**Decision:** [DONE] Presets always set `end_date=today` for predictable "Last N days" behavior

Preset logic: `start_date = today - N`, `end_date = today`

### Q3: Calendar UX
**Question:** Use `tkcalendar.DateEntry` - allow typing or calendar-only?

**Decision:** [DONE] Allow typing + validate; set `mindate`/`maxdate` to enforce range
- DateEntry supports both keyboard input and dropdown calendar
- Use `date_pattern='yyyy-mm-dd'` for consistent display
- Validate on OK to catch any edge cases

### Q4: Range Constraint
**Question:** Confirm allowed window is last 60 days from today (inclusive)?

**Decision:** [DONE] Yes
- `earliest_allowed = today - 60 days`
- `latest_allowed = today`

### Q5: Auth UX - Browser + Copy Behavior
**Question:** Auto-open `verification_uri_complete` when present?

**Decision:** [DONE] Yes
- If Twitch returns `verification_uri_complete`, open that (pre-fills code)
- Otherwise open `verification_uri` (user must paste code)
- Auto-copy code to clipboard on dialog open
- Update help text: "Code copied! Paste it on the Twitch page if prompted."

---

## Proposed Public API

### A) `core/device_auth.py` Changes

```python
@dataclass(frozen=True)
class DeviceCodeResponse:
    """Response from device code request."""

    device_code: str  # Secret code for polling (don't log this)
    user_code: str  # User-facing code to display
    verification_uri: str  # URL for user to visit
    verification_uri_complete: str | None  # URL with pre-filled code (if provided)
    expires_in: int  # Seconds until device_code expires
    interval: int  # Polling interval in seconds
```

Modify `request_device_code()`:
- Parse `verification_uri_complete` from response (optional field)
- No logging of this URL (contains device_code as query param)

### B) `ui/device_auth_dialog.py` Changes

```python
class DeviceAuthDialog:
    def __init__(
        self,
        parent: tk.Tk | tk.Toplevel | None,
        user_code: str,
        verification_uri: str,
        verification_uri_complete: str | None,  # NEW
        expires_in: int,
        on_cancel: Callable[[], None],
        browser_opener: Callable[[str], bool] | None = None,
        clipboard_copier: Callable[[str], None] | None = None,  # NEW - for testing
        auto_open_browser: bool = True,  # NEW
        auto_copy_code: bool = True,  # NEW
    ):
        ...

    def _auto_setup(self) -> None:
        """Called on show() - auto-copy and auto-open if enabled."""
        ...
```

### C) `ui/date_range_dialog.py` Changes

```python
class DateRangeDialog:
    """Tkinter dialog with tkcalendar.DateEntry for date range selection."""

    def __init__(
        self,
        parent: tk.Tk | tk.Toplevel | None = None,
        max_days_back: int = 60,
    ):
        ...

    def _set_preset(self, days: int) -> None:
        """Set date range to last N days (end=today, start=today-N)."""
        ...
```

DateEntry configuration:
- `mindate=today - 60`
- `maxdate=today`
- `date_pattern='yyyy-mm-dd'`

### D) `app.py` Menu Gating

Add to `create_tray_menu`:

```python
def requires_auth_and_enabled(_: pystray.MenuItem) -> bool:
    """True if authenticated and not currently fetching."""
    is_auth = auth_status is not None and auth_status.is_authenticated
    not_fetching = not state.is_fetching
    return is_auth and not_fetching
```

Apply `enabled=requires_auth_and_enabled` to:
- Start Auto Mode
- Stop Auto Mode  
- Fetch Latest Stream Markers
- Fetch Multiple Stream Markers

---

## Implementation Steps (RUN 2)

### Step 1: Add tkcalendar Dependency
1. Update `pyproject.toml`:
   ```toml
   dependencies = [
       "requests",
       "websockets",
       "pystray",
       "Pillow",
       "tkcalendar>=1.6.1",
   ]
   ```
2. Update `scripts/build_exe.ps1` if PyInstaller requires hidden imports
3. Test import: `python -c "from tkcalendar import DateEntry"`

### Step 2: Auth Dialog Improvements

**File: `core/device_auth.py`**
- Add `verification_uri_complete: str | None` to `DeviceCodeResponse`
- Parse from API response in `request_device_code()`

**File: `ui/device_auth_dialog.py`**
- Add `verification_uri_complete`, `auto_copy_code`, `auto_open_browser`, `clipboard_copier` params
- On `show()`:
  - If `auto_copy_code`: copy to clipboard immediately
  - If `auto_open_browser`: open `verification_uri_complete` or `verification_uri`
- Update status text: "Code copied! Paste it on the Twitch page if prompted."
- Rename "Open Twitch" button to "Open Browser" (it opens the appropriate URL)

### Step 3: Menu Gating

**File: `app.py`**
- Add `requires_auth_and_enabled()` helper inside `create_tray_menu`
- Apply to: Start/Stop Auto Mode, Fetch actions
- Keep Output Folder, EDL toggle, Windows Login toggles always enabled

### Step 4: Multi-Fetch Dialog Upgrade

**File: `ui/date_range_dialog.py`**
- Import: `from tkcalendar import DateEntry`
- Replace `tk.Entry` with `DateEntry`:
  ```python
  self.start_entry = DateEntry(
      input_frame,
      width=12,
      date_pattern='yyyy-mm-dd',
      mindate=self.earliest_allowed,
      maxdate=self.today,
  )
  ```
- Add preset button frame with 7/14/30/60 buttons
- Fix focus: ensure `self.start_entry.focus_set()` after window creation
- Use hidden root (`tk.Tk().withdraw()`) when no parent to avoid focus issues

### Step 5: Tests

**`tests/test_device_auth.py`** (extend):
- `test_request_device_code_parses_verification_uri_complete`
- `test_request_device_code_handles_missing_verification_uri_complete`

**`tests/test_date_presets.py`** (new):
- Pure function: `compute_preset_dates(days: int, today: date, earliest_allowed: date)`
- Test clamping when days > 60

**`tests/test_menu_gating.py`** (new):
- Extract `should_enable_twitch_action(is_authenticated, is_fetching)` pure helper
- Test: unauthenticated -> False
- Test: authenticated + fetching -> False
- Test: authenticated + not fetching -> True

**Avoid:** Full tkinter event-loop testing

### Step 6: Documentation Updates
- Update README.md with calendar picker UX mention
- Update AGENTS.md with tkcalendar in implemented list

---

## Test Plan

### Device Auth Tests (extend `test_device_auth.py`)
- [x] `test_request_device_code_parses_verification_uri_complete` - when present
- [x] `test_request_device_code_handles_missing_verification_uri_complete` - returns None

### Date Preset Tests (new `test_date_presets.py`)
- [x] `test_preset_7_days` - end=today, start=today-7
- [x] `test_preset_30_days` - end=today, start=today-30
- [x] `test_preset_60_days` - end=today, start=today-60
- [x] `test_preset_clamps_to_earliest` - days=90 clamps to earliest_allowed

### Menu Gating Tests (new `test_menu_gating.py`)
- [x] `test_unauthenticated_disables_fetch` - returns False
- [x] `test_authenticated_enables_fetch` - returns True
- [x] `test_authenticated_but_fetching_disables` - returns False
- [x] `test_output_folder_always_enabled` - always True regardless of auth

---

## Files Changed/Added (RUN 2)

| File | Action | Description |
|------|--------|-------------|
| `pyproject.toml` | Modify | Add `tkcalendar>=1.6.1` dependency |
| `scripts/build_exe.ps1` | Modify | Add hidden imports if needed |
| `core/device_auth.py` | Modify | Add `verification_uri_complete` field |
| `ui/device_auth_dialog.py` | Modify | Auto-copy, auto-open, new params |
| `ui/date_range_dialog.py` | Modify | DateEntry, presets, focus fix |
| `app.py` | Modify | Menu gating for auth-required actions |
| `tests/test_device_auth.py` | Modify | Add verification_uri_complete tests |
| `tests/test_date_presets.py` | New | Preset date computation tests |
| `tests/test_menu_gating.py` | New | Menu gating logic tests |
| `README.md` | Modify | Document new features |
| `AGENTS.md` | Modify | Update implemented list |

---

## Security & Risk Notes

### Supply-Chain Risk (tkcalendar)
- **Risk:** Third-party dependency
- **Mitigation:** 
  - Pin to stable version `>=1.6.1`
  - tkcalendar is UI-only (no network, no token access)
  - Well-established library (90k+ monthly downloads)

### PyInstaller Packaging
- **Risk:** DateEntry may need hidden imports or data files
- **Mitigation:**
  - Test EXE after build: open multi-fetch dialog
  - Add `--hidden-import=tkcalendar` if needed

### Secret Exposure
- **Risk:** `verification_uri_complete` contains device_code as query param
- **Mitigation:**
  - NEVER log `verification_uri_complete`
  - Only use for browser open, never display

---

## Verification Checklist (RUN 2)

- [ ] `pip install tkcalendar` works
- [ ] DateEntry appears with calendar dropdown
- [ ] Preset buttons set correct dates
- [ ] Dates outside range are disabled in calendar
- [ ] Auth dialog auto-copies code on open
- [ ] Auth dialog auto-opens browser
- [ ] Menu items disabled when unauthenticated
- [ ] All new tests pass
- [ ] EXE build works with tkcalendar
