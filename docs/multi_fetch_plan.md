# Fetch Multiple Stream Markers - RUN 1 Preflight Plan

> [!NOTE]
> **Status: IMPLEMENTED + PATCHED (v0.5.0)**
>
> This plan was implemented in RUN 2 and subsequently patched to fix runtime errors in export function signatures.

## Summary

Add a "Fetch Multiple Stream Markers" feature to the tray app that allows users to export markers from multiple VODs within a selectable date range (max 60 days back).

## User Review Required

> [!IMPORTANT]
> **Date Range Limit Rationale**
> 
> Maximum selectable range is **past 60 days** from today. This is conservative but allows for:
> - Partner/Affiliate base retention (7-14 days)
> - Partner/Affiliate with Turbo subscribers (~60 days)
> - We DO NOT attempt to detect subscription/partner status (unreliable)
> - UI will warn: "Older VODs may not exist depending on your retention settings"

> [!IMPORTANT]
> **No New Dependencies**
> 
> Using stdlib `tkinter` for date range dialog (already available in Python stdlib, no install needed).

> [!WARNING]
> **StateStore Signature Unchanged**
> 
> No changes to StateStore public API. All new state (if any) uses existing `get_state(key)` / `set_state(key, value)` methods.

## Proposed Changes

### Core API - Date Range Video Listing

#### [NEW] [`core/videos_api.py`](file:///c:/GoodVibez/automatic-twitch-markers/src/twitch_marker_agent/core/videos_api.py)

**Purpose:** Fetch archived VODs in a date range using Helix Get Videos endpoint with pagination.

**New Data Class:**
```python
@dataclass
class ArchivedVideo:
    """Represents an archived VOD."""
    video_id: str
    title: str
    created_at: str  # RFC3339 timestamp
    url: str
```

**New Exception:**
```python
class VideosFetchError(Exception):
    """Raised when video fetch fails."""
    pass
```

**Main Function:**
```python
def list_videos_in_date_range(
    http_client: requests.Session,
    config: AppConfig,
    access_token: str,
    user_id: str,
    start_date: date,  # datetime.date, inclusive
    end_date: date,    # datetime.date, inclusive
    logger: logging.Logger | None = None,
) -> list[ArchivedVideo]:
    """
    List archived VODs within date range using Helix Get Videos.
    
    Pagination: continues until cursor exhausted or results older than start_date.
    Results are ordered newest-first by Twitch API.
    
    Args:
        http_client: Requests session.
        config: App config (client_id).
        access_token: Valid OAuth token.
        user_id: Broadcaster user ID.
        start_date: Range start (inclusive).
        end_date: Range end (inclusive).
        logger: Optional logger.
    
    Returns:
        List of ArchivedVideo objects in range, newest first.
    
    Raises:
        ValueError: If start_date > end_date.
        VideosFetchError: On API errors.
    """
```

**Helper:**
```python
def _parse_rfc3339_to_date(timestamp: str) -> date:
    """Parse RFC3339 timestamp to date (handles timezone/Z suffix)."""
```

---

### Tray Controller - Multi-Fetch Orchestration

#### [MODIFY] [`tray_controller.py`](file:///c:/GoodVibez/automatic-twitch-markers/src/twitch_marker_agent/tray_controller.py)

**New Data Class:**
```python
@dataclass
class MultiFetchResult:
    """Result from multi-fetch operation."""
    success: bool
    message: str
    total_vods: int = 0
    successful_vods: int = 0
    skipped_vods: int = 0  # No markers found
    failed_vods: int = 0
    export_paths: list[Path] = field(default_factory=list)
```

**New Function:**
```python
def run_multi_fetch(
    http_client: requests.Session,
    config: AppConfig,
    state_store: StateStore,
    oauth: TwitchOAuth,
    output_dir: Path,
    export_formats: tuple[str, ...],
    start_date: date,
    end_date: date,
    logger: logging.Logger,
) -> MultiFetchResult:
    """
    Fetch and export markers from multiple VODs in date range.
    
    For each VOD:
    1. Fetch markers via video_id
    2. Export to configured formats
    3. Continue on individual failures
    
    Args:
        http_client: HTTP session.
        config: App config.
        state_store: State storage.
        oauth: OAuth client.
        output_dir: Export directory.
        export_formats: Formats (csv, edl).
        start_date: Range start (inclusive).
        end_date: Range end (inclusive).
        logger: Logger instance.
    
    Returns:
        MultiFetchResult with stats and paths.
    """
```

