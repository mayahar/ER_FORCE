param(
    [switch]$OpenDownloads,
    [string]$SdkSourceRoot = $env:TOBII_SDK_SOURCE
)

$ErrorActionPreference = "Stop"
$ScriptDir = $PSScriptRoot
$RepoRoot = Split-Path -Parent $ScriptDir
$VenvDir = Join-Path $RepoRoot ".venv-eye-tracking"
$PythonExe = Join-Path $VenvDir "Scripts\python.exe"
$InteropPyd = Join-Path $RepoRoot "TobiiPro_SDK\tobiiresearch\interop\python3\tobii_research_interop.pyd"
$RecordingsDir = Join-Path $RepoRoot "eye_tracking_analysis\recordings"

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Ensure-Python310 {
    $py310 = & py -3.10 -c "import sys; print(sys.executable)" 2>$null
    if (-not $py310) {
        Write-Host "Python 3.10 not found. Install it, then re-run this script." -ForegroundColor Yellow
        Write-Host "  winget install --id Python.Python.3.10"
        throw "Missing Python 3.10"
    }
    return $py310.Trim()
}

function Ensure-Venv {
    param([string]$Py310)
    if (-not (Test-Path $PythonExe)) {
        Write-Host "Creating virtual environment: $VenvDir"
        & $Py310 -m venv $VenvDir
    }
    & $PythonExe -m pip install --upgrade pip -q
    & $PythonExe -m pip install -r (Join-Path $ScriptDir "requirements.txt") -q
}

function Open-FirstTimeDownloads {
    Write-Host "Opening Tobii download pages (first-time setup)..."
    @(
        "https://connect.tobii.com/s/fusion-downloads?language=en_US",
        "https://connect.tobii.com/s/lab-downloads?language=en_US&p=tobii_pro_eye_tracker_manager",
        "https://connect.tobii.com/s/sdk-downloads"
    ) | ForEach-Object { Start-Process $_ }
}

function Sync-SdkNative {
    param([string]$SourceRoot)
    if (-not $SourceRoot) {
        $SourceRoot = Join-Path ([Environment]::GetFolderPath("Desktop")) "TobiiProSDKPython\64"
    }
    $syncScript = Join-Path $ScriptDir "sync_sdk_native.ps1"
    & $syncScript -SourceRoot $SourceRoot
}

Write-Host "ER_FORCE eye-tracking setup check"
Write-Host "Repo: $RepoRoot"

if ($OpenDownloads) {
    Open-FirstTimeDownloads
}

Write-Step "1/5 Python 3.10 virtual environment"
$py310 = Ensure-Python310
Ensure-Venv $py310
Write-Host "OK  $PythonExe"

Write-Step "2/5 Tobii Pro SDK native bindings (tobii_research_interop.pyd)"
if (Test-Path $InteropPyd) {
    Write-Host "OK  $InteropPyd"
} else {
    Write-Host "Missing native binding. Trying sync_sdk_native..." -ForegroundColor Yellow
    try {
        Sync-SdkNative -SourceRoot $SdkSourceRoot
    } catch {
        Write-Host ""
        Write-Host "Could not sync SDK bindings." -ForegroundColor Red
        Write-Host "  1) Install Tobii Pro SDK for Windows from Tobii download page"
        Write-Host "  2) Re-run: eye_tracking_setup\verify_eye_tracking.cmd"
        Write-Host "  Or set TOBII_SDK_SOURCE to your SDK folder, e.g.:"
        Write-Host "    set TOBII_SDK_SOURCE=C:\Path\To\TobiiProSDKPython\64"
        throw
    }
    if (-not (Test-Path $InteropPyd)) {
        throw "Sync finished but $InteropPyd is still missing."
    }
    Write-Host "OK  synced to $InteropPyd"
}

Write-Step "3/5 Python import test (tobii_research + eye_tracker_recorder)"
$importTest = @"
import sys
from pathlib import Path
root = Path(r'$RepoRoot').resolve()
for p in (str(root), str(root / 'TobiiPro_SDK')):
    if p not in sys.path:
        sys.path.insert(0, p)
import tobii_research as tr
from eye_tracking_analysis.eye_tracker_recorder import EyeTrackerRecorder
print('tobii_research', tr.__version__)
print('EyeTrackerRecorder', EyeTrackerRecorder)
"@
& $PythonExe -c $importTest
if ($LASTEXITCODE -ne 0) {
    throw "Import test failed."
}
Write-Host "OK  imports"

Write-Step "4/5 Hardware probe (USB / Tobii device)"
& $PythonExe (Join-Path $ScriptDir "probe_eyetracker.py")
$probeExit = $LASTEXITCODE

Write-Step "5/5 Recording folder"
New-Item -ItemType Directory -Force -Path $RecordingsDir | Out-Null
Write-Host "Raw gaze exports will be saved under:"
Write-Host "  $RecordingsDir"

Write-Host ""
Write-Host "----------------------------------------"
if ($probeExit -eq 0) {
    Write-Host "SUCCESS: Eye tracking is ready." -ForegroundColor Green
    Write-Host "Start the app with: eye_tracking_setup\run_app.cmd"
    Write-Host "On the game screen, after start you should see:"
    Write-Host "  (blue) eye recording active message"
    Write-Host "Calibrate in Tobii Pro Eye Tracker Manager on the FlightGear monitor."
    exit 0
}

if ($probeExit -eq 2) {
    Write-Host "SETUP OK, BUT NO TRACKER FOUND." -ForegroundColor Yellow
    Write-Host "Check USB, Tobii Fusion driver, and Eye Tracker Manager."
    Write-Host "Then re-run: eye_tracking_setup\verify_eye_tracking.cmd"
    exit 2
}

Write-Host "PROBE FAILED (exit $probeExit). See messages above." -ForegroundColor Red
exit $probeExit
