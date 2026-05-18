param(
    [string]$SourceRoot = (Join-Path ([Environment]::GetFolderPath("Desktop")) "TobiiProSDKPython\64")
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$TargetRoot = Join-Path $RepoRoot "TobiiPro_SDK"

if (-not (Test-Path $SourceRoot)) {
    throw "Tobii SDK source folder not found: $SourceRoot"
}

$pydSource = Join-Path $SourceRoot "tobiiresearch\interop\python3\tobii_research_interop.pyd"
if (-not (Test-Path $pydSource)) {
    throw "Missing tobii_research_interop.pyd under $SourceRoot"
}

New-Item -ItemType Directory -Force -Path $TargetRoot | Out-Null
Copy-Item -Path (Join-Path $SourceRoot "*") -Destination $TargetRoot -Recurse -Force

Write-Host "Synced Tobii Pro SDK Python bindings from $SourceRoot to $TargetRoot"
