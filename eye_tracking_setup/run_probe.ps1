$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$PythonExe = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    throw "Missing .venv. Run eye_tracking_setup\install_prerequisites.ps1 first."
}
& $PythonExe (Join-Path $PSScriptRoot "probe_eyetracker.py")
