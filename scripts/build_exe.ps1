# PowerShell script to build "Automatic Twitch Markers.exe" using PyInstaller
# Run from repo root: .\scripts\build_exe.ps1

param(
    [switch]$Clean = $false,
    [switch]$AllowPlaceholderClientId = $false
)

$ErrorActionPreference = "Stop"

Write-Host "=== Automatic Twitch Markers - Build Script ===" -ForegroundColor Cyan

# Ensure we're in repo root
if (-not (Test-Path "pyproject.toml")) {
    Write-Error "Must run from repository root (where pyproject.toml exists)"
    exit 1
}

# Clean previous builds if requested
if ($Clean) {
    Write-Host "Cleaning previous builds..." -ForegroundColor Yellow
    if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
    if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }
    if (Test-Path "*.spec") { Remove-Item -Force "*.spec" }
}

# Install project in editable mode
Write-Host "Installing project dependencies..." -ForegroundColor Green
pip install -e .
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to install project"
    exit 1
}

# Install PyInstaller (build-only tool)
Write-Host "Installing PyInstaller..." -ForegroundColor Green
pip install pyinstaller
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to install PyInstaller"
    exit 1
}

# Generate bootstrap config template for packaging
Write-Host "Generating bootstrap config template..." -ForegroundColor Green
$allowPlaceholderBuild = $AllowPlaceholderClientId -or ($env:TWITCH_MARKER_AGENT_ALLOW_PLACEHOLDER_BUILD -eq "1")
python -c "from pathlib import Path; import os; from twitch_marker_agent.core.config import resolve_client_id_seed, write_bootstrap_template; seed = resolve_client_id_seed(os.getenv('TWITCH_MARKER_AGENT_CLIENT_ID'), local_config_path=Path('local.config.json')); Path('build').mkdir(parents=True, exist_ok=True); write_bootstrap_template(Path('build/config.bootstrap.json'), client_id_seed=seed)"
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to generate bootstrap config template"
    exit 1
}

if (-not $allowPlaceholderBuild) {
    Write-Host "Validating bootstrap client_id..." -ForegroundColor Green
    python -c "import json, sys; from pathlib import Path; from twitch_marker_agent.core.config import is_placeholder_client_id; data = json.loads(Path('build/config.bootstrap.json').read_text(encoding='utf-8')); client_id = str(data.get('client_id', '')).strip(); ok = not is_placeholder_client_id(client_id); print('Build blocked: bootstrap client_id is placeholder. Set TWITCH_MARKER_AGENT_CLIENT_ID or set client_id in local.config.json.', file=sys.stderr) if not ok else None; sys.exit(0 if ok else 1)"
    if ($LASTEXITCODE -ne 0) {
        exit 1
    }
} else {
    Write-Warning "Placeholder client_id build allowed by override. Do not distribute this build."
}

# Build exe with PyInstaller
Write-Host "Building Automatic Twitch Markers.exe..." -ForegroundColor Green
pyinstaller `
    --onefile `
    --noconsole `
    --name "Automatic Twitch Markers" `
    --paths src `
    --collect-submodules pystray `
    --collect-submodules PIL `
    --hidden-import pystray._win32 `
    --hidden-import ttkbootstrap `
    --add-data "build\config.bootstrap.json;bootstrap" `
    src\twitch_marker_agent\app.py

if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller build failed"
    exit 1
}

# Verify output
if (Test-Path "dist\Automatic Twitch Markers.exe") {
    $size = (Get-Item "dist\Automatic Twitch Markers.exe").Length / 1MB
    Write-Host "`nBuild successful!" -ForegroundColor Green
    Write-Host "Output: dist\Automatic Twitch Markers.exe ($([math]::Round($size, 2)) MB)" -ForegroundColor Cyan
} else {
    Write-Error "Build completed but exe not found at expected location"
    exit 1
}

Write-Host "`nTo test: .\dist\'Automatic Twitch Markers.exe'" -ForegroundColor Yellow
