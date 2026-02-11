# Implementation Plan: Replace tkcalendar with ttkbootstrap DateEntry

## Overview

Replace `tkcalendar.DateEntry` with `ttkbootstrap.DateEntry` in the multi-fetch date range dialog to fix month navigation bugs and improve UI appearance.

**Problem:** User reports severe UX bugs with tkcalendar: month navigation closes/sticks/disables months when using mindate/maxdate constraints.

**Solution:** Switch to ttkbootstrap DateEntry which provides modern theming but requires custom validation logic (no native mindate/maxdate support).

---

## Preflight Questions & Decisions

### Q1: Dependency Approval
**Question:** Add `ttkbootstrap` as a new dependency?

**Recommendation:** ✅ Yes, add `ttkbootstrap>=1.5.0,<2.0`

**Benefits:**
- Modern ttk themes (flatly, darkly, cosmo, etc.)
- Built-in DateEntry widget with popup calendar
- Styling via `bootstyle` parameter (primary, secondary, success, info, warning, danger)
- Better maintained than tkcalendar (active development, responsive maintainers)
- Validation hooks via `raise_exception` parameter

**Risks & Mitigations:**
- **Supply chain risk:** Mitigate with version bounds `>=1.5.0,<2.0`
- **App size:** ~250KB additional size (negligible for Windows exe)
- **PyInstaller:** May need `--hidden-import ttkbootstrap` (verify in test build)
- **Performance:** Negligible; UI-only library

**Default:** WAIT FOR USER APPROVAL before proceeding to RUN 2

---

### Q2: Theming Scope
**Question:** Apply ttkbootstrap theme globally or dialog-only?

**Decision:** ✅ Dialog-only to keep diffs minimal

Apply theme only within DateRangeDialog using:
```python
import ttkbootstrap as ttk
from ttkbootstrap import DateEntry

# In show() method:
style = ttk.Style(theme="flatly")  # or "cosmo", "litera"
```

This avoids affecting Device Auth Dialog or other UI components.

---

### Q3: Range Enforcement UX
**Question:** Since ttkbootstrap DateEntry lacks mindate/maxdate, how to handle out-of-range selections?

**Decision:** ✅ Reject + revert with clear error message

Approach:
- Allow user to select any date in calendar popup
- On selection change, validate against constraints
- If invalid: revert to last valid value + show error label + tooltip
- Error message: "Date must be between {min_date} and {max_date}"

Alternative (clamp automatically) rejected because it's confusing UX.

---

### Q4: Keep Preset Buttons?
**Question:** Retain "Last 7 / 14 / 30 / 60 days" preset buttons?

**Decision:** ✅ Yes, keep presets with same behavior (end=today)

---

## Dependency Proposal

### ttkbootstrap
- **Version:** `>=1.5.0,<2.0`
- **License:** MIT
- **Monthly downloads:** ~120k (PyPI)
- **Last release:** Recent (actively maintained)
- **Dependencies:** Only Pillow (already in our deps)

### Removal
- **tkcalendar:** Remove from pyproject.toml
- **babel:** Only needed by tkcalendar; remove from build script

---

## Proposed Public API

### DateRangeDialog Class (unchanged public interface)
```python
class DateRangeDialog:
    def __init__(
        self,
        parent: tk.Tk | tk.Toplevel | None = None,
        max_days_back: int = 60
    ):
        ...
    
    def show(self) -> tuple[date, date] | None:
        """Show dialog and wait for user input."""
        ...
```

### Pure Helper Functions (NEW - testable)
```python
def compute_allowed_window(
    today: date,
    max_days_back: int
) -> tuple[date, date]:
    """
    Compute min and max allowed dates.
    
    Args:
        today: Current date (typically date.today()).
        max_days_back: Maximum days allowed in the past.
    
    Returns:
        (earliest_allowed, latest_allowed) tuple.
    """
    earliest = today - timedelta(days=max_days_back)
    return (earliest, today)


def validate_date_in_range(
    d: date,
    min_date: date,
    max_date: date,
    field_name: str = "Date"
) -> None:
    """
    Validate date is within allowed range.
    
    Args:
        d: Date to validate.
        min_date: Minimum allowed date (inclusive).
        max_date: Maximum allowed date (inclusive).
        field_name: Name of field for error message.
    
    Raises:
        ValueError: If date is out of range.
    """
    if d < min_date:
        raise ValueError(
            f"{field_name} ({d}) cannot be earlier than {min_date}"
        )
    if d > max_date:
        raise ValueError(
            f"{field_name} ({d}) cannot be later than {max_date}"
        )


def validate_date_range_order(
    start: date,
    end: date
) -> None:
    """
    Validate start date is before or equal to end date.
    
    Args:
        start: Start date.
        end: End date.
    
    Raises:
        ValueError: If start > end.
    """
    if start > end:
        raise ValueError(
            f"Start date ({start}) must be before or equal to end date ({end})"
        )


def compute_preset_dates(
    days: int,
    today: date,
    earliest_allowed: date,
) -> tuple[date, date]:
    """
    Compute start and end dates for a preset range.
    
    (EXISTING - keep unchanged)
    """
    ...
```

