[CmdletBinding()]
param(
    [string]$InstallDir = "$env:LOCALAPPDATA\ER_FORCE"
)

$ErrorActionPreference = "Stop"
$InstallerRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PayloadRoot = Join-Path $InstallerRoot "payload"
$AppPayload = Join-Path $PayloadRoot "app"
$Wheelhouse = Join-Path $PayloadRoot "wheelhouse"
$PythonInstaller = Get-ChildItem -Path $PayloadRoot -Filter "python-3.10.*-amd64.exe" | Select-Object -First 1

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Invoke-Robocopy([string]$Source, [string]$Destination) {
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    robocopy $Source $Destination /E /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -gt 7) {
        throw "robocopy failed for $Source -> $Destination (exit $LASTEXITCODE)"
    }
}

if (-not (Test-Path $AppPayload)) {
    throw "Missing installer payload: $AppPayload"
}
if (-not (Test-Path $Wheelhouse)) {
    throw "Missing installer wheelhouse: $Wheelhouse"
}
if (-not $PythonInstaller) {
    throw "Missing bundled Python 3.10 installer under $PayloadRoot"
}

$InstallDir = [System.IO.Path]::GetFullPath($InstallDir)
$RuntimeDir = Join-Path $InstallDir "runtime\Python310"
$RuntimePython = Join-Path $RuntimeDir "python.exe"
$VenvPython = Join-Path $InstallDir ".venv\Scripts\python.exe"

Write-Host ""
Write-Host "ER_FORCE offline installer"
Write-Host "Install directory: $InstallDir"

Write-Step "1/5 Copying ER_FORCE files and game data"
Invoke-Robocopy $AppPayload $InstallDir

Write-Step "2/5 Installing bundled Python 3.10 runtime"
if (-not (Test-Path $RuntimePython)) {
    New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null
    $quotedRuntimeDir = '"' + $RuntimeDir + '"'
    $args = "/quiet InstallAllUsers=0 TargetDir=$quotedRuntimeDir Include_pip=1 Include_launcher=0 PrependPath=0 Include_test=0 Shortcuts=0"
    $proc = Start-Process -FilePath $PythonInstaller.FullName -ArgumentList $args -Wait -PassThru
    if ($proc.ExitCode -ne 0) {
        throw "Python installer failed (exit $($proc.ExitCode))"
    }
} else {
    Write-Host "Python runtime already exists: $RuntimePython"
}

Write-Step "3/5 Creating Python 3.10 virtual environment"
if (-not (Test-Path $VenvPython)) {
    & $RuntimePython -m venv (Join-Path $InstallDir ".venv")
    if ($LASTEXITCODE -ne 0) {
        throw "venv creation failed (exit $LASTEXITCODE)"
    }
}

Write-Step "4/5 Installing Python packages from offline wheelhouse"
& $VenvPython -m pip install --no-index --find-links $Wheelhouse -r (Join-Path $InstallDir "requirements.txt")
if ($LASTEXITCODE -ne 0) {
    throw "pip install failed (exit $LASTEXITCODE)"
}

Write-Step "5/5 Creating desktop shortcut"
& $VenvPython (Join-Path $InstallDir "install\create_desktop_shortcut.py")
if ($LASTEXITCODE -ne 0) {
    Write-Host "Shortcut creation failed, but installation completed. You can run ER_FORCE.exe manually." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Installation completed." -ForegroundColor Green
Write-Host "Run:"
Write-Host "  $InstallDir\ER_FORCE.exe"
Write-Host ""
Write-Host "Note: Tobii device drivers / Eye Tracker Manager may still need to be installed from Tobii for the hardware to be detected."
