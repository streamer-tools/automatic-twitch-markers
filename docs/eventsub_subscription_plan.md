# Helix EventSub Subscription Implementation Plan

**Goal:** Create EventSub subscription via Helix API after receiving session_id from WebSocket.

**Status:** ✅ RUN 2 Complete - Implementation Done

---

## ChatGPT 5.2 Review (Accepted Suggestions)

| # | Suggestion | Status |
|---|------------|--------|
| 1 | GET /eventsub/subscriptions filters are mutually exclusive (only ONE of type, user_id, status, subscription_id) | ✅ Accepted - use type filter, filter by broadcaster_id client-side |
| 2 | "Ensure" pattern must be fast due to Twitch "subscribe quickly" window after session_welcome | ✅ Accepted - keep list/delete/create tight |
| 3 | Condition may be dict OR JSON string in response - parse tolerantly | ✅ Accepted |
| 4 | DELETE endpoint uses query param `?id=<sub_id>`, not path segment | ✅ Accepted |

## Preflight Q&A

### 1) Current Repo State

**Where should Helix calls live?**
- `core/markers_api.py` exists but is for Get Stream Markers (different endpoint)
- No existing Helix subscriptions module
- The legacy `EventSubClient.subscribe_stream_offline()` stub exists in eventsub_ws.py but that's the deprecated class

**Decision:** Create new module `core/eventsub_subscriptions.py` for:
- Creating EventSub subscriptions (POST /eventsub/subscriptions)
- Future: listing/deleting subscriptions

This keeps concerns separated:
- `eventsub_ws.py` = WebSocket connection/messages
- `eventsub_subscriptions.py` = Helix API for subscription management
- `markers_api.py` = Helix API for markers

---

### 2) Subscription(s) to Create

**This step:** Create `stream.offline` subscription, version `1`

**Condition:**
```json
{"broadcaster_user_id": config.broadcaster_id}
```

**Why stream.offline:** The README states the agent detects when streams go offline to fetch markers. This is the subscription we need for the MVP.

---

### 3) Token Choice + OAuth Integration

**Confirmed:**
- `TwitchOAuth.get_valid_user_access_token(min_ttl_seconds=300)` returns valid token, auto-refreshes if near expiry
- Raises `TokenRefreshError` if not authenticated

**For WebSocket transport, Twitch requires:**
- A **user access token** (NOT app access token)
- For `stream.offline`, no special scope is required

**Token retrieval pattern:**
```python
access_token = oauth.get_valid_user_access_token(min_ttl_seconds=60)
```

Use short min_ttl (60s) since subscription creation is a quick operation.

---

### 4) API Contract Details

**Endpoint:** `POST https://api.twitch.tv/helix/eventsub/subscriptions`

**Headers:**
```
Authorization: Bearer <user_access_token>
Client-Id: <client_id>
Content-Type: application/json
```

**Request Body:**
```json
{
    "type": "stream.offline",
    "version": "1",
    "condition": {
        "broadcaster_user_id": "<broadcaster_id>"
    },
    "transport": {
        "method": "websocket",
        "session_id": "<session_id from session_welcome>"
    }
}
```

**Success:** HTTP 202 Accepted
```json
{
    "data": [{
        "id": "<subscription_id>",
        "status": "enabled",
        "type": "stream.offline",
        "version": "1",
        "condition": {...},
        "transport": {...},
        "created_at": "..."
    }],
    "total": 1,
    "total_cost": 1,
    "max_total_cost": 10
}
```

**Error Codes:**
- 400: Malformed request
- 401: Invalid/expired token
- 403: Forbidden (missing scopes for some subscription types, not stream.offline)
- 409: Duplicate subscription (already 3 with same type+condition)
- 429: Rate limited

---

### 5) Where Do We "Handle session_welcome"?

**Current state:** `EventSubWebSocketClient.connect()` returns session_id after receiving session_welcome.

**Decision:** We do NOT need a new hook/callback for welcome events. The caller (agent.py orchestrator) will:
1. Call `client.connect()` → get session_id
2. Call subscription creation with session_id
3. Call `client.run_until_stopped()`

This is simple and matches the README flow.

---

### 6) Duplicate Subscriptions / Idempotency

**Problem:** Twitch allows max 3 subscriptions with same type+condition. If we create on every startup without cleanup, we'll hit the limit.

**Options:**
- A) Fire-and-forget: Simple but hits limit after 3 restarts
- B) Ensure-subscription: List → check → create only if missing

