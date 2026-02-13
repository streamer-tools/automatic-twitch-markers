# Twitch OAuth Implementation Plan

Complete OAuth implementation including login flow (Phase B) and token maintenance (Phase C).

---

## Overview

**Goal:** Full OAuth lifecycle: browser login, token storage, refresh, validation, and expiry-aware access.

**Status:** [DONE] Phase B (login) + Phase C (token maintenance) complete.

**Files:**
- `src/twitch_marker_agent/core/twitch_oauth.py` (implemented)
- `src/twitch_marker_agent/cli.py` (`auth-login` command)
- `tests/test_twitch_oauth.py` (80 tests)

---

## Phase A Preflight Q&A

### 1) Test Strategy (No Port Binding)
Factor pure helper functions for unit testing without network/port:
- `build_authorize_url(client_id, redirect_uri, scopes, state)` -> URL string
- `parse_redirect_uri(uri)` -> `(host, port, path)` tuple
- `compute_expires_at(expires_in_seconds)` -> UTC ISO8601 string
- `_validate_callback_params(params, expected_state)` -> code or raises

### 2) Callback Handling + Shutdown
1. `threading.Thread` runs `HTTPServer.serve_forever()`
2. Shared `dict` + `threading.Event` for result signaling
3. Handler writes result to container, sets event
4. Main thread waits via `event.wait(timeout=timeout_seconds)`
5. After event/timeout: `server.shutdown()` from main thread
6. Join thread, then `server.server_close()` to release socket
7. All wrapped in `try/finally` for guaranteed cleanup

### 3) Timeout Behavior
- Hard timeout: 120 seconds (configurable)
- Exception: `OAuthTimeoutError`
- CLI message: `"OAuth login timed out after 120 seconds. Please try again."`

### 4) CSRF Protection
- Generate: `secrets.token_urlsafe(32)`
- Store: local variable during `interactive_login()` call
- Validate: compare callback `state` to stored value
- On mismatch: raise `OAuthCancelledError("State mismatch - possible CSRF attack.")`

### 5) Logging Policy
**Never log:** access_token, refresh_token, client_secret, response bodies

**On failure, log only:**
```python
logger.error(f"Token exchange failed: HTTP {status_code}")
logger.error(f"Token exchange failed: {error} - {error_description}")
```

### 6) Browser Open Behavior
- Use `webbrowser.open(authorize_url)` (stdlib, Windows-compatible)
- On failure: print URL for manual copy, server still waits

### 7) Port Already In Use
- Detect via `OSError` when binding
- Message: `"Port 3000 is already in use. Close other apps using it or change redirect_uri."`
- Raise `OAuthCancelledError`

### 8) Refresh Token Rotation Safety
- **Phase B (exchange):** Store refresh_token only if present
- **Future refresh:** Only overwrite if new value returned; never overwrite with None

---

## Recommended Changes Review

| # | Change | Decision | Rationale |
|---|--------|----------|-----------|
| 1 | Keep `TwitchOAuth` name | [DONE] Agree | Avoids breaking existing imports |
| 2 | Explicit DI constructor | [DONE] Agree | Testable, consistent with AGENTS.md |
| 3 | Pure state validation helper | [DONE] Agree | Unit-testable without port binding |
| 4 | Timezone-aware UTC ISO8601 | [DONE] Agree | Prevents datetime comparison bugs |
| 5 | Bind `127.0.0.1` + `allow_reuse_address` | [DONE] Agree | Safer + reduces port-stuck on Windows |
| 6 | Defensive refresh_token storage | [DONE] Agree | Never overwrite with None |
| 7 | Repo-relative paths only | [DONE] Agree | Portable documentation |

---

## Technical Design

### Constructor (DI-friendly)
```python
def __init__(
    self,
    config: AppConfig,
    state_store: StateStore,
    logger: logging.Logger,
    http_session: requests.Session | None = None,
    browser_opener: Callable[[str], bool] | None = None,
) -> None:
```

### Custom Exceptions
```python
class OAuthCancelledError(Exception): ...  # user cancelled / state mismatch / port in use
class OAuthTimeoutError(Exception): ...    # callback not received in time
class TokenExchangeError(Exception): ...   # token endpoint error
```

### Callback Server (allow_reuse_address before bind)
```python
class _ReusableHTTPServer(HTTPServer):
    allow_reuse_address = True  # Set as class attribute before __init__ binds
```
Server binds to `127.0.0.1` on port parsed from `config.redirect_uri`.

### Redirect URI Parsing
Parse `config.redirect_uri` (e.g., `http://localhost:3000/callback`) to extract:
- host: `localhost` -> bind `127.0.0.1`
- port: `3000`
- path: `/callback`

Same URI used in authorize URL and token exchange POST (exact match required by Twitch).

### Token Storage Keys
- `twitch_access_token`
- `twitch_refresh_token` (only if present)
- `twitch_token_expires_at` (UTC ISO8601 with timezone)

### Token Expiry Format
```python
from datetime import datetime, timezone, timedelta
expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
expires_at_str = expires_at.isoformat()  # "2026-02-02T21:30:00.123456+00:00"
```

