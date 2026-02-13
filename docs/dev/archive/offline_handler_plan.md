# Stream Offline Handler Implementation Plan

**Goal:** Handle stream.offline EventSub notifications and trigger marker export.

**Status:** [DONE] RUN 2 Complete - Implementation Done

---

## Preflight Q&A

### 1) Where Will the Offline Handler Live?

**Current state:**
- `core/agent.py` - Stub orchestrator with `on_stream_offline(event_data)` method (raises NotImplementedError)
- `core/eventsub_ws.py` - Implemented. Delivers notifications via `asyncio.Queue[EventSubMessage]`

**Decision:** Create new module `core/offline_handler.py` for:
- Pure handler functions (testable without agent dependencies)
- `handle_stream_offline_notification()` - main entry point
- Agent.py will consume queue and delegate to this module

**Why separate module:**
- Keeps agent.py thin (orchestration only)
- Handler is pure function: no state, DI-friendly
- Easy to test without mocking async queue machinery

---

### 2) EventSub Message Shape

**Current delivery:** `EventSubMessage` dataclass from `eventsub_ws.py`

```python
@dataclass
class EventSubMessage:
    message_type: str  # "notification"
    payload: dict[str, Any]  # Contains subscription + event
    subscription_type: str | None  # "stream.offline"
    message_id: str | None  # For dedupe
```

**For stream.offline notification:**
```json
{
  "message_type": "notification",
  "subscription_type": "stream.offline",
  "message_id": "unique-id-123",
  "payload": {
    "subscription": {
      "type": "stream.offline",
      "condition": {"broadcaster_user_id": "12345"}
    },
    "event": {
      "broadcaster_user_id": "12345",
      "broadcaster_user_login": "username",
      "broadcaster_user_name": "Username"
    }
  }
}
```

**Key fields for dedupe:**
- `message_id` - unique per message
- `event.broadcaster_user_id` - for filtering

---

### 3) Marker Export Pipeline

**What exists:**
| Module | Status | Notes |
|--------|--------|-------|
| `markers_api.py` | [DONE] **IMPLEMENTED** | `get_stream_markers()`, `get_latest_video_id()` |
| `export_csv.py` | [DONE] **IMPLEMENTED** | `export_markers_csv()` works. |
| `config.output_dir` | Exists | Output directory from config. |

---

### 4) OAuth Scopes Readiness

**Current scope:** `channel:manage:broadcast`

**Required for Get Stream Markers:**
- `channel:manage:broadcast` [DONE] Included (also enables future broadcast management features)

**Twitch docs confirm:** Required scope is `user:read:broadcast` OR `channel:manage:broadcast`

**Verdict:** Scope is correctly configured and future-proofed.

---

### 5) Idempotency / Duplicates

**Problem:** EventSub is at-least-once; same stream.offline may arrive multiple times.

**Dedupe strategy (two-layer):**

| Layer | Mechanism | Scope |
|-------|-----------|-------|
| **Message-level** | In-memory `set[message_id]` | Per session (cleared on restart) |
| **Video-level** | `StateStore.get_state("processed_video:{broadcaster_id}:{video_id}")` | Persistent across restarts |

**Implementation:**
1. Check message_id against in-memory set -> skip if seen
2. After fetching video_id, check StateStore -> skip if processed
3. After successful export, store `processed_video:{broadcaster_id}:{video_id}` = timestamp

**No StateStore schema changes:** Just new key pattern.

---

### 6) Eventual Consistency / Retry Strategy

**Problem:** After stream.offline, VOD markers may not be immediately available.

**Retry strategy:**

| Status | Action |
|--------|--------|
| 200 OK | Success, export markers |
| 404 Not Found | Retry (VOD not ready) |
| 429 Rate Limited | Retry with backoff |
| 401 Unauthorized | Abort, raise auth error |
| Other 4xx/5xx | Abort, log error |

**Backoff schedule:**
- Initial delay: 5 seconds
- Max delay: 60 seconds
- Max attempts: 6 (~2.5 minutes total window)
- Backoff: exponential with jitter

**Uses:** `core/retry.py` `retry_with_backoff` (sync)

---

## Implementation Summary (RUN 2 Complete)

### Files Created/Modified

| File | Change |
|------|--------|
| `src/.../core/markers_api.py` | MODIFIED - implemented stubs |
| `src/.../core/offline_handler.py` | **NEW** - handler module |
| `src/.../core/twitch_oauth.py` | MODIFIED - scope fix |
| `tests/test_markers_api.py` | **NEW** - 16 tests |
| `tests/test_offline_handler.py` | **NEW** - 17 tests |
| `README.md` | Changelog v0.3.2 |
| `AGENTS.md` | Updated stub status |

