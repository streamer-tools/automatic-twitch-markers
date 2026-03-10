# Tray App Stabilization — Investigation & Implementation Plan

## Summary

Three product-quality issues for the Windows tray app:
1. Rename built EXE to **Automatic Twitch Markers**
2. Persist Auto Mode across app restart / PC reboot
3. Fix intermittent Auto Mode refusal-to-start

---

## A) EXE / App Naming Audit

### Current state

`TwitchMarkerAgent` appears in **30+ locations**:

| Location | Current Value |
|---|---|
| [build_exe.ps1](file:///c:/GoodVibez/automatic-twitch-markers/scripts/build_exe.ps1) `--name` | `TwitchMarkerAgent` |
| [release.yml](file:///c:/GoodVibez/automatic-twitch-markers/.github/workflows/release.yml) `--name`, artifact, zip | `TwitchMarkerAgent` |
| [app.py:867](file:///c:/GoodVibez/automatic-twitch-markers/src/twitch_marker_agent/app.py#L867) tray title | `"Twitch Marker Agent"` |
| [windows_startup.py:21](file:///c:/GoodVibez/automatic-twitch-markers/src/twitch_marker_agent/platform/windows_startup.py#L21) `_APP_NAME` | `"TwitchMarkerAgent"` |
| [build_exe.ps1](file:///c:/GoodVibez/automatic-twitch-markers/scripts/build_exe.ps1) banner/log strings | `TwitchMarkerAgent.exe` |
| Docs: README, packaging, configuration, handoff | `TwitchMarkerAgent.exe` |
| Tests: `test_windows_startup.py`, `test_runtime_paths.py` | `TwitchMarkerAgent` |
| Generated spec file | `TwitchMarkerAgent.spec` |

### New values

| Location | New Value |
|---|---|
| Build `--name` | `"Automatic Twitch Markers"` |
| CI `--name`, artifact, zip | `"Automatic Twitch Markers"` / `AutomaticTwitchMarkers-windows.zip` |
| Tray title | `"Automatic Twitch Markers"` |
| Tray `name=` (pystray internal) | `"automatic-twitch-markers"` (already correct) |
| Build script banner/log strings | `Automatic Twitch Markers.exe` |

> [!WARNING]
> **Registry `_APP_NAME`**: Should this change from `TwitchMarkerAgent` to `AutomaticTwitchMarkers`?
> - **Risk**: Users who already have startup enabled will have a stale registry entry pointing at the old EXE name. The old entry won't be cleaned up automatically.
> - **Recommendation**: Keep `_APP_NAME = "TwitchMarkerAgent"` for backward compatibility. The registry value name is an internal identifier, not user-visible. Existing startup entries will still work if the EXE is in the same location (the command path is absolute). If we later want to change it, a migration step can clean up the old key.
> - Alternatively: Add migration logic in `enable_startup()` that deletes the old key before writing the new one.

---

## B) Auto Mode Persistence Audit

### Current state

- `AutoModeState` is a runtime-only dataclass (line 80 of `tray_controller.py`)
- No persisted key exists for "Auto Mode enabled"
- `StateStore.get_state`/`set_state` already used for `tray.output_dir` and `tray.edl_enabled` — same pattern fits

### Design

**Key**: `tray.auto_mode_enabled` (new constant `TRAY_AUTO_MODE_ENABLED_KEY`)

**Write points**:
- `start_auto_mode()` → `set_state("tray.auto_mode_enabled", "true")` after thread starts
- `stop_auto_mode()` → `set_state("tray.auto_mode_enabled", "false")` after thread stops
- `on_exit()` → `set_state("tray.auto_mode_enabled", "false")` on graceful shutdown

**Read point** — startup sequence in `run_tray_app()`:
1. Initialize tray state, create icon, show menu
2. Refresh auth status
3. Check `get_state("tray.auto_mode_enabled")` → if `"true"` AND authenticated, auto-start

### New functions

```python
# In tray_controller.py
TRAY_AUTO_MODE_ENABLED_KEY = "tray.auto_mode_enabled"

def get_auto_mode_enabled(state_store: "StateStore") -> bool:
    """Get persisted Auto Mode enabled preference."""
    stored = state_store.get_state(TRAY_AUTO_MODE_ENABLED_KEY)
    if stored is None:
        return False
    return str(stored).strip().lower() in ("true", "1", "yes")

def set_auto_mode_enabled(state_store: "StateStore", enabled: bool) -> None:
    """Persist Auto Mode enabled preference."""
    state_store.set_state(TRAY_AUTO_MODE_ENABLED_KEY, "true" if enabled else "false")
```

No new `StateStore` public method signatures required.

### Startup sequence (in `run_tray_app()`)

```python
# After icon creation, auth refresh, and menu build:
if get_auto_mode_enabled(state_store) and cached_auth_status and cached_auth_status.is_authenticated:
    logger.info("Restoring Auto Mode from persisted state")
    auto_state = start_auto_mode(auto_state, agent, logger)
    update_menu()
```

**Why this order**: The icon must exist first so notifications work. Auth must be validated before attempting Auto Mode. If auth is invalid, we keep the persisted flag true but don't start — user sees "Start Auto Mode" in menu and can manually retry after re-authenticating.

---

## C) Intermittent Auto Mode Refusal-to-Start Audit

### Confirmed bug: stale `is_running` flag

In [tray_controller.py:490](file:///c:/GoodVibez/automatic-twitch-markers/src/twitch_marker_agent/tray_controller.py#L490):

```python
def start_auto_mode(state, agent, logger) -> AutoModeState:
    if state.is_running:           # ← STALE FLAG CHECK
        logger.debug("Auto mode already running, ignoring start request")
        return state
```

**Problem**: If the worker thread dies (e.g. EventSub connection lost, uncaught exception in `asyncio.run`), `state.is_running` remains `True` because it was set on line 511 and only cleared by `stop_auto_mode()`. The UI menu correctly derives from `thread.is_alive()` (lines 174-190 of `app.py`), so it shows "Start Auto Mode" — but clicking it hits the `is_running` guard and silently returns.

**Evidence**: The app.py UI already uses `_is_auto_running()` which checks `thread.is_alive()`, but `start_auto_mode()` checks `state.is_running` instead. These diverge when the thread dies without a stop.

### Top 3 failure modes (ranked by confidence)

| # | Failure Mode | Confidence | Evidence |
|---|---|---|---|
| 1 | **Stale `is_running` flag after thread death** — `start_auto_mode()` gates on `state.is_running` (bool), not `thread.is_alive()`. If thread dies, bool stays `True`, blocking restart. | **HIGH** (code-proven) | `tray_controller.py:490` vs `app.py:107-113` |
| 2 | **`AgentRunner._is_running` stays `True` briefly during error paths** — If `run_async()` returns via early `return` (lines 263-307), the `finally` block (line 373) resets `_is_running = False`, but the `AutoModeState.is_running` in the tray layer isn't automatically updated. | **MEDIUM** (code-proven, but mitigated by thread.is_alive check in UI) | `agent_runner.py:247,373` |
| 3 | **Stop timeout leaving state inconsistent** — `stop_auto_mode()` with timeout returns `is_running=True` if thread doesn't exit (line 556-560), but there's no follow-up reconciliation. A subsequent `start_auto_mode()` then refuses because `state.is_running == True` and the old thread reference may still exist. | **MEDIUM** (code-proven) | `tray_controller.py:550-560` |

### Fix

Replace the `is_running` guard in `start_auto_mode()` with a `thread.is_alive()` check:

```python
def start_auto_mode(state, agent, logger) -> AutoModeState:
    if state.thread is not None and state.thread.is_alive():
        logger.debug("Auto mode already running, ignoring start request")
        return state
    # ... proceed to start
```

This makes `start_auto_mode()` consistent with the UI predicates. A dead thread is treated as "not running", allowing restart.

---

## D) Design Constraints for RUN 2

1. **`start_auto_mode()` should derive state from `thread.is_alive()`** — Yes, confirmed. This is the root fix.

2. **Should `stop_auto_mode()` also reconcile?** — `stop_auto_mode()` already checks `state.is_running` as a guard. We should also derive from `thread.is_alive()` for consistency. If the thread is already dead, skip the stop sequence.

3. **Should Auto Mode failure callback clear persisted enabled state?** — No. Transient failures (network blips, token refresh) shouldn't clear the user's preference. The persisted flag represents user *intent*, not runtime state.

4. **If auto-start-on-launch fails** — Keep the persisted enabled state. Surface a tray notification so the user knows. The user can then manually start via the menu after re-authenticating. This is the least surprising behavior.

---

## Proposed Changes

### Component 1: Tray Controller

#### [MODIFY] [tray_controller.py](file:///c:/GoodVibez/automatic-twitch-markers/src/twitch_marker_agent/tray_controller.py)

- Add `TRAY_AUTO_MODE_ENABLED_KEY = "tray.auto_mode_enabled"`
- Add `get_auto_mode_enabled()` and `set_auto_mode_enabled()` functions
- Fix `start_auto_mode()`: replace `state.is_running` guard with `thread.is_alive()` check
- Fix `stop_auto_mode()`: replace `state.is_running` guard with `thread.is_alive()` check
- Wire `set_auto_mode_enabled()` calls into `start_auto_mode()` and `stop_auto_mode()` (accepting `state_store` parameter)

> [!IMPORTANT]
> `start_auto_mode()` and `stop_auto_mode()` need an optional `state_store` parameter to persist the flag. This does NOT change any `StateStore` public method signatures (invariant preserved), it only adds a parameter to tray controller functions.

---

### Component 2: Tray App

#### [MODIFY] [app.py](file:///c:/GoodVibez/automatic-twitch-markers/src/twitch_marker_agent/app.py)

- Change tray title from `"Twitch Marker Agent"` to `"Automatic Twitch Markers"` (line 867)
- Pass `state_store` to `start_auto_mode()` / `stop_auto_mode()` calls
- Add auto-start-on-launch logic after icon creation
- Set `auto_mode_enabled = false` in `on_exit()`

---

### Component 3: Build / CI

#### [MODIFY] [build_exe.ps1](file:///c:/GoodVibez/automatic-twitch-markers/scripts/build_exe.ps1)

- Change `--name TwitchMarkerAgent` → `--name "Automatic Twitch Markers"`
- Update all `TwitchMarkerAgent.exe` references → `Automatic Twitch Markers.exe`

#### [MODIFY] [release.yml](file:///c:/GoodVibez/automatic-twitch-markers/.github/workflows/release.yml)

- Change `--name TwitchMarkerAgent` → `--name "Automatic Twitch Markers"`
- Update zip/artifact names → `AutomaticTwitchMarkers-windows.zip`

---

### Component 4: Windows Startup (decision needed)

#### [MODIFY] [windows_startup.py](file:///c:/GoodVibez/automatic-twitch-markers/src/twitch_marker_agent/platform/windows_startup.py)

- Keep `_APP_NAME = "TwitchMarkerAgent"` (backward compatible) **OR** change to `"AutomaticTwitchMarkers"` with migration

---

### Component 5: Tests

#### [MODIFY] [test_tray_controller.py](file:///c:/GoodVibez/automatic-twitch-markers/tests/test_tray_controller.py)

- Add `TestGetAutoModeEnabled` — state store returns true/false/None
- Add `TestSetAutoModeEnabled` — persists correct string values
- Add `test_start_auto_mode_with_dead_thread_allows_restart` — stale flag regression test
- Add `test_stop_auto_mode_with_dead_thread_is_noop` — dead thread stop
- Add `test_start_auto_mode_persists_enabled_state` — writes to state store
- Add `test_stop_auto_mode_clears_enabled_state` — writes to state store

#### [MODIFY] [test_windows_startup.py](file:///c:/GoodVibez/automatic-twitch-markers/tests/test_windows_startup.py)

- Update `_APP_NAME` assertions if registry name changes

#### [MODIFY] [test_runtime_paths.py](file:///c:/GoodVibez/automatic-twitch-markers/tests/test_runtime_paths.py)

- Update test EXE path expectations if applicable

---

### Component 6: Docs

#### Files that need updates

| File | Change |
|---|---|
| [README.md](file:///c:/GoodVibez/automatic-twitch-markers/README.md) | `TwitchMarkerAgent.exe` → `Automatic Twitch Markers.exe` |
| [docs/user/packaging.md](file:///c:/GoodVibez/automatic-twitch-markers/docs/user/packaging.md) | EXE name references |
| [docs/user/configuration.md](file:///c:/GoodVibez/automatic-twitch-markers/docs/user/configuration.md) | EXE name reference |
| [docs/dev/handoff.md](file:///c:/GoodVibez/automatic-twitch-markers/docs/dev/handoff.md) | EXE name reference |
| [AGENTS.md](file:///c:/GoodVibez/automatic-twitch-markers/AGENTS.md) | No change needed (references module names, not EXE name) |

Archived docs (`docs/dev/archive/*`) are historical records and should NOT be updated.

---

## Pre-Flight Questions — Answers

### 1. Should the rename be built artifact only, or built artifact + tray/UI strings too?

**Recommendation: Both.** The tray tooltip title (`"Twitch Marker Agent"`) is user-visible and should match the product name `"Automatic Twitch Markers"`. The pystray `name=` is already `"automatic-twitch-markers"` (internal identifier, no change needed).

### 2. Should Windows startup registry value name change?

**Recommendation: Keep `"TwitchMarkerAgent"` for now.** It's an internal identifier, not user-visible. Changing it orphans existing startup entries. If we do change it later, a migration step should delete the old key.

### 3. What is the safest persistence location for "Auto Mode enabled"?

**`StateStore.get_state`/`set_state`** with key `"tray.auto_mode_enabled"`. This follows the exact pattern used by `tray.output_dir` and `tray.edl_enabled`. No new `StateStore` method signatures needed.

### 4. On relaunch with persisted Auto Mode enabled, what startup sequence?

1. Initialize all state objects and dependencies
2. Create tray icon and show initial menu
3. Refresh auth status (validates token, may trigger silent refresh)
4. **If** `tray.auto_mode_enabled == "true"` **AND** auth is valid → auto-start Auto Mode
5. **If** auth is invalid → keep flag true, surface notification, user retries manually

### 5. Top 3 causes of intermittent Auto Mode refusal-to-start

See Section C above. In order:
1. **Stale `is_running` flag** (HIGH confidence, code-proven)
2. **AgentRunner internal `_is_running` / tray `is_running` desync** (MEDIUM)
3. **Stop timeout leaving `is_running=True`** (MEDIUM)

---

## Verification Plan

### Automated Tests

**Command**: `python -m unittest discover -s tests -v`

New tests to add in `test_tray_controller.py`:
1. `test_get_auto_mode_enabled_default_false` — `get_state` returns None → False
2. `test_get_auto_mode_enabled_true` — `get_state` returns "true" → True
3. `test_set_auto_mode_enabled_true` — calls `set_state` with "true"
4. `test_set_auto_mode_enabled_false` — calls `set_state` with "false"
5. `test_start_auto_mode_dead_thread_allows_restart` — state has `is_running=True` + dead thread → should still start new thread
6. `test_stop_auto_mode_dead_thread_noop` — state has dead thread → clean stop without error
7. `test_start_auto_mode_persists_enabled` — start writes "true" to state store
8. `test_stop_auto_mode_clears_enabled` — stop writes "false" to state store

Existing tests that should still pass:
- `TestStartAutoMode.test_spawns_thread_once`
- `TestStartAutoMode.test_noop_when_running`
- `TestStopAutoMode.test_calls_request_stop_and_joins`
- `TestAutoModeStatusChecks.test_dead_thread_shows_stopped`

### Manual Verification

1. **Build**: Run `.\scripts\build_exe.ps1 -Clean -AllowPlaceholderClientId` → verify output is `dist\Automatic Twitch Markers.exe`
2. **Tray title**: Launch EXE → hover over tray icon → tooltip reads "Automatic Twitch Markers"
3. **Auto-restart**: Enable Auto Mode → close app → relaunch → Auto Mode restores automatically
4. **Dead-thread restart**: (harder to reproduce) Enable Auto Mode → disconnect network to kill EventSub → wait for thread to die → click "Start Auto Mode" → should start successfully

---

## RUN 2 Execution Order

1. Fix `start_auto_mode()` / `stop_auto_mode()` stale flag → core reliability fix
2. Add persistence functions and constants
3. Wire persistence into start/stop/exit
4. Add auto-start-on-launch in `run_tray_app()`
5. Rename EXE in build script + CI
6. Rename tray title in `app.py`
7. Update tests
8. Update docs
9. Run full test suite