---

## Fixes Required for Phase B

| # | Fix |
|---|-----|
| 1 | Keep class name `TwitchOAuth` |
| 2 | Explicit DI constructor with optional `http_session`, `browser_opener` |
| 3 | Subclass `HTTPServer` with `allow_reuse_address = True` (set before bind) |
| 4 | Parse `config.redirect_uri` for server host/port/path |
| 5 | Use same `redirect_uri` in authorize URL and token exchange |
| 6 | Request timeouts: `timeout=(10, 30)` |
| 7 | `try/finally` with `server.shutdown()` + `server.server_close()` |
| 8 | Hard timeout via `threading.Event.wait(timeout=timeout_seconds)` |
| 9 | Secret-safe logging: never log tokens or response bodies |
| 10 | State generation: `secrets.token_urlsafe(32)` |
| 11 | Pure helper `_validate_callback_params()` for unit testing |
| 12 | Browser fallback: print URL if `browser_opener()` fails |
| 13 | Port-in-use: catch `OSError`, raise `OAuthCancelledError` |
| 14 | Store refresh_token only if present |
| 15 | Timezone-aware expiry: `datetime.now(timezone.utc).isoformat()` |
| 16 | Token exchange: `grant_type=authorization_code`, form-encoded |

---

## Phase B Scope

### Implemented Methods (Phase B)
- `build_authorize_url(scopes: list[str]) -> str`
- `interactive_login(timeout_seconds: int = 120) -> None`

### Implemented Methods (Phase C)
- `refresh_access_token() -> None`
- `validate_access_token(token: str) -> dict | None`
- `get_valid_user_access_token(min_ttl_seconds: int = 300) -> str`

### CLI Command
```powershell
python -m twitch_marker_agent.cli auth-login [-c config.json]
```

---

## Test Plan

| Test | What It Verifies |
|------|------------------|
| `test_build_authorize_url_contains_all_params` | URL has client_id, redirect_uri, response_type, scope, state |
| `test_build_authorize_url_scope_format` | Scopes are space-separated |
| `test_parse_redirect_uri` | Correctly extracts host, port, path |
| `test_compute_expires_at_format` | Returns timezone-aware UTC ISO8601 |
| `test_validate_callback_params_success` | Returns code when state matches |
| `test_validate_callback_params_state_mismatch` | Raises OAuthCancelledError |
| `test_validate_callback_params_error` | Raises OAuthCancelledError on error param |
| `test_exchange_code_mocked` | Mock session, verify POST body |
| `test_exchange_code_stores_tokens` | Tokens written to StateStore |

---

## Verification

```powershell
python -m unittest discover -s tests -v
python -m twitch_marker_agent.cli auth-login --help
python -c "from twitch_marker_agent.core.twitch_oauth import TwitchOAuth"
```

---

## Phase C: Token Maintenance

**Goal:** Implement token refresh, validation, and automatic token retrieval.

**Scope:** 
- `refresh_access_token()`
- `validate_access_token(token)`
- `get_valid_user_access_token(min_ttl_seconds)`

**NOT in scope:** EventSub, Helix markers, agent scheduling, new CLI commands.

---

### Phase C Preflight Q&A

#### 1) Public API / Behavior

| Method | Returns | Exceptions |
|--------|---------|------------|
| `refresh_access_token()` | `None` (stores tokens internally) | `TokenRefreshError` on HTTP error or missing refresh token |
| `validate_access_token(token)` | `dict` on 200, `None` on 401 | No exception on 401; raises on network error |
| `get_valid_user_access_token(min_ttl_seconds)` | `str` (access token) | `TokenRefreshError` if no refresh token ("Run auth-login") |

**Behavior when not authenticated:**
`get_valid_user_access_token()` raises `TokenRefreshError` with message:
`"No refresh token available. Run 'auth-login' to authenticate."`

#### 2) Refresh Request Contract

```python
data = {
    "grant_type": "refresh_token",
    "refresh_token": stored_refresh_token,
    "client_id": config.client_id,
    "client_secret": config.client_secret,
}
response = session.post(TWITCH_TOKEN_URL, data=data, timeout=HTTP_TIMEOUT)
```

- Form-encoded (`data=`), not JSON
- Timeout: `(10, 30)` tuple (same as Phase B)

#### 3) Refresh Token Rotation Safety

```python
new_refresh = response_data.get("refresh_token")
if new_refresh:  # Only store if present
    self._state_store.store_token(self.TOKEN_KEY_REFRESH, new_refresh)
# If missing: do nothing -> existing refresh token preserved
```

**Rule:** Never call `store_token(KEY_REFRESH, None)`.

#### 4) Validation Semantics

| HTTP Status | Return Value | Exception |
|-------------|--------------|-----------|
| 200 | Parsed JSON dict (includes `expires_in`, `login`, etc.) | -- |
| 401 | `None` | -- |
| Other (5xx, network) | -- | `requests.RequestException` propagates |

**Validate call frequency:**
`get_valid_user_access_token()` does NOT call validate on every call.
Instead, it uses stored `expires_at` timestamp to decide if refresh is needed.
Validate is optional for debugging or explicit verification.