### Test Results

```
Ran 166 tests in 2.666s
OK
```

---

### 7) Public API Proposal

```python
# === core/offline_handler.py ===

from dataclasses import dataclass
from pathlib import Path
from typing import Any

@dataclass
class MarkerExportResult:
    """Result of marker export operation."""
    video_id: str
    marker_count: int
    export_paths: list[Path]
    skipped: bool = False
    skip_reason: str | None = None

def should_handle_notification(
    message: EventSubMessage,
    expected_broadcaster_id: str,
    seen_message_ids: set[str],
) -> bool:
    """Check if notification should be processed."""
    ...

def handle_stream_offline(
    http_client: requests.Session,
    config: AppConfig,
    access_token: str,
    broadcaster_id: str,
    state_store: StateStore,
    logger: logging.Logger,
    seen_message_ids: set[str] | None = None,
) -> MarkerExportResult:
    """
    Handle stream.offline by fetching and exporting markers.
    
    1. Get latest video ID
    2. Check if already processed
    3. Fetch markers with retry
    4. Export to configured formats
    5. Mark as processed
    """
    ...

# === core/markers_api.py (implement stubs) ===

def get_stream_markers(...) -> list[MarkerVideo]:
    """Fetch stream markers from Helix API."""
    ...  # Implement the stub

def get_latest_video_id(...) -> str | None:
    """Get most recent VOD ID for user."""
    ...  # Implement the stub
```

---

### 8) Logging Policy

**Never log:**
- [NO] Tokens, auth headers
- [NO] Full response bodies
- [NO] Large payload JSON

**INFO level:**
- [DONE] "stream.offline received for broadcaster_id=X"
- [DONE] "Fetching markers for video_id=Y"
- [DONE] "Exported N markers to path/to/file.csv"
- [DONE] "Skipping duplicate video_id=Y (already processed)"

**DEBUG level:**
- [DONE] "Attempt 1/6: waiting for VOD markers..."
- [DONE] "Message message_id=abc already seen, skipping"

---

### 9) Test Strategy

**Test file:** `tests/test_offline_handler.py`

| Test | Description |
|------|-------------|
| `test_should_handle_ignores_non_offline` | Filters out non-stream.offline |
| `test_should_handle_ignores_wrong_broadcaster` | Filters by broadcaster_id |
| `test_should_handle_ignores_seen_message_id` | Dedupe by message_id |
| `test_handle_offline_success` | Full flow with mocked API |
| `test_handle_offline_retries_on_404` | Retry when VOD not ready |
| `test_handle_offline_skips_processed_video` | Dedupe by video_id |
| `test_handle_offline_exports_csv` | Verifies CSV export called |
| `test_handle_offline_marks_processed` | StateStore updated |
| `test_get_stream_markers_success` | Markers API mock 200 |
| `test_get_stream_markers_401_auth_error` | Auth error handling |
| `test_get_latest_video_id_success` | Videos API mock |
| `test_get_latest_video_id_empty` | No VODs case |

---

## Implementation Plan (RUN 2)

### Step 1: Implement markers_api.py stubs
- `get_stream_markers()` - GET /helix/streams/markers
- `get_latest_video_id()` - GET /helix/videos

### Step 2: Create offline_handler.py
- `MarkerExportResult` dataclass
- `should_handle_notification()` - filter/dedupe
- `handle_stream_offline()` - main flow with retry

### Step 3: Add exception classes
- `MarkersFetchError` in markers_api.py
- `MarkersAuthError` for 401

### Step 4: Unit Tests
- All tests from test plan above

### Step 5: Documentation
- Update README changelog
- Update AGENTS.md stub status

---

## Files Changed (RUN 2)

| File | Change |
|------|--------|
| `src/twitch_marker_agent/core/markers_api.py` | MODIFY - implement stubs |
| `src/twitch_marker_agent/core/offline_handler.py` | **NEW** - handler module |
| `tests/test_offline_handler.py` | **NEW** - tests |
| `tests/test_markers_api.py` | **NEW** - markers API tests |
| `README.md` | Update changelog |
| `AGENTS.md` | Update stub status |

---

## Out of Scope (This Step)

- [NO] Full agent.py orchestration wiring
- [NO] Tray app UI
- [NO] EDL export (CSV only for this step)
- [NO] Multiple broadcaster support
- [NO] Config schema changes
