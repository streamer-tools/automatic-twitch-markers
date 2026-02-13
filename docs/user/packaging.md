# Packaging Guide

Build instructions for creating the Windows executable (`TwitchMarkerAgent.exe`).

## Local Build (PowerShell)

### Prerequisites
- Python 3.12+
- Windows
- PowerShell 5.1+

### Build
```powershell
.\scripts\build_exe.ps1
```

Recommended seed:
```powershell
$env:TWITCH_MARKER_AGENT_CLIENT_ID = "your_real_client_id"
.\scripts\build_exe.ps1
```

Clean build:
```powershell
.\scripts\build_exe.ps1 -Clean
```

Dev-only placeholder override (do not distribute):
```powershell
.\scripts\build_exe.ps1 -AllowPlaceholderClientId
# or
$env:TWITCH_MARKER_AGENT_ALLOW_PLACEHOLDER_BUILD = "1"
.\scripts\build_exe.ps1
```

## Build Output
```text
dist/
└── TwitchMarkerAgent.exe
```

## CI/CD Release Build
GitHub Actions release workflow:
1. Runs tests.
2. Generates bootstrap config template.
3. Validates seeded non-placeholder `client_id`.
4. Builds exe via PyInstaller.
5. Publishes zipped artifact for release tags.

## Troubleshooting
- If PowerShell blocks scripts, use an execution policy that permits local script execution.
- If build cleanup fails, close processes holding `dist/` files.
- If runtime import errors occur, verify PyInstaller collect/hidden-import flags.

## Related Docs
- [Configuration](configuration.md)
- [Windows Startup](windows_startup.md)