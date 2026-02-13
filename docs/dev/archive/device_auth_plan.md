# Device Code Flow Authentication Implementation Plan

Add end-user Twitch authentication to the Windows tray app using OAuth Device Code Flow (public client, no client_secret shipped).

## Preflight Questions (with Proposed Defaults)

### 1. Scopes
**Question:** Request minimal scope for markers only (`channel:read:broadcast`) or broader (`channel:manage:broadcast`)?

**Default:** Use `channel:manage:broadcast` (already used by existing OAuth flow in `twitch_oauth.py:41`). This scope is required for Get Stream Markers API and future broadcast management features.

---

### 2. UX: Duplicate Auth Prevention
**Question:** Should "Authenticate with Twitch..." be disabled while auth is pending?

**Default:** Yes. Lock out duplicate auth attempts by:
- Disabling menu item while dialog is open
- Showing status "Auth pending..." in menu
- Only one auth flow can run at a time

---

### 3. "Connected as ..." Display Location
**Question:** Where should the connected status appear?

**Default:** A disabled menu item at the top of the tray menu:
```
------------------------
[OK] Connected as lirik
------------------------
    OR
------------------------
[WARN] Not authenticated
------------------------
```

---

### 4. Client ID Sourcing
**Question:** How should client_id be provided for desktop DCF auth?

**Default:**
1. Use `config.client_id` if present (existing behavior)
2. Allow env var override: `TWITCH_MARKER_AGENT_CLIENT_ID`
3. Optionally embed a `DEFAULT_CLIENT_ID` constant for distribution builds

> [!NOTE]
> `client_id` is NOT secret and can be safely embedded. No config schema changes needed.

---

### 5. Failure Behavior on Invalid Refresh Token
**Question:** If refresh fails due to expired/invalid refresh token, should we auto-prompt re-auth?

**Default:**
- Flip to unauthenticated state (clear invalid tokens)
- Show tray notification: "Session expired. Authenticate with Twitch..."
- Update menu to show "Not authenticated" status
- Do NOT auto-open auth dialog (let user initiate)

---

## Proposed Changes

### Core Module: Device Auth

#### [NEW] [device_auth.py](file:///c:/GoodVibez/automatic-twitch-markers/src/twitch_marker_agent/core/device_auth.py)

New DI-friendly module for Device Code Flow. All functions accept injected dependencies (http_client, logger).

**Endpoints:**
```python
TWITCH_DEVICE_URL = "https://id.twitch.tv/oauth2/device"
TWITCH_TOKEN_URL = "https://id.twitch.tv/oauth2/token"
DCF_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:device_code"
```

**Data Classes:**
```python
@dataclass(frozen=True)
class DeviceCodeResponse:
    """Response from device code request."""
    device_code: str      # Secret code for polling (don't log)
    user_code: str        # User-facing code to display
    verification_uri: str # URL for user to visit
    expires_in: int       # Seconds until device_code expires
    interval: int         # Polling interval in seconds

@dataclass
class TokenResponse:
    """Successful token response."""
    access_token: str
    refresh_token: str
    expires_in: int
    scope: list[str]
```

**Exceptions:**
```python
class DeviceAuthError(Exception):
    """Base exception for device auth errors."""
    pass

class DeviceCodeExpiredError(DeviceAuthError):
    """User did not complete auth in time."""
    pass

class DeviceAuthDeniedError(DeviceAuthError):
    """User explicitly denied authorization."""
    pass

class DeviceAuthCancelledError(DeviceAuthError):
    """Auth flow was cancelled by the application."""
    pass
```

