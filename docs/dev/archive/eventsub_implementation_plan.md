# EventSub WebSocket Implementation Plan

**Goal:** Connect to Twitch EventSub WebSocket and handle message types.

**Status:** [DONE] RUN 2 Complete - Implementation Done

---

## ChatGPT 5.2 Review (Accepted Suggestions)

| # | Suggestion | Status |
|---|------------|--------|
| 1 | Use `ping_interval=None` in `websockets.connect()` - Twitch closes connection on client messages other than Pong | [DONE] Accepted |
| 2 | Don't assume session_id stays same on reconnect - update from new Welcome | [DONE] Accepted |
| 3 | Keepalive timeout = subscription deadline - log warning that caller must subscribe quickly | [DONE] Accepted |
| 4 | `asyncio.Queue` is async-friendly within loop, not thread-safe - fix wording | [DONE] Accepted |
| 5 | Use `wait_for(ws.recv())` pattern instead of `async for` - easier shutdown/testing | [DONE] Accepted |

---

## Preflight Q&A

### 1) Current State of eventsub_ws.py

**Status:** Stubbed with existing structure to preserve.

**Existing components:**
- `EVENTSUB_WS_URL = "wss://eventsub.wss.twitch.tv/ws"`
- `EventSubMessage` dataclass (message_type, payload, subscription_type)
- `EventSubClient` class with stubbed methods:
  - `connect()` -> raises NotImplementedError
  - `subscribe_stream_offline()` -> raises NotImplementedError (OUT OF SCOPE)
  - `run()` -> raises NotImplementedError
  - `shutdown()` -> raises NotImplementedError
  - `_parse_message()` -> partially implemented (JSON parse + extract metadata)

**Decision:** Preserve `EventSubMessage` dataclass. Rename class to `EventSubWebSocketClient` for clarity. Keep `subscribe_stream_offline` stubbed (next README step).

---

### 2) Current Usage

**Search results:** No imports of `eventsub_ws` found in `src/`.

**Agent.py status:** Has `self._eventsub_client: Any = None` placeholder. Will be wired in future agent orchestration step.

**Decision:** Safe to refactor without breaking any imports.

---

### 3) Async API Design

**Question:** Async-only or sync wrapper?

**Recommendation:** **Async-only** for this step.

**Rationale:**
- `websockets` library is async-native; forcing sync would require complex threading
- Future Windows tray app can run an asyncio event loop in a background thread
- Core should stay simple and let entry points (cli.py, app.py) handle async-to-sync bridging
- Matches AGENTS.md: "core/ remains framework-agnostic"

**Consumer pattern:** Use `asyncio.Queue` for notifications (async-friendly within the event loop; thread bridging is entry point responsibility).

---

### 4) Proposed Public API

```python
from dataclasses import dataclass
from typing import Callable, Awaitable, Any
import asyncio
import logging

@dataclass
class EventSubMessage:
    """Parsed EventSub WebSocket message."""
    message_type: str  # session_welcome, session_keepalive, notification, session_reconnect, revocation
    payload: dict[str, Any]
    subscription_type: str | None = None
    message_id: str | None = None

class EventSubWebSocketClient:
    """EventSub WebSocket client for receiving Twitch events."""
    
    def __init__(
        self,
        logger: logging.Logger,
        notification_queue: asyncio.Queue[EventSubMessage] | None = None,
        on_revocation: Callable[[EventSubMessage], Awaitable[None]] | None = None,
    ) -> None: ...
    
    # === Properties ===
    @property
    def session_id(self) -> str | None: ...
    
    @property
    def keepalive_timeout_seconds(self) -> int | None: ...
    
    @property
    def is_connected(self) -> bool: ...
    
    # === Main API ===
    async def connect(self, url: str = EVENTSUB_WS_URL) -> str:
        """Connect and return session_id from welcome message."""
        ...
    
    async def run_until_stopped(self) -> None:
        """Main message loop. Blocks until stop() is called or connection lost."""
        ...
    
    async def stop(self) -> None:
        """Signal graceful shutdown."""
        ...
    
    async def close(self) -> None:
        """Close websocket connection."""
        ...

# === Pure Helpers (for testing) ===
def parse_eventsub_message(raw_json: str) -> EventSubMessage: ...
def classify_message_type(message: EventSubMessage) -> str: ...
```

**Consumer receives notifications via:**
- `notification_queue` (async queue) - notifications pushed here
- `on_revocation` callback - called when subscription revoked

**Session ID retrieval:**
- `client.session_id` property after `connect()` returns

---

### 5) Internal State

| State | Type | Purpose |
|-------|------|---------|
| `_session_id` | `str \| None` | From session_welcome |
| `_keepalive_timeout_seconds` | `int \| None` | From session_welcome |
| `_last_message_at` | `datetime \| None` | Updated on any message |
| `_reconnect_url` | `str \| None` | From session_reconnect |
| `_ws` | `WebSocketClientProtocol \| None` | Active websocket |
| `_ws_url` | `str` | Current URL (initial or reconnect) |
| `_stop_event` | `asyncio.Event` | Signals shutdown |
| `_is_running` | `bool` | Loop active flag |

---

### 6) Stop/Shutdown Strategy

**Problem:** WebSocket recv() blocks indefinitely.