---

## Implementation Steps (RUN 2)

### Step 1: Update Dependencies
1. Update `pyproject.toml`:
   - Remove `tkcalendar>=1.6.1,<2.0`
   - Add `ttkbootstrap>=1.5.0,<2.0`
2. Update `scripts/build_exe.ps1`:
   - Remove `--collect-submodules tkcalendar`
   - Remove `--hidden-import babel.numbers`
   - Add `--hidden-import ttkbootstrap` if needed (verify via test build)

### Step 2: Add Pure Validation Helpers
Create validation helpers in `ui/date_range_dialog.py`:
- `compute_allowed_window(today, max_days_back)`
- `validate_date_in_range(d, min_date, max_date, field_name)`
- `validate_date_range_order(start, end)`

These are pure functions with no tkinter dependencies for easy testing.

### Step 3: Replace DateEntry Widgets
In `DateRangeDialog.show()`:
```python
# OLD:
from tkcalendar import DateEntry

self.start_entry = DateEntry(
    input_frame,
    width=14,
    font=("Arial", 10),
    date_pattern="yyyy-mm-dd",
    mindate=self.earliest_allowed,  # NOT SUPPORTED
    maxdate=self.today,              # NOT SUPPORTED
)

# NEW:
import ttkbootstrap as ttk
from ttkbootstrap import DateEntry

# Apply theme (dialog-only)
style = ttk.Style(theme="flatly")

self.start_entry = DateEntry(
    input_frame,
    width=14,
    dateformat="%Y-%m-%d",  # ttkbootstrap uses dateformat not date_pattern
    bootstyle="primary",    # Modern styling
    raise_exception=False,  # We handle validation manually
)
```

### Step 4: Implement Custom Range Enforcement
Add validation on:
1. **DateEntry selection event** - bind to `<<DateEntrySelected>>`
2. **Preset button click** - validate before setting
3. **OK button click** - final validation

Validation flow:
```python
def _validate_and_constrain_dates(self) -> bool:
    """
    Validate current date selections.
    
    Returns True if valid, False otherwise (with error displayed).
    """
    try:
        start = self.start_entry.get_date()
        end = self.end_entry.get_date()
        
        # Convert datetime to date if needed
        if isinstance(start, datetime):
            start = start.date()
        if isinstance(end, datetime):
            end = end.date()
        
        # Validate each date in range
        validate_date_in_range(start, self.earliest_allowed, self.today, "Start date")
        validate_date_in_range(end, self.earliest_allowed, self.today, "End date")
        
        # Validate ordering
        validate_date_range_order(start, end)
        
        # Clear error label
        if self.error_label:
            self.error_label.config(text="")
        
        return True
        
    except ValueError as e:
        # Show error, keep last valid values
        if self.error_label:
            self.error_label.config(text=str(e))
        return False
```

### Step 5: Update Preset Buttons
Presets remain unchanged in behavior:
```python
def _set_preset(self, days: int) -> None:
    """Set date range to last N days (end=today, start=today-N)."""
    start_date, end_date = compute_preset_dates(
        days=days,
        today=self.today,
        earliest_allowed=self.earliest_allowed,
    )
    if self.start_entry and self.end_entry:
        self.start_entry.set_date(start_date)
        self.end_entry.set_date(end_date)
        # Validate immediately
        self._validate_and_constrain_dates()
```

### Step 6: Focus/Editability
Keep existing focus logic:
```python
# Ensure focus - critical for editability
self.dialog.lift()
self.dialog.focus_force()
self.start_entry.focus_set()
```

Test that grab_set() doesn't interfere with ttkbootstrap DateEntry popup.

### Step 7: Update Tests
- Update existing tests in `tests/test_date_presets.py` (already pure)
- Add new validation tests (use pure helpers)
- No tkinter event-loop tests

---

## Test Plan

### Existing Tests (keep unchanged)
`tests/test_date_presets.py`:
- `test_preset_7_days` - end=today, start=today-7
- `test_preset_30_days` - end=today, start=today-30
- `test_preset_60_days` - end=today, start=today-60
- `test_preset_clamps_to_earliest` - days=90 clamps to earliest
- `test_end_always_equals_today` - end always equals today

