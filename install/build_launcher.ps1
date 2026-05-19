# Builds ER_FORCE.exe at the repo root using PyInstaller.
# Run with: install\build_launcher.cmd
[CmdletBinding()]
param(
    [string]$RepoRoot = ""
)

$ErrorActionPreference = "Stop"

$InstallDir = $PSScriptRoot
if ([string]::IsNullOrEmpty($InstallDir)) {
    $InstallDir = Split-Path -Parent $MyInvocation.MyCommand.Path
}
if ([string]::IsNullOrEmpty($InstallDir)) {
    throw "Could not determine script directory."
}

if ([string]::IsNullOrEmpty($RepoRoot)) {
    $RepoRoot = (Resolve-Path (Join-Path $InstallDir "..")).Path
}
$LauncherPy   = Join-Path $InstallDir "er_force_launcher.py"
$MakeIconPy   = Join-Path $InstallDir "make_icon.py"
$AssetsDir    = Join-Path $InstallDir "assets"
$IconPng      = Join-Path $AssetsDir "er_force_icon.png"
$IconIco      = Join-Path $AssetsDir "er_force_icon.ico"
$BuildOut     = Join-Path $RepoRoot "build\pyinstaller-er-force"
$DistOut      = Join-Path $RepoRoot "dist"
$FinalExe     = Join-Path $RepoRoot "ER_FORCE.exe"

function Find-Python {
    foreach ($cand in @(
        (Join-Path $RepoRoot ".venv-eye-tracking\Scripts\python.exe"),
        (Join-Path $RepoRoot "venv\Scripts\python.exe")
    )) {
        if (Test-Path $cand) { return $cand }
    }
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    throw "No Python interpreter found. Run eye_tracking_setup\setup_colleague.cmd first."
}

$Python = Find-Python
Write-Host "Using Python: $Python"

Write-Host "Ensuring PyInstaller + Pillow are installed..."
& $Python -m pip install --quiet --upgrade pyinstaller pillow
if ($LASTEXITCODE -ne 0) { throw "pip install failed (exit $LASTEXITCODE)" }

if (-not (Test-Path $IconIco) -or ((Get-Item $IconPng).LastWriteTime -gt (Get-Item $IconIco).LastWriteTime)) {
    Write-Host "Generating er_force_icon.ico from PNG..."
    & $Python $MakeIconPy
    if ($LASTEXITCODE -ne 0) { throw "make_icon.py failed (exit $LASTEXITCODE)" }
}

if (Test-Path $FinalExe) {
    Write-Host "Removing previous ER_FORCE.exe..."
    Remove-Item $FinalExe -Force -ErrorAction SilentlyContinue
}

Write-Host "Running PyInstaller..."
& $Python -m PyInstaller `
    --noconfirm --onefile --windowed `
    --name ER_FORCE `
    --icon $IconIco `
    --distpath $DistOut `
    --workpath $BuildOut `
    --specpath $InstallDir `
    $LauncherPy
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed (exit $LASTEXITCODE)" }

$Built = Join-Path $DistOut "ER_FORCE.exe"
if (-not (Test-Path $Built)) { throw "Build did not produce $Built" }

Copy-Item $Built $FinalExe -Force
Write-Host ""
Write-Host "ER_FORCE.exe is ready at:"
Write-Host "  $FinalExe"