**Core Functions:**
```python
def request_device_code(
    client_id: str,
    scopes: list[str],
    http_client: requests.Session,
    logger: logging.Logger,
) -> DeviceCodeResponse:
    """
    Request a device code from Twitch.
    
    Makes POST to https://id.twitch.tv/oauth2/device with:
    - client_id
    - scopes (space-delimited)
    
    Returns DeviceCodeResponse with user_code, verification_uri, etc.
    
    Raises:
        DeviceAuthError: On network or API errors.
    """

def poll_for_device_token(
    client_id: str,
    device_code: str,
    scopes: list[str],
    interval: int,
    timeout_seconds: int,
    http_client: requests.Session,
    logger: logging.Logger,
    cancel_event: threading.Event | None = None,
) -> TokenResponse:
    """
    Poll for device token until user authorizes or timeout.
    
    Handles standard DCF statuses:
    - authorization_pending: continue polling
    - slow_down: increase interval by 5 seconds
    - expired_token: raise DeviceCodeExpiredError
    - access_denied: raise DeviceAuthDeniedError
    
    Args:
        cancel_event: Optional event to signal cancellation.
    
    Returns:
        TokenResponse with tokens on success.
    
    Raises:
        DeviceCodeExpiredError: Device code expired.
        DeviceAuthDeniedError: User denied auth.
        DeviceAuthCancelledError: Cancelled via cancel_event.
        DeviceAuthError: Network or parse errors.
    """
```

---

### Tray Controller Integration

#### [MODIFY] [tray_controller.py](file:///c:/GoodVibez/automatic-twitch-markers/src/twitch_marker_agent/tray_controller.py)

Add device auth entrypoints:

```python
@dataclass
class DeviceAuthState:
    """Mutable state for device auth flow."""
    is_pending: bool = False
    cancel_event: threading.Event | None = None
    user_code: str | None = None
    verification_uri: str | None = None

@dataclass  
class AuthStatus:
    """Current authentication status."""
    is_authenticated: bool
    display_name: str | None = None
    user_id: str | None = None

def get_auth_status(
    oauth: TwitchOAuth,
    http_client: requests.Session,
    logger: logging.Logger,
) -> AuthStatus:
    """
    Get current auth status for menu display.
    
    Checks for valid stored token and fetches user info if authenticated.
    Caches display_name to avoid repeated API calls.
    """

def start_device_auth_flow(
    client_id: str,
    scopes: list[str],
    http_client: requests.Session,
    logger: logging.Logger,
) -> DeviceCodeResponse:
    """
    Start device auth flow by requesting device code.
    
    Returns DeviceCodeResponse for UI to display.
    """

def complete_device_auth_flow(
    client_id: str,
    device_code: str,
    scopes: list[str],
    interval: int,
    timeout_seconds: int,
    state_store: StateStore,
    http_client: requests.Session,
    logger: logging.Logger,
    cancel_event: threading.Event,
    on_status_update: Callable[[str], None] | None = None,
) -> AuthStatus:
    """
    Poll for token and store on success.
    
    Runs in background thread. Updates status via callback.
    Stores tokens in StateStore using existing keys.
    
    Returns:
        AuthStatus on success.
    
    Raises:
        DeviceAuthError subclasses on failure.
    """

def disconnect_twitch(
    state_store: StateStore,
    logger: logging.Logger,
) -> None:
    """
    Clear stored tokens and revoke (best-effort).
    
    Clears:
    - twitch_access_token
    - twitch_refresh_token  
    - twitch_token_expires_at
    """
```

---

### UI: Device Auth Dialog

#### [NEW] [device_auth_dialog.py](file:///c:/GoodVibez/automatic-twitch-markers/src/twitch_marker_agent/ui/device_auth_dialog.py)

Tkinter modal dialog following existing `DateRangeDialog` patterns.

```python
class DeviceAuthDialog:
    """
    Tkinter dialog for Device Code Flow authentication.
    
    Shows:
    - Large user_code display
    - "Open Twitch" button (opens verification_uri in browser)
    - "Copy Code" button (copies user_code to clipboard)
    - Status text + countdown timer
    - Cancel button
    
    Runs polling in background thread.
    Updates UI via after() callbacks (thread-safe).
    """
    
    def __init__(
        self,
        parent: tk.Tk | None,
        user_code: str,
        verification_uri: str,
        expires_in: int,
        on_poll: Callable[[], TokenResponse | None],
        on_cancel: Callable[[], None],
    ):
        """
        Initialize dialog.
        
        Args:
            on_poll: Callback that returns TokenResponse or None (still pending).
                     Raises on error.
            on_cancel: Callback to signal cancellation.
        """
    
    def show(self) -> TokenResponse | None:
        """
        Show dialog and wait for completion.
        
        Returns:
            TokenResponse on success, None if cancelled.
        """
```