**Recommendation:** **Option B - Ensure subscription pattern**

> [!IMPORTANT]
> **Mutually Exclusive Filters:** Twitch only allows ONE of: `type`, `user_id`, `status`, or `subscription_id` per request. Cannot combine them.

**Implementation:**
1. `GET /eventsub/subscriptions?type=stream.offline` (filter by type only)
2. **Client-side filter** by `condition.broadcaster_user_id == broadcaster_id`
3. Check for existing enabled websocket subscription
4. If found with matching session_id → skip (already subscribed)
5. If found with different/stale session_id → delete stale sub, create new
6. If none found → create new

> [!WARNING]
> **Timing Constraint:** Twitch expects subscription creation quickly after `session_welcome`. Keep the ensure flow tight: single list call, minimal deletes, then create immediately.

**Why:** 
- Avoids hitting duplicate limit on restarts
- Cleans up stale subscriptions from crashed sessions
- Slightly more API calls but robust

**Alternative (simpler):** Just try to create, catch 409 and proceed. This works but accumulates stale subs. 

**For THIS step:** Implement the ensure pattern. If time is critical in future, we can simplify.

---

### 7) Error Handling + Logging

**Never log:**
- Tokens, auth headers, or full response bodies

**Error handling:**
| Status | Behavior |
|--------|----------|
| 401 | Raise `SubscriptionAuthError("Token invalid. Run 'auth-login' to re-authenticate.")` |
| 403 | Log warning, raise `SubscriptionError("Forbidden - check token scopes")` |
| 409 | Log info "Subscription already exists", return existing sub if possible |
| 429 | Log warning, raise `SubscriptionRateLimitError` (caller can retry) |
| 4xx | Raise `SubscriptionError` with safe message |
| Network | Raise `SubscriptionError` wrapping original exception |

**Logging:**
- INFO: "Creating stream.offline subscription for broadcaster_id=<id>"
- INFO: "Subscription created: id=<first 8 chars of sub_id>..."
- DEBUG: Response status codes

---

### 8) Sync vs Async Boundary

**Problem:** `requests` is sync, EventSub WS is async.

**Current pattern in codebase:** OAuth uses sync `requests.Session`, injected via DI.

**Decision:** Keep subscription functions **sync** with `requests.Session` injection.

**Rationale:**
- Matches existing OAuth pattern
- Agent orchestrator (async) can call via `asyncio.to_thread(create_subscription, ...)`
- Keeps core simple and testable

---

### 9) Test Strategy

**Tests location:** `tests/test_eventsub_subscriptions.py`

**Pure helpers for easy testing:**
- `build_subscription_request(type, version, condition, session_id)` → dict
- `parse_subscription_response(response_data)` → Subscription dataclass

**Tests required:**

| Test | Description |
|------|-------------|
| `test_build_request_structure` | Verify request has type/version/condition/transport |
| `test_parse_condition_as_dict` | Condition as normal dict |
| `test_parse_condition_as_json_string` | Condition as JSON-encoded string (robustness) |
| `test_create_subscription_success` | Mock 202 response, verify returns Subscription |
| `test_create_subscription_401_raises_auth_error` | Clear reauth message |
| `test_create_subscription_409_duplicate` | Returns existing or safe exception |
| `test_create_subscription_403_forbidden` | Safe exception |
| `test_create_subscription_429_rate_limit` | Rate limit exception |
| `test_list_subscriptions` | Mock GET, verify parsing |
| `test_list_subscriptions_rejects_multiple_filters` | Raises ValueError if type AND user_id passed |
| `test_delete_subscription` | Mock DELETE 204, verify no error |
| `test_ensure_subscription_creates_if_none` | List empty → create called |
| `test_ensure_subscription_skips_if_exists` | List has matching → skip |
| `test_ensure_subscription_deletes_stale` | List has stale → delete + create |

---

## Proposed Public API