**Date Validation Helper:**
```python
def validate_date_range(
    start_date: date,
    end_date: date,
    max_days_back: int = 60,
) -> tuple[bool, str]:
    """
    Validate date range constraints.
    
    Rules:
    - start_date <= end_date
    - end_date <= today
    - start_date >= today - max_days_back
    
    Returns:
        (is_valid: bool, error_message: str)
    """
```

---

### Tray UI - Date Range Dialog

#### [NEW] [`ui/date_range_dialog.py`](file:///c:/GoodVibez/automatic-twitch-markers/src/twitch_marker_agent/ui/date_range_dialog.py)

**Purpose:** Tkinter dialog for date range selection.

**Main Class:**
```python
class DateRangeDialog:
    """Tkinter dialog for selecting date range."""
    
    def __init__(self, parent=None, max_days_back: int = 60):
        """Initialize with optional parent and max days constraint."""
        
    def show(self) -> tuple[date, date] | None:
        """
        Show dialog and wait for user input.
        
        Returns:
            (start_date, end_date) if OK clicked, None if cancelled.
        """
```

**Features:**
- Default: end_date=today, start_date=today-7
- Date pickers using tkinter built-in widgets (Entry + validation)
- Inline validation with error labels
- OK/Cancel buttons
- Validates on OK click, shows errors without closing dialog

#### [MODIFY] [`app.py`](file:///c:/GoodVibez/automatic-twitch-markers/src/twitch_marker_agent/app.py)

**New Menu Item:**
Add "Fetch Multiple Stream Markers" after "Fetch Latest Stream Markers":
```python
pystray.MenuItem(
    "Fetch Multiple Stream Markers",
    on_multi_fetch,
    enabled=is_not_fetching,
)
```

**New Callback:**
```python
def on_multi_fetch(icon, item):
    """Handle multi-fetch action with date range dialog."""
    # 1. Show date range dialog
    # 2. If cancelled, return
    # 3. Run multi-fetch in thread
    # 4. Update status, show notification
```

## Verification Plan

### Automated Tests

All tests use `unittest` + `unittest.mock`, no real network.

#### Test Module 1: [`tests/test_videos_api.py`](file:///c:/GoodVibez/automatic-twitch-markers/tests/test_videos_api.py)

**Tests:**
1. **`TestListVideosInDateRange`**
   - `test_empty_results` - API returns no data
   - `test_single_page_all_in_range` - All videos fit in range, single page
   - `test_pagination_multiple_pages` - Multiple pages, all in range
   - `test_early_stop_on_old_video` - Stops paging when video older than start_date
   - `test_filters_by_date_range` - Only returns videos in [start, end] inclusive
   - `test_api_error_raises` - HTTP 401/403/429/500 raise VideosFetchError
   
2. **`TestParseRFC3339ToDate`**
   - `test_with_z_suffix` - "2024-01-15T12:00:00Z" → date(2024, 1, 15)
   - `test_with_timezone_offset` - "2024-01-15T12:00:00+00:00" → date(2024, 1, 15)
   - `test_invalid_format_raises` - Malformed timestamp raises ValueError

**Run Command:**
```powershell
python -m unittest tests.test_videos_api -v
```

#### Test Module 2: [`tests/test_tray_controller_multi_fetch.py`](file:///c:/GoodVibez/automatic-twitch-markers/tests/test_tray_controller_multi_fetch.py)

**Tests:**
1. **`TestValidateDateRange`**
   - `test_valid_range` - start <= end, both within 60 days
   - `test_start_after_end_invalid` - start > end → invalid
   - `test_end_in_future_invalid` - end > today → invalid
   - `test_start_too_old_invalid` - start < today-60 → invalid
   - `test_boundary_cases_valid` - start=today-60, end=today → valid

2. **`TestRunMultiFetch`**
   - `test_no_vods_found` - Empty video list → success=True, 0 VODs message
   - `test_single_vod_with_markers` - Fetch + export 1 VOD successfully
   - `test_multiple_vods_all_succeed` - Fetch + export 3 VODs successfully
   - `test_one_vod_fails_continues` - VOD 2 fails markers fetch, continues to VOD 3
   - `test_vod_with_no_markers_skipped` - VOD has no markers, counts as skipped
   - `test_token_refresh_error` - OAuth fails → returns error result

