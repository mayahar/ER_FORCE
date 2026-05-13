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

Write-Host "1/4 Tobii Pro desktop software (Fusion driver + Eye Tracker Manager)"
Write-Host "   Open Tobii download pages in your browser, then install both packages."
$downloadPages = @(
    "https://connect.tobii.com/s/fusion-downloads?language=en_US",
    "https://connect.tobii.com/s/lab-downloads?language=en_US&p=tobii_pro_eye_tracker_manager",
    "https://www.tobii.com/products/software/applications-and-developer-kits/tobii-pro-eye-tracker-manager#downloads"
)
foreach ($url in $downloadPages) {
    Start-Process $url
}

Write-Host "2/4 Tobii Pro SDK (native runtime + Python bindings)"
Write-Host "   Open the SDK download page, install the Windows SDK, then run sync_sdk_native.ps1."
Start-Process "https://connect.tobii.com/s/sdk-downloads"

$py310 = Ensure-Python310
Ensure-Venv $py310

Write-Host "3/4 Python 3.10 environment ready at $VenvDir"

Write-Host "4/4 Display mapping"
& $PythonExe (Join-Path $PSScriptRoot "list_displays.py")

Write-Host ""
Write-Host "Next steps:"
Write-Host "  - Install Tobii Pro Fusion support and Tobii Pro Eye Tracker Manager from the opened pages."
Write-Host "  - Sync SDK bindings: eye_tracking_setup\sync_sdk_native.cmd"
Write-Host "  - Calibrate in Eye Tracker Manager on the same monitor used for fullscreen FlightGear."
Write-Host "  - Verify hardware: eye_tracking_setup\run_probe.cmd"
