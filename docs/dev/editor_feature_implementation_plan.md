# Editor Channel Feature — Investigation & Implementation Plan

## Summary

Allow a Twitch editor to authenticate with their own account and fetch marker files for a broadcaster channel they edit, using that broadcaster's login as a manual override.

---

## A) Auth / Token / Scope Audit

### Current token scope: `channel:manage:broadcast`

The Twitch `Get Stream Markers` API grants permission based on **who owns the channel**, not who makes the request. Specifically:

> The `user_id` query parameter on `GET /helix/streams/markers` must be the **broadcaster's** user ID.
> The authenticated token must belong to either the **broadcaster** or an **editor** of that channel.

**Conclusion**: The existing `channel:manage:broadcast` scope is **sufficient** — no new scopes are needed. An editor's token will be accepted by the Helix endpoint as long as the editor relationship exists on Twitch. No scope changes are required.

---

## B) Broadcaster ID Resolution — Current Architecture

### How the app currently finds the broadcaster

**Single call-site in `tray_controller.py` line 295:**
```python
broadcaster_id = resolve_broadcaster_id(config, state_store)
```

**`resolve_broadcaster_id` in `auth_identity.py`:**
```python
# Reads StateStore["twitch_broadcaster_id"], falls back to config.broadcaster_id
```

**Auth bootstrap (on login success in `app.py`):**
- Calls Helix `/users` with no `login` param → gets **self** identity
- Persists as `state_store["twitch_broadcaster_id"]` (the authenticated user)

### What "self channel" assumption exists

| Code path | Broadcaster ID source | Explicit assumption |
|---|---|---|
| `run_manual_fetch()` | `resolve_broadcaster_id(config, state_store)` | Implicitly "self" (set during auth) |
| `run_multi_fetch()` | Same call | Same |
| EventSub subscription (`ensure_subscription_fn`) | `resolve_broadcaster_id(config, state_store)` | Same — **Auto Mode subscribes to self's offline event** |
| EventSub offline handler | Config `broadcaster_id` + token | Same |

