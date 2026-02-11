# PowerShell script to build TwitchMarkerAgent.exe using PyInstaller
# Run from repo root: .\scripts\build_exe.ps1

param(
    [switch]$Clean = $false
)

$ErrorActionPreference = "Stop"

Write-Host "=== Twitch Marker Agent - Build Script ===" -ForegroundColor Cyan

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

# Build exe with PyInstaller
Write-Host "Building TwitchMarkerAgent.exe..." -ForegroundColor Green
pyinstaller `
    --onefile `
    --noconsole `
    --name TwitchMarkerAgent `
    --paths src `
    --collect-submodules pystray `
    --collect-submodules PIL `
    --hidden-import pystray._win32 `
    --hidden-import ttkbootstrap `
    src\twitch_marker_agent\app.py

if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller build failed"
    exit 1
}

# Verify output
if (Test-Path "dist\TwitchMarkerAgent.exe") {
    $size = (Get-Item "dist\TwitchMarkerAgent.exe").Length / 1MB
    Write-Host "`nBuild successful!" -ForegroundColor Green
    Write-Host "Output: dist\TwitchMarkerAgent.exe ($([math]::Round($size, 2)) MB)" -ForegroundColor Cyan
} else {
    Write-Error "Build completed but exe not found at expected location"
    exit 1
}

Write-Host "`nTo test: .\dist\TwitchMarkerAgent.exe" -ForegroundColor Yellow
