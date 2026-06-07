# Builds an offline installer folder under dist\ER_FORCE_Installer.
# The resulting folder can be copied to another Windows PC and installed
# without Python already being present on that PC.
[CmdletBinding()]
param(
    [string]$RepoRoot = "",
    [string]$OutDir = "",
    [string]$PythonVersion = "3.10.11"
)

$ErrorActionPreference = "Stop"

$InstallDir = $PSScriptRoot
if ([string]::IsNullOrEmpty($RepoRoot)) {
    $RepoRoot = (Resolve-Path (Join-Path $InstallDir "..")).Path
} else {
    $RepoRoot = (Resolve-Path $RepoRoot).Path
}
if ([string]::IsNullOrEmpty($OutDir)) {
    $OutDir = Join-Path $RepoRoot "dist\ER_FORCE_Installer"
}

$PayloadDir = Join-Path $OutDir "payload"
$AppDir = Join-Path $PayloadDir "app"
$Wheelhouse = Join-Path $PayloadDir "wheelhouse"
$PythonInstaller = Join-Path $PayloadDir "python-$PythonVersion-amd64.exe"
$PythonUrl = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-amd64.exe"

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Find-Python310 {
    foreach ($cand in @(
        (Join-Path $RepoRoot ".venv\Scripts\python.exe"),
        (Join-Path $RepoRoot ".venv-eye-tracking\Scripts\python.exe"),
        (Join-Path $RepoRoot "venv\Scripts\python.exe")
    )) {
        if (Test-Path $cand) {
            $version = & $cand -c "import sys; print('.'.join(map(str, sys.version_info[:2])))"
            if ($LASTEXITCODE -eq 0 -and $version.Trim() -eq "3.10") {
                return $cand
            }
        }
    }
    $py310 = & py -3.10 -c "import sys; print(sys.executable)" 2>$null
    if ($LASTEXITCODE -eq 0 -and $py310) {
        return $py310.Trim()
    }
    throw "Python 3.10 is required on the build machine. Run eye_tracking_setup\setup_colleague.cmd first."
}

function Copy-Tree([string]$Source, [string]$Destination) {
    if (-not (Test-Path $Source)) {
        throw "Required source path is missing: $Source"
    }
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    robocopy $Source $Destination /E /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -gt 7) {
        throw "robocopy failed for $Source -> $Destination (exit $LASTEXITCODE)"
    }
}

Write-Step "Preparing output folder"
if (Test-Path $OutDir) {
    Remove-Item -LiteralPath $OutDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $AppDir, $Wheelhouse | Out-Null

Write-Step "Copying application payload, including game"
$dirs = @(
    "core",
    "Editors",
    "eye_tracking_analysis",
    "eye_tracking_setup",
    "game",
    "install",
    "score",
    "ui",
    "voice"
)
foreach ($dir in $dirs) {
    Copy-Tree (Join-Path $RepoRoot $dir) (Join-Path $AppDir $dir)
}

$files = @(
    "ERR_FORCE.exe",
    "ERR_FORCE_fast.cmd",
    "CONFIGURE_JOYSTICK.cmd",
    "fatigue_features_editor.exe",
    "fatigue_protoype.bat",
    "OPEN_DATA_FOLDER.cmd",
    "OPEN_FATIGUE_WEIGHTS_EDITOR.cmd",
    "OPEN_INSTALL_FOLDER.cmd",
    "OPEN_REPORTS_FOLDER.cmd",
    "OPEN_RESEARCH_CONFIG_EDITOR.cmd",
    "RESEARCHER_PROTOCOL_HE.txt",
    "research_config_editor.exe",
    "requirements.txt",
    "README.md",
    "VERIFY_EYE_TRACKER.cmd",
    "__init__.py"
)
foreach ($file in $files) {
    $src = Join-Path $RepoRoot $file
    if (Test-Path $src) {
        Copy-Item $src (Join-Path $AppDir $file) -Force
    }
}

Write-Step "Copying installer scripts"
Get-ChildItem -Path (Join-Path $InstallDir "offline_installer") -File | ForEach-Object {
    Copy-Item $_.FullName (Join-Path $OutDir $_.Name) -Force
}

Write-Step "Downloading Python $PythonVersion offline installer"
Invoke-WebRequest -Uri $PythonUrl -OutFile $PythonInstaller

Write-Step "Downloading pip wheelhouse for Python 3.10"
$Python = Find-Python310
Write-Host "Using build Python: $Python"
$RequirementFiles = @(
    (Join-Path $RepoRoot "requirements.txt"),
    (Join-Path $RepoRoot "eye_tracking_setup\requirements.txt")
)
foreach ($RequirementFile in $RequirementFiles) {
    if (Test-Path $RequirementFile) {
        & $Python -m pip download `
            --dest $Wheelhouse `
            --only-binary=:all: `
            --platform win_amd64 `
            --implementation cp `
            --python-version 310 `
            --abi cp310 `
            -r $RequirementFile
        if ($LASTEXITCODE -ne 0) {
            throw "pip download failed for $RequirementFile (exit $LASTEXITCODE)"
        }
    }
}

Write-Step "Writing manifest"
$manifest = [ordered]@{
    name = "ERR_FORCE"
    built_at = (Get-Date).ToString("s")
    python_version = $PythonVersion
    includes_game = $true
    install_entrypoint = "INSTALL_ON_WINDOWS.cmd"
    launcher = "ERR_FORCE_fast.cmd"
}
$manifest | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 (Join-Path $OutDir "manifest.json")

Write-Host ""
Write-Host "Offline installer folder is ready:" -ForegroundColor Green
Write-Host "  $OutDir"
Write-Host ""
Write-Host "Copy this whole folder to the target PC and run install_app.cmd."