**Key insight**: All paths share the same StateStore key (`twitch_broadcaster_id`). Overwriting it for an edited channel would break Auto Mode (which would then subscribe to the *editor's channel*'s offline events using someone else's token). Therefore, a **separate override key** is needed.

---

## C) Recommended UX Pattern

### Recommended: Mode toggle in tray menu

```
──────────────────────────────
Authenticated as @YourLogin
──────────────────────────────
✓ Channel: My Channel                ← checkable item
  Channel: Edited Channel ►          ← submenu:
      Set Channel Login…             ← opens input dialog
      ──────────────────
      recent_channel_1
      recent_channel_2
      ──────────────────
      Clear Saved Channels
──────────────────────────────
[Fetch Latest Stream Markers]  ← Now uses active channel
[Fetch Multiple Stream Markers]
...
```

**Why this pattern:**
- Fits existing pystray `Menu`/`MenuItem` patterns already in use
- Natural "My Channel / Edited Channel" toggle visible at a glance
- Recents are surfaced inline without a separate settings page
- Simple to gate: fetch actions always read from the same resolved function

**UX rules:**
- Auto Mode always uses "My Channel" regardless of edit mode selection (see E)
- Active channel label shown in menu header: `Channel: @login (Editor)` or `Channel: @my_login`
- Permission errors on fetch surface as tray notifications with clear message

---

## D) Persistence Model

### New StateStore keys (no public signature changes)

```python
# tray_controller.py constants
TRAY_CHANNEL_MODE_KEY        = "tray.channel_mode"        # "self" | "edited"
TRAY_EDITED_CHANNEL_ID_KEY   = "tray.edited_channel_id"   # resolved user_id
TRAY_EDITED_CHANNEL_LOGIN_KEY = "tray.edited_channel_login" # login string
TRAY_EDITED_RECENT_KEY       = "tray.edited_recent_channels"  # JSON list
```

### Data shapes

**`tray.channel_mode`**: `"self"` or `"edited"` (default absent = `"self"`)

**`tray.edited_channel_id`** / **`tray.edited_channel_login`**: string, resolved at time of successful first fetch

**`tray.edited_recent_channels`**: JSON-encoded list of objects, max 5 entries, newest first:
```json
[
  {"login": "streamername", "id": "12345678", "display_name": "StreamerName"},
  ...
]
```

**Why store both login and id:** ID never changes (rename-safe). Login is for display. Store both at resolution time.

**Why store JSON in a state string:** StateStore `get_state`/`set_state` accept string values. Use `json.dumps`/`json.loads`. No StateStore signature change required.

**Persistence is global per app instance** — the current architecture is single-user, so per-user scoping is not needed.

---

## E) Scope Boundary Recommendation

### RUN 2 Scope: Manual Fetch + Multi-Fetch ONLY

**Explicitly defer Auto Mode / EventSub editor support.**

**Reasoning:**

| Feature | Risk | Verdict |
|---|---|---|
| Manual fetch with edited channel | Low — single call-site, isolated broadcaster_id param | ✅ Include in RUN 2 |
| Multi-fetch with edited channel | Low — same call-site pattern as manual fetch | ✅ Include in RUN 2 |
| Auto Mode EventSub with edited channel | **High** — EventSub `stream.offline` subscription must be for **the broadcaster's channel**, not the editor's. The subscription uses the broadcaster ID from StateStore, which is "self" ID. Changing this for editors would require: a different EventSub subscription subject (broadcaster who may not have authorized this app's client_id for their own EventSub), handling `stream.offline` for a channel you don't own, and careful token/broadcaster coupling that assumes the editor's Twitch relationship stays current at all times. | ❌ Defer |

**Auto Mode correctly stays on "My Channel"** — the app listens for its own `stream.offline` event. An editor wanting auto-export for another broadcaster's channel would need the broadcaster to install the app (or a future webhook/subscription model).

**Tray guardrail:** Auto Mode is not gated by channel mode. If user switches to "Edited Channel" mode, Auto Mode still runs for self. A static label in the Auto Mode section clarifies: `"Auto Mode monitors: My Channel"`.

---

## Pre-Flight Answers

### 1. Safest first-release scope?
**Manual fetch + multi-fetch only.** Auto Mode deferred — see E above.

### 2. Best tray UX pattern?
Mode toggle with "Channel: My Channel / Edited Channel ►" submenu that includes "Set Channel Login…" + recents + clear. See B above.

### 3. Safest persistence model?
Four new `tray.*` StateStore string keys (one with JSON). No new StateStore methods needed. See D above.

### 4. Top "self = broadcaster" assumptions and risk to generalize?
| Call-site | Risk | Fix |
|---|---|---|
| `run_manual_fetch` line 295: `resolve_broadcaster_id` | Low — isolated | New `resolve_active_channel_id(state_store, config)` function |
| `run_multi_fetch` same pattern | Low | Same new function |
| Auth bootstrap (`persist_broadcaster_identity`) | Zero risk — this always stores self, untouched | None |
| EventSub subscription | High | Deferred |

### 5. What to defer from RUN 2?
- Auto Mode / EventSub edited channel support
- API-driven editor-channel discovery (Twitch has no public "list channels I edit" endpoint)
- Per-authenticated-user recent lists
- Multi-account support

---

## Proposed Public API

### New module: `core/helix_users.py` (or add to `auth_identity.py`)

```python
def fetch_user_by_login(
    http_client: requests.Session,
    client_id: str,
    access_token: str,
    login: str,
    logger: logging.Logger,
) -> BroadcasterIdentity:
    """
    Resolve a Twitch login to user_id + display_name via Helix /users?login=.

    Args:
        http_client: Requests session.
        client_id: Twitch application client ID.
        access_token: Valid OAuth access token.
        login: Broadcaster login to look up.
        logger: Logger instance.

    Returns:
        BroadcasterIdentity with id/login/display name.

    Raises:
        BroadcasterIdentityError: If login not found or request fails.
    """
```

### New functions in `tray_controller.py`

```python
TRAY_CHANNEL_MODE_KEY = "tray.channel_mode"
TRAY_EDITED_CHANNEL_ID_KEY = "tray.edited_channel_id"
TRAY_EDITED_CHANNEL_LOGIN_KEY = "tray.edited_channel_login"
TRAY_EDITED_RECENT_KEY = "tray.edited_recent_channels"

def get_channel_mode(state_store: "StateStore") -> str:
    """Returns 'self' or 'edited'. Defaults to 'self'."""

def set_channel_mode(state_store: "StateStore", mode: str) -> None:
    """Persist 'self' or 'edited' channel mode."""

def get_edited_channel(state_store: "StateStore") -> "BroadcasterIdentity | None":
    """Get current saved edited channel identity, or None."""

def set_edited_channel(state_store: "StateStore", identity: "BroadcasterIdentity") -> None:
    """Persist edited channel identity."""

def clear_edited_channel(state_store: "StateStore") -> None:
    """Clear saved edited channel and mode, reverting to self."""

def get_recent_edited_channels(state_store: "StateStore") -> "list[BroadcasterIdentity]":
    """Get list of recent edited channels (newest first, max 5)."""

def add_recent_edited_channel(
    state_store: "StateStore",
    identity: "BroadcasterIdentity",
    max_recents: int = 5,
) -> None:
    """Add to recent edited channels, dedup by id, newest first."""

def resolve_active_broadcaster_id(
    config: "AppConfig",
    state_store: "StateStore",
) -> str | None:
    """
    Resolve the broadcaster ID to use for fetch operations.

    In 'self' mode: same as resolve_broadcaster_id().
    In 'edited' mode: returns the override edited channel ID.
    Falls back to 'self' if edited channel not set.
    """
```

### Changed signatures in `tray_controller.py`

```python
def run_manual_fetch(
    http_client: "requests.Session",
    config: "AppConfig",
    state_store: "StateStore",
    oauth: "TwitchOAuth",
    output_dir: Path,
    export_formats: tuple[str, ...],
    logger: logging.Logger,
) -> ManualFetchResult:
    # Change: use resolve_active_broadcaster_id() instead of resolve_broadcaster_id()
    # No signature change.
```

The `run_manual_fetch` and `run_multi_fetch` signatures do **not** change — only the internal `resolve_broadcaster_id` call is swapped for `resolve_active_broadcaster_id`.

---

## Implementation Steps (RUN 2)

1. **`core/auth_identity.py`** — Add `fetch_user_by_login()` (new function, calls `/helix/users?login=…`)

2. **`tray_controller.py`** — Add constants + 7 new persistence functions; replace `resolve_broadcaster_id` with `resolve_active_broadcaster_id` in `run_manual_fetch` and `run_multi_fetch`

3. **`app.py`** — Add `on_set_edited_channel()` dialog callback; add channel mode submenu to `create_tray_menu()`; pass channel mode display into menu

4. **Tests** — See test plan below

5. **Docs** — README, `tray_app.md`, new `editor_channel.md`

---

## Test Plan

### New tests in `test_tray_controller.py`

| Test | What |
|---|---|
| `test_get_channel_mode_default_self` | Returns "self" when key absent |
| `test_set_channel_mode_edited` | Persists "edited" |
| `test_get_edited_channel_none` | Returns None when no edited channel set |
| `test_set_and_get_edited_channel` | Round-trips BroadcasterIdentity via JSON |
| `test_clear_edited_channel_resets_mode` | Clears both edited channel + mode keys |
| `test_add_recent_deduplicates_by_id` | Adding same ID twice keeps only one |
| `test_add_recent_max_5` | List capped at 5, newest first |
| `test_resolve_active_broadcaster_id_self_mode` | Returns self broadcaster ID |
| `test_resolve_active_broadcaster_id_edited_mode` | Returns edited channel ID |
| `test_resolve_active_broadcaster_id_edited_mode_no_channel_set` | Falls back to self |
| `test_manual_fetch_uses_edited_channel_id` | `run_manual_fetch` uses override ID in edited mode |
| `test_manual_fetch_permission_error_does_not_save_recent` | `MarkersAuthError` → no recent added |

### New tests in `test_auth_identity.py`

| Test | What |
|---|---|
| `test_fetch_user_by_login_success` | Returns BroadcasterIdentity for valid login |
| `test_fetch_user_by_login_not_found` | Raises BroadcasterIdentityError |
| `test_fetch_user_by_login_http_error` | Raises BroadcasterIdentityError |

---

## Files Changed / Added in RUN 2

| File | Change |
|---|---|
| `core/auth_identity.py` | Add `fetch_user_by_login()` |
| `tray_controller.py` | Add constants + 7 functions + `resolve_active_broadcaster_id()`, swap call-site |
| `app.py` | Add channel mode submenu, `on_set_edited_channel()`, `on_clear_edited_channel()` |
| `tests/test_tray_controller.py` | Add 12 new tests |
| `tests/test_auth_identity.py` | Add 3 new tests |
| `README.md` | Mention editor channel feature in Features section |
| `docs/user/tray_app.md` | Document channel mode menu + behavior |
| `docs/user/editor_channel.md` | **[NEW]** Full user guide for the feature |

---

## Docs That Need Updates in RUN 2

| Doc | Change |
|---|---|
| `README.md` | Add "Editor channel" to Features list |
| `docs/user/tray_app.md` | Add Channel Mode section |
| `docs/user/editor_channel.md` | New file: usage guide, scope limits, Auto Mode note |
| `docs/dev/handoff.md` | Add feature to implemented components list |

> [!IMPORTANT]
> **Auto Mode scope guardrail — must be documented**: Auto Mode always monitors the authenticated user's own channel. It does NOT follow the "Edited Channel" selection. This must be clearly documented in `editor_channel.md` and noted in the tray menu UI.

> [!IMPORTANT]
> **Permission validation**: The app validates editor access by attempting the actual markers fetch. If Twitch returns a 403/auth error, the channel is NOT saved to recents and the user sees a clear tray notification. There is no pre-validation step (Twitch offers no reliable "am I an editor?" endpoint).