**UI Layout:**
```
+-----------------------------------------+
|   Authenticate with Twitch              |
+-----------------------------------------+
|                                         |
|   Enter this code on Twitch:            |
|                                         |
|         +-------------------+           |
|         |    ABCD-EFGH      |  (large)  |
|         +-------------------+           |
|                                         |
|   [  Open Twitch  ]  [  Copy Code  ]    |
|                                         |
|   Status: Waiting for authorization...  |
|   Expires in: 4:32                      |
|                                         |
|              [  Cancel  ]               |
|                                         |
+-----------------------------------------+
```

---

### Tray Menu Updates

#### [MODIFY] [app.py](file:///c:/GoodVibez/automatic-twitch-markers/src/twitch_marker_agent/app.py)

Add menu items and handlers:

```python
def create_tray_menu(
    ...
    auth_status: AuthStatus,        # NEW
    device_auth_state: DeviceAuthState,  # NEW
    on_authenticate: Callable[[], None],  # NEW
    on_disconnect: Callable[[], None],    # NEW
):
    """
    Build tray context menu.
    
    Menu structure:
    - [OK] Connected as <display_name>  (disabled, status only)
      OR
    - [WARN] Not authenticated  (disabled, status only)
    - -----------------
    - Authenticate with Twitch...  (enabled if not auth'd & not pending)
    - Disconnect Twitch  (enabled if auth'd)
    - -----------------
    - (existing items...)
    """

# In run_tray_app():
def on_authenticate():
    """Handle Authenticate with Twitch... action."""
    # 1. Set device_auth_state.is_pending = True
    # 2. Create cancel_event
    # 3. Call start_device_auth_flow()
    # 4. Show DeviceAuthDialog
    # 5. On success: store tokens, update status, show notification
    # 6. On cancel/error: clean up state
    # 7. Update menu

def on_disconnect():
    """Handle Disconnect Twitch action."""
    # 1. Call disconnect_twitch()
    # 2. Update auth_status
    # 3. Update menu
    # 4. Show notification "Disconnected from Twitch"
```

---

### Token Refresh Modifications

#### [MODIFY] [twitch_oauth.py](file:///c:/GoodVibez/automatic-twitch-markers/src/twitch_marker_agent/core/twitch_oauth.py)

Modify `refresh_access_token` to support DCF tokens:

```python
# Add state key to track auth method
TOKEN_KEY_AUTH_METHOD = "twitch_auth_method"  # "dcf" or "authorization_code"

def _refresh_access_token_unlocked(self) -> None:
    """
    Internal refresh implementation.
    
    For DCF tokens (auth_method == "dcf"):
    - Do NOT send client_secret
    - Handle single-use refresh tokens (store new one)
    - On 401: clear tokens, raise TokenRefreshError with re-auth message
    """
    auth_method = self._state_store.get_token(self.TOKEN_KEY_AUTH_METHOD) or "authorization_code"
    
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": self._config.client_id,
    }
    
    # Only include client_secret for authorization_code flow
    if auth_method != "dcf":
        data["client_secret"] = self._config.client_secret
    
    # ... rest of refresh logic
```

> [!IMPORTANT]
> DCF refresh tokens are **single-use**. Each refresh returns a new refresh_token that must be stored. The existing code already handles this (lines 648-651).

> [!WARNING]
> DCF refresh tokens expire after **30 days of inactivity**. Users may need to re-authenticate periodically.

---

## Verification Plan

### Automated Tests

All tests use `unittest` + `unittest.mock`. No real network calls.

#### Core Device Auth Tests (`tests/test_device_auth.py`)

| Test | Description |
|------|-------------|
| `test_request_device_code_success` | Mock successful device code response |
| `test_request_device_code_network_error` | Mock network error, verify safe exception |
| `test_request_device_code_api_error` | Mock 400/500 response, verify error handling |
| `test_poll_authorization_pending_loops` | Mock pending -> success, verify polling |
| `test_poll_slow_down_increases_interval` | Mock slow_down, verify interval increase |
| `test_poll_expired_token_raises` | Mock expired_token, verify DeviceCodeExpiredError |
| `test_poll_access_denied_raises` | Mock access_denied, verify DeviceAuthDeniedError |
| `test_poll_cancellation` | Set cancel_event, verify DeviceAuthCancelledError |
| `test_poll_network_error_safe_message` | Verify error message doesn't leak secrets |

