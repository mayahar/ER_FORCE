param(
    [switch]$SkipDownloads,
    [switch]$SkipPython
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$VenvDir = Join-Path $RepoRoot ".venv-eye-tracking"
$PythonExe = Join-Path $VenvDir "Scripts\python.exe"

function Ensure-Python310 {
    $py310 = & py -3.10 -c "import sys; print(sys.executable)" 2>$null
    if (-not $py310) {
        Write-Host "Installing Python 3.10..."
        winget install --id Python.Python.3.10 --accept-package-agreements --accept-source-agreements
        $py310 = & py -3.10 -c "import sys; print(sys.executable)" 2>$null
    }
    if (-not $py310) {
        throw "Python 3.10 is required for Tobii Pro SDK bindings."
    }
    return $py310.Trim()
}

function Ensure-Venv {
    param([string]$Py310)
    if (-not (Test-Path $PythonExe)) {
        Write-Host "Creating virtual environment at $VenvDir"
        & $Py310 -m venv $VenvDir
    }
    & $PythonExe -m pip install --upgrade pip
    & $PythonExe -m pip install -r (Join-Path $PSScriptRoot "requirements.txt")
}

if (-not $SkipDownloads) {
    Write-Host "1/4 Tobii Pro desktop software (Fusion driver + Eye Tracker Manager)"
    Write-Host "   Opening download pages — install before continuing."
    $downloadPages = @(
        "https://connect.tobii.com/s/fusion-downloads?language=en_US",
        "https://connect.tobii.com/s/lab-downloads?language=en_US&p=tobii_pro_eye_tracker_manager",
        "https://www.tobii.com/products/software/applications-and-developer-kits/tobii-pro-eye-tracker-manager#downloads",
        "https://connect.tobii.com/s/sdk-downloads"
    )
    foreach ($url in $downloadPages) {
        Start-Process $url
    }
    Write-Host ""
    Write-Host "After installing, run: eye_tracking_setup\setup_colleague.cmd"
    Write-Host ""
}

if (-not $SkipPython) {
    Write-Host "Python 3.10 + virtual environment"
    $py310 = Ensure-Python310
    Ensure-Venv $py310
    Write-Host "OK  $VenvDir"

    Write-Host "Display mapping (for Tobii calibration)"
    & $PythonExe (Join-Path $PSScriptRoot "list_displays.py")
}
