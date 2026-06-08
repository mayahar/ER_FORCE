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
Write-Host "Installer folder: $InstallerRoot"

$Identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$Principal = New-Object Security.Principal.WindowsPrincipal($Identity)
if ($Principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host ""
    Write-Host "Warning: this installer is running as Administrator." -ForegroundColor Yellow
    Write-Host "The app and Desktop shortcut will be created for this Windows account."
    Write-Host "If this is not your normal user, close this window and run INSTALL_ON_WINDOWS.cmd normally."
}

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
$RequirementFiles = @(
    (Join-Path $InstallDir "requirements.txt"),
    (Join-Path $InstallDir "eye_tracking_setup\requirements.txt")
)
foreach ($RequirementFile in $RequirementFiles) {
    if (Test-Path $RequirementFile) {
        & $VenvPython -m pip install --no-index --find-links $Wheelhouse -r $RequirementFile
        if ($LASTEXITCODE -ne 0) {
            throw "pip install failed for $RequirementFile (exit $LASTEXITCODE)"
        }
    }
}

Write-Step "5/5 Creating desktop shortcut"
& $VenvPython (Join-Path $InstallDir "install\create_desktop_shortcut.py")
if ($LASTEXITCODE -ne 0) {
    Write-Host "Shortcut creation failed, but installation completed. You can run ERR_FORCE_fast.cmd manually." -ForegroundColor Yellow
}

$InstalledToFile = Join-Path $InstallerRoot "INSTALLED_TO.txt"
$RunFromHere = Join-Path $InstallerRoot "RUN_ERR_FORCE_FROM_INSTALLED_LOCATION.cmd"
Set-Content -Encoding UTF8 -Path $InstalledToFile -Value @(
    "ERR_FORCE installed to:",
    $InstallDir,
    "",
    "Launcher:",
    (Join-Path $InstallDir "ERR_FORCE_fast.cmd")
)
Set-Content -Encoding ASCII -Path $RunFromHere -Value @(
    "@echo off",
    "setlocal",
    "call `"$InstallDir\ERR_FORCE_fast.cmd`" %*",
    "exit /b %ERRORLEVEL%"
)

$DesktopRoot = [Environment]::GetFolderPath("Desktop")
$ToolsDir = Join-Path $DesktopRoot "ERR Force Tools"
New-Item -ItemType Directory -Force -Path $ToolsDir | Out-Null

function Write-ToolCmd([string]$Name, [string[]]$Lines) {
    Set-Content -Encoding ASCII -Path (Join-Path $ToolsDir $Name) -Value $Lines
}

Write-ToolCmd "Run ERR Force.cmd" @(
    "@echo off",
    "setlocal",
    "call `"$InstallDir\ERR_FORCE_fast.cmd`" %*",
    "exit /b %ERRORLEVEL%"
)
Write-ToolCmd "Verify Eye Tracker.cmd" @(
    "@echo off",
    "setlocal",
    "cd /d `"$InstallDir`"",
    "call scripts\VERIFY_EYE_TRACKER.cmd",
    "exit /b %ERRORLEVEL%"
)
Write-ToolCmd "Configure Joystick.cmd" @(
    "@echo off",
    "setlocal",
    "cd /d `"$InstallDir`"",
    "call scripts\CONFIGURE_JOYSTICK.cmd",
    "exit /b %ERRORLEVEL%"
)
Write-ToolCmd "Calibrate Microphone.cmd" @(
    "@echo off",
    "setlocal",
    "cd /d `"$InstallDir`"",
    "call scripts\CALIBRATE_MICROPHONE.cmd",
    "exit /b %ERRORLEVEL%"
)
Write-ToolCmd "Open Data Folder.cmd" @(
    "@echo off",
    "setlocal",
    "cd /d `"$InstallDir`"",
    "call scripts\OPEN_DATA_FOLDER.cmd",
    "exit /b %ERRORLEVEL%"
)
Write-ToolCmd "Open Reports Folder.cmd" @(
    "@echo off",
    "setlocal",
    "cd /d `"$InstallDir`"",
    "call scripts\OPEN_REPORTS_FOLDER.cmd",
    "exit /b %ERRORLEVEL%"
)
Write-ToolCmd "Open Install Folder.cmd" @(
    "@echo off",
    "start `"`" explorer `"$InstallDir`"",
    "exit /b 0"
)
Write-ToolCmd "Research Config Editor.cmd" @(
    "@echo off",
    "setlocal",
    "cd /d `"$InstallDir`"",
    "call scripts\OPEN_RESEARCH_CONFIG_EDITOR.cmd",
    "exit /b %ERRORLEVEL%"
)
Write-ToolCmd "Fatigue Weights Editor.cmd" @(
    "@echo off",
    "setlocal",
    "cd /d `"$InstallDir`"",
    "call scripts\OPEN_FATIGUE_WEIGHTS_EDITOR.cmd",
    "exit /b %ERRORLEVEL%"
)
Write-ToolCmd "Hardware Config Editor.cmd" @(
    "@echo off",
    "setlocal",
    "cd /d `"$InstallDir`"",
    "call scripts\OPEN_HARDWARE_CONFIG_EDITOR.cmd",
    "exit /b %ERRORLEVEL%"
)

$ProtocolSource = Join-Path $InstallDir "RESEARCHER_PROTOCOL_HE.txt"
if (Test-Path $ProtocolSource) {
    Copy-Item $ProtocolSource (Join-Path $ToolsDir "Researcher Protocol - Hebrew.txt") -Force
}

Write-Host ""
Write-Host "Installation completed." -ForegroundColor Green
Write-Host "Run:"
Write-Host "  $InstallDir\ERR_FORCE_fast.cmd"
Write-Host ""
Write-Host "Also created:"
Write-Host "  $InstalledToFile"
Write-Host "  $RunFromHere"
Write-Host "  $ToolsDir"
Write-Host ""
Write-Host "Note: Tobii device drivers / Eye Tracker Manager may still need to be installed from Tobii for the hardware to be detected."
