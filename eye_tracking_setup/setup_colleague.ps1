# One-shot colleague setup: Python venv, Tobii SDK sync, imports, hardware probe.
# Usage:
#   setup_colleague.cmd              - routine check (tracker must be connected)
#   setup_colleague.cmd -FirstTime   - also open Tobii download pages in browser

param(
    [Alias("FirstTime")]
    [switch]$OpenDownloads,
    [string]$SdkSourceRoot = $env:TOBII_SDK_SOURCE
)

$ErrorActionPreference = "Stop"
$ScriptDir = $PSScriptRoot
$RepoRoot = Split-Path -Parent $ScriptDir

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host " ER_FORCE - colleague eye-tracking setup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Repo: $RepoRoot"
Write-Host ""

if ($OpenDownloads) {
    Write-Host "Step A: First-time Tobii software (install from browser tabs)..." -ForegroundColor Cyan
    & (Join-Path $ScriptDir "install_prerequisites.ps1") -SkipPython
    Write-Host ""
}

Write-Host "Step B: Python environment + pip packages..." -ForegroundColor Cyan
& (Join-Path $ScriptDir "install_prerequisites.ps1") -SkipDownloads

Write-Host ""
Write-Host "Step C: SDK sync, imports, hardware probe..." -ForegroundColor Cyan
& (Join-Path $ScriptDir "verify_eye_tracking.ps1") -SdkSourceRoot $SdkSourceRoot

exit $LASTEXITCODE
