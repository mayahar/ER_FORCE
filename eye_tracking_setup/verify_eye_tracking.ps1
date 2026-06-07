[CmdletBinding()]
param(
    [string]$SdkSourceRoot = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$PythonCandidates = @(
    (Join-Path $RepoRoot ".venv\Scripts\python.exe"),
    (Join-Path $RepoRoot ".venv-eye-tracking\Scripts\python.exe"),
    (Join-Path $RepoRoot "venv\Scripts\python.exe")
)

$PythonExe = $PythonCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $PythonExe) {
    Write-Host "Missing Python environment under $RepoRoot." -ForegroundColor Red
    Write-Host "Run the installer again or run eye_tracking_setup\setup_colleague.cmd."
    exit 1
}

Write-Host "Using Python: $PythonExe"
& $PythonExe (Join-Path $PSScriptRoot "probe_eyetracker.py")
$Rc = $LASTEXITCODE
if ($Rc -eq 0) {
    exit 0
}
if ($Rc -eq 2) {
    exit 2
}
exit 1