### New Tests (pure functions)
`tests/test_date_range_validation.py` (NEW):
```python
class TestComputeAllowedWindow(unittest.TestCase):
    def test_computes_60_day_window(self):
        today = date(2026, 2, 9)
        earliest, latest = compute_allowed_window(today, max_days_back=60)
        self.assertEqual(latest, today)
        self.assertEqual(earliest, date(2025, 12, 11))  # 60 days back
    
    def test_computes_7_day_window(self):
        today = date(2026, 2, 9)
        earliest, latest = compute_allowed_window(today, max_days_back=7)
        self.assertEqual(latest, today)
        self.assertEqual(earliest, date(2026, 2, 2))


class TestValidateDateInRange(unittest.TestCase):
    def test_valid_date_passes(self):
        d = date(2026, 2, 5)
        min_d = date(2026, 2, 1)
        max_d = date(2026, 2, 9)
        # Should not raise
        validate_date_in_range(d, min_d, max_d)
    
    def test_date_before_min_raises(self):
        d = date(2026, 1, 31)
        min_d = date(2026, 2, 1)
        max_d = date(2026, 2, 9)
        with self.assertRaises(ValueError) as ctx:
            validate_date_in_range(d, min_d, max_d)
        self.assertIn("cannot be earlier than", str(ctx.exception))
    
    def test_date_after_max_raises(self):
        d = date(2026, 2, 10)
        min_d = date(2026, 2, 1)
        max_d = date(2026, 2, 9)
        with self.assertRaises(ValueError) as ctx:
            validate_date_in_range(d, min_d, max_d)
        self.assertIn("cannot be later than", str(ctx.exception))
    
    def test_boundary_dates_pass(self):
        min_d = date(2026, 2, 1)
        max_d = date(2026, 2, 9)
        # Min boundary
        validate_date_in_range(min_d, min_d, max_d)
        # Max boundary
        validate_date_in_range(max_d, min_d, max_d)


class TestValidateDateRangeOrder(unittest.TestCase):
    def test_start_before_end_passes(self):
        start = date(2026, 2, 1)
        end = date(2026, 2, 9)
        # Should not raise
        validate_date_range_order(start, end)
    
    def test_start_equals_end_passes(self):
        start = date(2026, 2, 5)
        end = date(2026, 2, 5)
        # Should not raise
        validate_date_range_order(start, end)
    
    def test_start_after_end_raises(self):
        start = date(2026, 2, 10)
        end = date(2026, 2, 5)
        with self.assertRaises(ValueError) as ctx:
            validate_date_range_order(start, end)
        self.assertIn("must be before or equal to", str(ctx.exception))
```

---

## Files Changed/Added (RUN 2)

| File | Action | Description |
|------|--------|-------------|
| `pyproject.toml` | Modify | Remove tkcalendar, add ttkbootstrap |
| `ui/date_range_dialog.py` | Modify | Replace DateEntry, add validation helpers |
| `scripts/build_exe.ps1` | Modify | Remove tkcalendar/babel imports, add ttkbootstrap |
| `tests/test_date_range_validation.py` | New | Pure function validation tests |
| `tests/test_date_presets.py` | Keep | Already pure, no changes needed |
| `README.md` | Modify | Document new styling |
| `docs/ttkbootstrap_migration_plan.md` | New | This plan document |

---

## Security & Risk Notes

### Supply-Chain Risk (ttkbootstrap)
- **Risk:** Third-party dependency
- **Mitigation:**
  - Pin to stable version `>=1.5.0,<2.0`
  - ttkbootstrap is UI-only (no network, no token access)
  - Well-established library (~120k monthly downloads)
  - MIT license (permissive, auditable)

### Removal Risk (tkcalendar)
- **Impact:** Users with current installs may see import errors if they run from source without reinstalling
- **Mitigation:** Update README with clear reinstall instructions

### PyInstaller Packaging
- **Risk:** ttkbootstrap may need hidden imports or data files
- **Mitigation:**
  - Test EXE after build: open multi-fetch dialog
  - Add `--hidden-import ttkbootstrap` if needed
  - Verify themes load correctly

---

## Verification Checklist (RUN 2)

- [ ] `pip install ttkbootstrap` works
- [ ] tkcalendar removed from environment
- [ ] DateEntry appears with modern styled calendar
- [ ] Month navigation works without freezing/disabling months
- [ ] Out-of-range dates show clear error message
- [ ] Preset buttons set correct dates
- [ ] Focus/editability works on dialog open
- [ ] All new validation tests pass
- [ ] EXE build works with ttkbootstrap
- [ ] Calendar popup doesn't interfere with grab_set()

---

## Next Steps

**RUN 1 COMPLETE** - Awaiting user approval.

To proceed to RUN 2, user must reply exactly: **"Proceed RUN 2"**