#### 5) Expiry Tracking

**Computation (same as Phase B):**
```python
expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
expires_at_str = expires_at.isoformat()  # "2026-02-02T23:30:00.123456+00:00"
```

**Updates:**
- `refresh_access_token()` -> updates `twitch_token_expires_at` from refresh response
- `validate_access_token()` -> does NOT update stored expiry (read-only check)

#### 6) Near-Expiry Policy

| min_ttl_seconds | Behavior |
|-----------------|----------|
| Default: 300 (5 minutes) | Refresh if `ttl <= min_ttl_seconds` |
| When expired or missing | Refresh immediately |

**Rationale:** 5 minutes gives buffer for API calls during a stream.

**Logic:**
```python
if expires_at is None or now >= expires_at:
    refresh()
elif (expires_at - now).total_seconds() <= min_ttl_seconds:
    refresh()
else:
    return cached_access_token
```

#### 7) Concurrency Safety

**Uses re-entrant lock (RLock):**
```python
self._refresh_lock = threading.RLock()
```

**Why RLock:** `get_valid_user_access_token()` acquires the lock and calls `refresh_access_token()`, which also acquires the lock. RLock allows re-entry from the same thread, preventing deadlock.

**Usage:**
```python
# In refresh_access_token():
with self._refresh_lock:
    self._refresh_access_token_unlocked()

# In get_valid_user_access_token():
with self._refresh_lock:
    # double-check pattern: re-evaluate if refresh still needed
    if still_needs_refresh:
        self.refresh_access_token()  # RLock allows re-entry
```

**Testing:** 
Test logic without real threads by mocking. The lock prevents race conditions in production but unit tests verify single-threaded behavior.

#### 8) Unit Test Plan

| Test | Description |
|------|-------------|
| `test_refresh_success_stores_access_token` | Mock 200, verify access_token stored |
| `test_refresh_success_stores_expires_at` | Verify expires_at computed and stored |
| `test_refresh_rotates_refresh_token` | Response includes new refresh_token -> stored |
| `test_refresh_preserves_refresh_token_if_omitted` | Response omits refresh_token -> old value kept |
| `test_refresh_401_raises_error` | Mock 401 -> raises TokenRefreshError |
| `test_refresh_no_stored_token_raises` | No refresh_token in store -> raises with "auth-login" message |
| `test_validate_200_returns_dict` | Mock 200 -> returns parsed JSON |
| `test_validate_401_returns_none` | Mock 401 -> returns None (no exception) |
| `test_get_valid_token_returns_cached_when_fresh` | expires_at far future -> returns cached, no HTTP |
| `test_get_valid_token_refreshes_when_near_expiry` | expires_at soon -> calls refresh, returns new token |
| `test_get_valid_token_refreshes_when_expired` | expires_at past -> calls refresh |
| `test_get_valid_token_raises_when_no_tokens` | No tokens stored -> raises with "auth-login" message |

---

### Fixes Required for Phase C

| # | Fix |
|---|-----|
| 1 | Add `threading.Lock` for refresh concurrency safety |
| 2 | `refresh_access_token()` returns `None`, stores internally |
| 3 | Secret-safe logging: log only status code + error/error_description |
| 4 | Defensive refresh_token storage: only store if response includes it |
| 5 | Request timeout: `timeout=HTTP_TIMEOUT` (10, 30) |
| 6 | Parse expires_at with `datetime.fromisoformat()` for comparison |
| 7 | Default `min_ttl_seconds=300` (5 minutes) |
| 8 | Clear error message when not authenticated: "Run auth-login" |
| 9 | `validate_access_token()` returns `None` on 401 (no exception) |
| 10 | Use `Authorization: OAuth <token>` header for validate endpoint |

---

### Phase C Verification

```powershell
python -m unittest discover -s tests -v
python -c "from twitch_marker_agent.core.twitch_oauth import TwitchOAuth"
```

---

### Phase C Implementation Results

**Status:** [DONE] Complete (with Phase C Patch)

**Changes Made:**

1. **`refresh_access_token()`** - POST to token endpoint with `grant_type=refresh_token`, stores new access_token/expires_at, rotates refresh_token only if response includes one. Concurrency-safe (uses RLock).

2. **`validate_access_token(token)`** - GET to validate endpoint with `Authorization: OAuth <token>` header, returns dict on 200, None on 401.

3. **`get_valid_user_access_token(min_ttl_seconds=300)`** - Returns cached token if fresh, refreshes if TTL <= min_ttl_seconds or expired/invalid, raises TokenRefreshError if not authenticated.

4. **Concurrency** - Uses `threading.RLock()` (re-entrant) so both direct calls to `refresh_access_token()` and calls via `get_valid_user_access_token()` are safe from concurrent refreshes or deadlock.

5. **Expiry hardening** - Handles missing, invalid, or naive datetime gracefully (treats as expired).

**Tests:**
- `TestRefreshAccessToken` (8 tests including payload + timeout verification)
- `TestValidateAccessToken` (3 tests)  
- `TestGetValidUserAccessToken` (8 tests)

**Total Tests:** 80