**Run Command:**
```powershell
python -m unittest tests.test_tray_controller_multi_fetch -v
```

#### Test Module 3: [`tests/test_date_range_dialog.py`](file:///c:/GoodVibez/automatic-twitch-markers/tests/test_date_range_dialog.py)

**Tests:**
1. **`TestDateRangeDialog`**
   - `test_default_values` - end=today, start=today-7
   - `test_validation_start_after_end` - Shows error, dialog stays open
   - `test_validation_end_in_future` - Shows error, dialog stays open
   - `test_validation_start_too_old` - Shows error, dialog stays open
   - `test_cancel_returns_none` - Cancel button returns None
   - `test_ok_with_valid_range` - OK button returns (start, end)

**Note:** Tkinter UI tests are challenging to automate. Will use manual testing for UI verification.

**Run Command (unit tests for validation logic):**
```powershell
python -m unittest tests.test_date_range_dialog -v
```

### Manual Verification

1. **Date Range Dialog:**
   - Run tray app → "Fetch Multiple Stream Markers"
   - Verify default dates (end=today, start=today-7)
   - Test validation errors (start > end, future dates, > 60 days back)
   - Verify Cancel aborts cleanly
   - Verify OK with valid range proceeds

2. **Multi-Fetch Execution:**
   - Select range with 2-3 VODs
   - Verify: progress notification, all VODs exported, summary message
   - Check output folder for CSV/EDL files (one set per VOD)

3. **Error Handling:**
   - Select range with no VODs → friendly "no VODs found" message
   - Simulate 1 VOD with markers, 1 without → verify summary shows counts

### Full Test Suite

**Run Command:**
```powershell
python -m unittest discover -s tests -v
```

Expected: All existing tests + new tests pass (~320 total).

## Files Changed/Added

### New Files

1. **`src/twitch_marker_agent/core/videos_api.py`** (~250 lines)
   - ArchivedVideo dataclass
   - list_videos_in_date_range function
   - RFC3339 parsing helper
   - Unit tests: `tests/test_videos_api.py` (~200 lines)

2. **`src/twitch_marker_agent/ui/`** (new package)
   - **`src/twitch_marker_agent/ui/__init__.py`** (empty)
   - **`src/twitch_marker_agent/ui/date_range_dialog.py`** (~150 lines)
   - Unit tests: `tests/test_date_range_dialog.py` (~150 lines)

3. **`tests/test_tray_controller_multi_fetch.py`** (~300 lines)
   - Tests for validate_date_range
   - Tests for run_multi_fetch

### Modified Files

1. **`src/twitch_marker_agent/tray_controller.py`** (+~150 lines)
   - Add MultiFetchResult dataclass
   - Add validate_date_range function
   - Add run_multi_fetch function

2. **`src/twitch_marker_agent/app.py`** (+~50 lines)
   - Add "Fetch Multiple Stream Markers" menu item
   - Add on_multi_fetch callback
   - Import date_range_dialog

3. **`README.md`** (+~10 lines)
   - Document new menu item in tray features
   - Add note about 60-day limit and VOD retention

4. **`docs/tray_app.md`** (+~15 lines)
   - Describe multi-fetch feature
   - Explain date range constraints

## Dependencies

**No new dependencies required.**
- Using stdlib `tkinter` for date range dialog (included in Python stdlib)
- Using stdlib `datetime` for date handling
- All existing dependencies remain unchanged

## Compliance Checklist

✅ No secrets logged (tokens, client_secret, auth headers)
✅ No new dependencies (tkinter is stdlib)
✅ No config.json schema changes
✅ No StateStore public method signature changes
✅ core/ remains DI-friendly (videos_api.py follows pattern)
✅ Tests use unittest + unittest.mock only
✅ Minimal diffs, focused on new feature

---

## RUN 1 COMPLETE - AWAITING USER APPROVAL

**Next Steps:**
1. User reviews this plan
2. User replies with exact phrase: **"Proceed RUN 2"**
3. RUN 2: Implement all code + tests + docs