```python
from dataclasses import dataclass
from typing import Any
import logging
import requests

# === Exceptions ===

class SubscriptionError(Exception):
    """Base exception for subscription operations."""
    pass

class SubscriptionAuthError(SubscriptionError):
    """Raised when authentication fails (401)."""
    pass

class SubscriptionRateLimitError(SubscriptionError):
    """Raised when rate limited (429)."""
    pass

# === Data Classes ===

@dataclass
class Subscription:
    """Represents an EventSub subscription."""
    id: str
    status: str  # "enabled", "webhook_callback_verification_pending", etc.
    type: str  # "stream.offline"
    version: str
    condition: dict[str, Any]
    transport_method: str  # "websocket" or "webhook"
    transport_session_id: str | None  # for websocket
    created_at: str

# === Pure Helpers ===

def build_subscription_request(
    sub_type: str,
    version: str,
    condition: dict[str, Any],
    session_id: str,
) -> dict[str, Any]:
    """Build request body for EventSub subscription creation."""
    ...

def parse_subscription_response(data: dict[str, Any]) -> Subscription:
    """
    Parse subscription data from Helix response.
    
    Handles condition as either dict or JSON-encoded string.
    """
    ...

# === Main Functions ===

def create_eventsub_subscription(
    http_client: requests.Session,
    client_id: str,
    access_token: str,
    sub_type: str,
    version: str,
    condition: dict[str, Any],
    session_id: str,
    logger: logging.Logger,
) -> Subscription:
    """
    Create an EventSub subscription via Helix API.
    
    Raises:
        SubscriptionAuthError: If token is invalid (401).
        SubscriptionRateLimitError: If rate limited (429).
        SubscriptionError: For other failures.
    """
    ...

def list_eventsub_subscriptions(
    http_client: requests.Session,
    client_id: str,
    access_token: str,
    sub_type: str | None = None,
    user_id: str | None = None,
    logger: logging.Logger | None = None,
) -> list[Subscription]:
    """List EventSub subscriptions with optional filters."""
    ...

def delete_eventsub_subscription(
    http_client: requests.Session,
    client_id: str,
    access_token: str,
    subscription_id: str,
    logger: logging.Logger | None = None,
) -> None:
    """
    Delete an EventSub subscription by ID.
    
    Uses: DELETE /eventsub/subscriptions?id=<subscription_id>
    """
    ...

def ensure_stream_offline_subscription(
    http_client: requests.Session,
    client_id: str,
    access_token: str,
    broadcaster_id: str,
    session_id: str,
    logger: logging.Logger,
) -> Subscription:
    """
    Ensure a stream.offline subscription exists for the broadcaster.
    
    - Lists existing subscriptions
    - Deletes stale websocket subscriptions for same broadcaster
    - Creates new if none exists
    """
    ...
```

---

## Implementation Plan (RUN 2)

### Step 1: Create Module Structure
- New file: `src/twitch_marker_agent/core/eventsub_subscriptions.py`
- Add exceptions: `SubscriptionError`, `SubscriptionAuthError`, `SubscriptionRateLimitError`
- Add `Subscription` dataclass

### Step 2: Pure Helper Functions
- `build_subscription_request()` - build JSON body
- `parse_subscription_response()` - parse response to Subscription

### Step 3: create_eventsub_subscription()
- POST to Helix endpoint
- Handle 202 success
- Handle 401/403/409/429 errors
- Return Subscription

### Step 4: list_eventsub_subscriptions()
- GET with ONE query param only (type OR user_id, not both)
- Raise ValueError if caller passes multiple filters
- Filter by broadcaster_id client-side
- Parse response array
- Handle pagination if needed (first page should suffice for MVP)

### Step 5: delete_eventsub_subscription()
- DELETE using query param `?id=<subscription_id>`
- Handle 204 success, errors

### Step 6: ensure_stream_offline_subscription()
- Orchestrate list → delete stale → create
- Log actions

### Step 7: Remove Legacy Stub
- Remove `subscribe_stream_offline` from deprecated `EventSubClient` class
- Or leave as stub with deprecation warning

### Step 8: Unit Tests
- All tests from test plan above

---

## Files Changed (RUN 2)

| File | Change |
|------|--------|
| `src/twitch_marker_agent/core/eventsub_subscriptions.py` | NEW - subscription management |
| `tests/test_eventsub_subscriptions.py` | NEW - tests (11+) |
| `src/twitch_marker_agent/core/eventsub_ws.py` | OPTIONAL - remove legacy stub |
| `README.md` | Update changelog |
| `AGENTS.md` | Update stub status |
| `docs/eventsub_implementation_plan.md` | Update this file status |

---

## Out of Scope (This Step)

- ❌ stream.offline event handling (next step)
- ❌ Agent orchestration wiring
- ❌ Get Stream Markers API
- ❌ New dependencies
- ❌ Config schema changes