**Solution:**
1. `stop()` sets `_stop_event`
2. `run_until_stopped()` uses `asyncio.wait_for()` or `asyncio.wait()` with timeout
3. Check `_stop_event.is_set()` periodically (after each message or timeout)
4. `close()` calls `ws.close()` with normal close code (1000)

**Graceful shutdown sequence:**
```python
async def stop(self) -> None:
    self._stop_event.set()

async def close(self) -> None:
    if self._ws:
        await self._ws.close(code=1000)
        self._ws = None
    self._session_id = None
```

---

### 7) Reconnection Strategy

**session_reconnect handling:**
1. Store `reconnect_url` from message
2. Open NEW connection to `reconnect_url`
3. Wait for new `session_welcome`
4. **Update `_session_id`** from new Welcome (do NOT assume it stays the same)
5. Close OLD connection only AFTER new Welcome received
6. Continue message loop on new connection

**Unexpected disconnect handling (minimal):**
- Log error and exit `run_until_stopped()`
- Let caller (agent.py) decide retry logic with exponential backoff
- No automatic retry in this module (avoids complexity creep)

---

### 8) Logging Policy

**INFO level (safe to log):**
- "Connected to EventSub WebSocket"
- "Received session_welcome, session_id=<first 8 chars>..."
- "Keepalive timeout: {n} seconds"
- "Received notification: {subscription_type}"
- "Reconnect requested, connecting to new URL"
- "Connection closed: {code}"
- "Shutting down EventSub client"

**DEBUG level:**
- Message types received
- Last message timestamp updates
- Full message structure (without sensitive data)

**NEVER log:**
- Access tokens (not used in WS messages, but reminder)
- Full message payloads at INFO
- Any auth headers

---

### 9) Testing Strategy

**Pure helpers for unit testing:**
- `parse_eventsub_message(raw_json)` - JSON -> EventSubMessage
- `classify_message_type(message)` - returns type string

**Mocking websockets:**
```python
# Mock websockets.connect as async context manager
mock_ws = AsyncMock()
mock_ws.__aiter__.return_value = iter([message1, message2])
mock_ws.close = AsyncMock()

with patch("websockets.connect", return_value=async_context_manager(mock_ws)):
    ...
```

**Minimum tests for RUN 2:**

| Test | Description |
|------|-------------|
| `test_parse_welcome_extracts_session_id` | Parse session_welcome, verify session_id |
| `test_parse_welcome_extracts_keepalive_timeout` | Verify keepalive_timeout_seconds |
| `test_parse_keepalive_message` | Verify message_type = session_keepalive |
| `test_parse_notification_extracts_type` | Verify subscription_type extracted |
| `test_parse_reconnect_extracts_url` | Verify reconnect_url from payload |
| `test_notification_pushed_to_queue` | Mock ws, verify queue.get() returns notification |
| `test_revocation_calls_callback` | Mock ws with revocation, verify callback called |
| `test_stop_sets_event` | Verify stop() sets _stop_event |
| `test_close_closes_websocket` | Verify ws.close() called |
| `test_classify_message_type` | Unit test for type classification |

---

## Implementation Plan (RUN 2)

### Step 1: Pure Helper Functions
- `parse_eventsub_message(raw_json: str) -> EventSubMessage`
- `classify_message_type(message: EventSubMessage) -> str`

### Step 2: EventSubWebSocketClient Class
- Constructor with DI (logger, notification_queue, on_revocation callback)
- Internal state initialization
- Properties: session_id, keepalive_timeout_seconds, is_connected

### Step 3: connect() Method
- Connect to EVENTSUB_WS_URL using `websockets.connect(ping_interval=None)`
  - **Important:** `ping_interval=None` disables client pings (Twitch closes on client messages other than Pong)
- Wait for first message using `asyncio.wait_for(ws.recv(), timeout=...)`
- Parse as session_welcome
- Store session_id and keepalive_timeout_seconds
- Log warning: "Caller must create subscription within {keepalive_timeout_seconds}s or server may close (code 4003)"
- Return session_id

### Step 4: run_until_stopped() Message Loop
- Loop while not stopped
- Receive message using `asyncio.wait_for(ws.recv(), timeout=keepalive_timeout + buffer)`
  - **Note:** Use `wait_for` pattern (not `async for`) for easier shutdown/reconnect testing
- Parse and classify message
- Handle each type:
  - session_keepalive: update last_message_at
  - notification: push to queue
  - session_reconnect: store reconnect_url, trigger reconnect (update session_id from new Welcome)
  - revocation: call on_revocation callback
- On disconnect: log and exit loop
- On timeout (no message for > keepalive_timeout): assume connection lost, log and exit loop

### Step 5: stop() and close() Methods
- stop(): set _stop_event
- close(): close websocket, clear state

### Step 6: Unit Tests
- All tests from test plan above
- Use AsyncMock and patch for websockets

---

## Files Changed (RUN 2)

| File | Change |
|------|--------|
| `src/twitch_marker_agent/core/eventsub_ws.py` | Implement full WebSocket client |
| `tests/test_eventsub_ws.py` | New test file (10+ tests) |
| `docs/eventsub_implementation_plan.md` | This file (update status) |

---

## Out of Scope (This Step)

- [NO] Helix subscription creation (subscribe_stream_offline stays stubbed)
- [NO] stream.offline event handling
- [NO] Agent orchestration wiring
- [NO] Automatic retry with backoff (caller responsibility)
- [NO] Config schema changes
- [NO] New dependencies