#### Tray Controller Auth Tests (`tests/test_tray_auth_flow.py`)

| Test | Description |
|------|-------------|
| `test_start_flow_calls_request_device_code` | Verify core function called with correct args |
| `test_complete_flow_stores_tokens` | Mock success, verify StateStore.store_token calls |
| `test_complete_flow_stores_auth_method` | Verify "dcf" stored as auth method |
| `test_disconnect_clears_all_tokens` | Verify all token keys deleted |
| `test_get_auth_status_authenticated` | Mock valid token, verify status |
| `test_get_auth_status_not_authenticated` | No token, verify status |
| `test_cancellation_stops_polling` | Set cancel_event, verify clean stop |

#### Token Refresh DCF Tests (add to `tests/test_twitch_oauth.py`)

| Test | Description |
|------|-------------|
| `test_refresh_dcf_no_client_secret` | Verify client_secret not sent for DCF |
| `test_refresh_dcf_stores_new_refresh_token` | Verify rotation works |
| `test_refresh_dcf_401_suggests_reauth` | Verify clear error message |

### Manual Verification

1. Build and run tray app
2. Click "Authenticate with Twitch..."
3. Verify dialog shows user_code
4. Click "Open Twitch" - verify browser opens to verification URL
5. Complete auth on Twitch
6. Verify "Connected as <name>" appears in tray menu
7. Click "Disconnect Twitch"
8. Verify status changes to "Not authenticated"

---

## Files to Change/Add in RUN 2

### New Files
| File | Purpose |
|------|---------|
| `src/twitch_marker_agent/core/device_auth.py` | Core DCF logic |
| `src/twitch_marker_agent/ui/device_auth_dialog.py` | Tkinter auth dialog |
| `tests/test_device_auth.py` | Core module tests |
| `tests/test_tray_auth_flow.py` | Controller/integration tests |

### Modified Files
| File | Changes |
|------|---------|
| `src/twitch_marker_agent/tray_controller.py` | Add auth entrypoints, AuthStatus/DeviceAuthState dataclasses |
| `src/twitch_marker_agent/app.py` | Add menu items, auth handlers |
| `src/twitch_marker_agent/core/twitch_oauth.py` | DCF-aware refresh, TOKEN_KEY_AUTH_METHOD |
| `src/twitch_marker_agent/core/__init__.py` | Export new module |
| `tests/test_twitch_oauth.py` | Add DCF refresh tests |
| `README.md` | Document tray auth feature |
| `AGENTS.md` | Add device_auth.py to implemented list |

### Not Modified
| File | Reason |
|------|--------|
| `config.json` | No schema changes (per constraints) |
| `config.py` | client_id already exists, client_secret stays optional |
| `state_store.py` | Reuse existing token storage methods |

---

## Implementation Order (RUN 2 Steps)

1. **Create `core/device_auth.py`** - dataclasses, exceptions, core functions
2. **Add tests for device_auth** - verify core logic before integration
3. **Modify `twitch_oauth.py`** - DCF-aware refresh
4. **Add DCF refresh tests** - verify no client_secret sent
5. **Create `ui/device_auth_dialog.py`** - tkinter dialog
6. **Add tray_controller entrypoints** - AuthStatus, DeviceAuthState, functions
7. **Add tray controller tests** - verify integration
8. **Modify `app.py`** - menu items, handlers
9. **Update documentation** - README, AGENTS.md
10. **Run full test suite** - `python -m unittest discover -s tests -v`

---

## Test Commands (for RUN 2)

```powershell
# Run device auth core tests
python -m unittest tests.test_device_auth -v

# Run tray auth flow tests
python -m unittest tests.test_tray_auth_flow -v

# Run all tests
python -m unittest discover -s tests -v
```
