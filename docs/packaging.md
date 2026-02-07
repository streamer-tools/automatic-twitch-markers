# Packaging Guide

This document describes how to build the Windows executable for Twitch Marker Agent.

## Overview

The project uses [PyInstaller](https://pyinstaller.org/) to create a standalone Windows executable (`TwitchMarkerAgent.exe`) that bundles Python, all dependencies, and the tray application into a single file.

**Output**: `dist/TwitchMarkerAgent.exe` (single-file, no-console tray app)

---

## Local Build (PowerShell)

### Prerequisites
- Python 3.12 or higher
- Windows OS
- PowerShell 5.1 or higher

### Build Steps

1. **Navigate to repository root**:
   ```powershell
   cd C:\path\to\automatic-twitch-markers
   ```

2. **Run build script**:
   ```powershell
   .\scripts\build_exe.ps1
   ```

3. **Clean build** (optional, removes previous build artifacts):
   ```powershell
   .\scripts\build_exe.ps1 -Clean
   ```

### What the Script Does
- Installs project in editable mode (`pip install -e .`)
- Installs PyInstaller as a build-only tool
- Runs PyInstaller with:
  - `--onefile`: Single executable
  - `--noconsole`: No console window (windowed app)
  - `--name TwitchMarkerAgent`: Output name
  - `--collect-submodules pystray,PIL`: Bundle tray/image libraries
  - Entry point: `src\twitch_marker_agent\app.py`

### Output Location
```
dist/
└── TwitchMarkerAgent.exe
```

### Testing the Build
```powershell
.\dist\TwitchMarkerAgent.exe
```
- Tray icon should appear in system tray
- Right-click for menu (Auto Mode, Fetch Markers, etc.)
- Requires `local.config.json` with valid Twitch credentials

---

## CI/CD Build (GitHub Actions)

### Automated releases triggered by:
- **Git tags** matching `v*` (e.g., `v0.4.0`, `v1.0.0`)
- **Manual dispatch** via GitHub Actions UI

### Workflow Steps
1. Checkout code
2. Setup Python 3.12 on Windows runner
3. Install project dependencies
4. Run full test suite (`python -m unittest discover -s tests -v`)
5. Install PyInstaller
6. Build exe with same configuration as local script
7. Package as `TwitchMarkerAgent-windows.zip`
8. Upload workflow artifact (always)
9. Attach zip to GitHub Release (only for tag builds)

### Accessing Build Artifacts

**For any build** (tag or manual):
- Go to Actions tab → Click workflow run → Download artifact

**For tagged releases**:
- Go to Releases page → Download `TwitchMarkerAgent-windows.zip`

---

## Troubleshooting

### "Module not found" errors at runtime
**Symptom**: Exe builds successfully but crashes with import errors when run.

**Solution**: Add missing module to `--collect-submodules` or `--hidden-import` in both:
- `scripts/build_exe.ps1`
- `.github/workflows/release.yml`

Example:
```powershell
--hidden-import some_module
```

### Exe crashes immediately (no error visible)
**Symptom**: Double-clicking exe does nothing; no tray icon appears.

**Cause**: `--noconsole` hides crash output.

**Debug**:
1. Temporarily remove `--noconsole` from build script
2. Rebuild exe
3. Run exe from PowerShell to see error messages:
   ```powershell
   .\dist\TwitchMarkerAgent.exe
   ```

### Pystray/PIL bundling issues
**Symptom**: Tray icon doesn't appear; errors about `PIL` or `pystray`.

**Solution**: Verify these flags are present:
```powershell
--collect-submodules pystray
--collect-submodules PIL
--hidden-import pystray._win32
```

### Large exe size
**Expected**: ~30-50 MB (includes Python runtime + all dependencies)

**Optimization** (if needed):
- Use `--exclude-module` to remove unused stdlib modules
- Consider switching to Nuitka for smaller binaries (future enhancement)

### Build fails in CI but works locally
**Check**:
1. Python version matches (3.12)
2. Dependencies are pinned or compatible across environments
3. Paths use forward slashes or backslashes consistently for Windows

---

## Build Configuration Details

### PyInstaller Command (Full)
```powershell
pyinstaller `
    --onefile `
    --noconsole `
    --name TwitchMarkerAgent `
    --paths src `
    --collect-submodules pystray `
    --collect-submodules PIL `
    --hidden-import pystray._win32 `
    src\twitch_marker_agent\app.py
```

### Entry Point
- **Module**: `twitch_marker_agent.app`
- **Function**: `main()` (called via `if __name__ == "__main__"`)
- **Behavior**: Loads config, initializes dependencies, runs tray app

### No Icon File
The tray icon is generated at runtime via Pillow (see `create_icon()` in `app.py`). Future enhancement: extract to `.ico` file and use `--icon` flag.

---

## Future Enhancements
- [ ] Code signing (Windows Authenticode)
- [ ] Icon file (`.ico`) for branded exe
- [ ] Nuitka builds for smaller/faster binaries
- [ ] Multi-platform builds (macOS/Linux tray apps)
