# Release Readiness Implementation Plan

## Preflight Question Answers

### 1. Tray App Entry Point
**Answer**: `twitch_marker_agent.app:main` 
- Module path: `src/twitch_marker_agent/app.py`
- Function: `main()` (lines 550-595)
- Loads config, initializes deps, calls `run_tray_app()`

### 2. One Executable vs Multiple
**Recommendation**: **One tray exe only** for v1.0
- **Primary use case**: Tray app (set-and-forget background agent)
- **CLI**: Currently only used for `auth-login` one-time setup; users can run via `python -m twitch_marker_agent.cli auth-login` from source
- **Rationale**: Simplifies packaging, distribution, and user experience. CLI can be added later if needed.

### 3. Output Exe Naming
**Recommendation**: `TwitchMarkerAgent.exe`
- Matches `APP_NAME` constant in `windows_startup.py`
- PascalCase for Windows exe convention
- Descriptive and discoverable

### 4. CI Trigger Pattern
**Recommendation**: Both tag pattern `v*` AND manual `workflow_dispatch`
- **Tags**: Automated releases for version tags (e.g., `v0.4.0`, `v1.0.0`)
- **Manual dispatch**: Allows testing/rebuilding without creating tags
- Standard GitHub Actions pattern

### 5. Existing CI/Workflows
**Answer**: No existing `.github/workflows/` directory
- Clean slate for new CI implementation

---

## Proposed Changes

### 1. No Public API Changes
This is a **packaging + infrastructure** task. No Python API changes.

### 2. Implementation Plan (Ordered Steps)

#### **Step 1: Create Build Script**
File: `scripts/build_exe.ps1`
- PowerShell script for local Windows builds
- Steps:
  1. Ensure clean environment
  2. Install PyInstaller as build-only tool (`pip install pyinstaller`)
  3. Run PyInstaller with configuration:
     - Entry point: `src\twitch_marker_agent\app.py`
     - Windowed mode (no console): `--noconsole`
     - One-file mode: `--onefile`
     - Name: `--name TwitchMarkerAgent`
     - Hidden imports for pystray/Pillow if needed
  4. Output to `dist\TwitchMarkerAgent.exe`

#### **Step 2: Create GitHub Actions Workflow**
File: `.github/workflows/release.yml`
- Triggers:
  - `push: tags: ['v*']`
  - `workflow_dispatch:`
- Jobs:
  1. **Setup**: Python 3.12 on `windows-latest`
  2. **Install**: `pip install -e .` + `pip install pyinstaller`
  3. **Test**: `python -m unittest discover -s tests -v`
  4. **Build**: Run PyInstaller build command
  5. **Artifact**: Upload `dist\TwitchMarkerAgent.exe` as workflow artifact
  6. **Release** (if tag): Attach exe to GitHub Release using `actions/upload-release-asset` or `softprops/action-gh-release`

#### **Step 3: Create Packaging Documentation**
File: `docs/packaging.md`
- Sections:
  1. **Overview**: What the build produces
  2. **Local Build**: How to run `scripts\build_exe.ps1`
  3. **CI Build**: How releases are automated
  4. **Distribution**: Where users download exe
  5. **Troubleshooting**: Common PyInstaller issues

#### **Step 4: Update Existing Documentation**
Files: `README.md`, `docs/handoff.md`
- **README.md** "Next Implementation Steps":
  - Change line 157: `10. [x] Add Windows startup integration`
  - Add: `11. [ ] Package as Windows exe (PyInstaller)`
  - Add: `12. [ ] Setup CI/CD for releases (GitHub Actions)`
- **docs/handoff.md** "Active Work / Next Steps":
  - Ensure consistency with README checklist

---

## Test Plan

### No New Unit Tests Required
This is infrastructure-only. Existing tests validate functionality.

### Manual Verification Steps
1. **Local build**:
   - Run `scripts\build_exe.ps1`
   - Verify `dist\TwitchMarkerAgent.exe` created
   - Double-click exe -> tray icon appears
   - Test manual fetch (requires auth setup)
   - Test auto mode start/stop
   - Test Windows startup toggle
   
2. **CI/CD**:
   - Push test tag (e.g., `v0.3.5-test`)
   - Verify workflow runs successfully
   - Download workflow artifact
   - Verify exe runs

3. **Release flow** (when ready):
   - Create real release tag (e.g., `v0.4.0`)
   - Verify GitHub Release created with attached exe
   - Download from Release page
   - Verify exe signature/integrity (future: code signing)

---

## Files to Change/Add (RUN 2)

### New Files
1. `scripts/build_exe.ps1` - Local build script
2. `.github/workflows/release.yml` - CI/CD pipeline
3. `docs/packaging.md` - Packaging documentation

### Modified Files
1. `README.md` - Update "Next Implementation Steps" checklist
2. `docs/handoff.md` - Update "Active Work / Next Steps" section

### No Changes To
- Python source code (`src/`)
- Tests (`tests/`)
- `pyproject.toml` (PyInstaller not added as runtime dependency)
- `config.json` schema

---

## Implementation Notes

### PyInstaller vs Nuitka
**Recommendation: PyInstaller**
- **Pros**: Industry standard, extensive pystray/Pillow support, simpler configuration
- **Cons**: Larger exe size, slower startup than Nuitka
- **Decision**: PyInstaller unless user requests Nuitka for specific reasons (speed, size)

### Icon Consideration
No `.ico` or `.png` files found in repo. Icon is generated at runtime via Pillow in `app.py` (lines ~52-60).
- **For now**: Skip icon in exe build (uses default)
- **Future**: Extract runtime-generated icon to `.ico` file and use `--icon` flag

### Hidden Imports
May need `--hidden-import` flags for:
- `pystray._win32` (Windows backend)
- `PIL._tkinter_finder` (if tkinter folder picker used)

Will test during RUN 2 and add if imports fail.

### Code Signing
Out of scope for this task. Future enhancement.
