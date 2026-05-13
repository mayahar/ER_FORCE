$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$TargetDir = Join-Path $RepoRoot "TobiiPro_SDK\tobiiresearch\interop\python3"
$SearchRoots = @(
    "$env:LOCALAPPDATA\Programs",
    "$env:ProgramFiles",
    "${env:ProgramFiles(x86)}"
)

New-Item -ItemType Directory -Force -Path $TargetDir | Out-Null

$matches = @()
foreach ($root in $SearchRoots) {
    if (-not (Test-Path $root)) { continue }
    $matches += Get-ChildItem -Path $root -Recurse -Filter "tobii_research_interop*.pyd" -ErrorAction SilentlyContinue
}

if ($matches.Count -eq 0) {
    throw "No tobii_research_interop*.pyd found. Install Tobii Pro SDK for Windows first."
}

$source = $matches | Sort-Object LastWriteTime -Descending | Select-Object -First 1
Copy-Item -Force $source.FullName (Join-Path $TargetDir $source.Name)

$dllMatches = @()
foreach ($root in $SearchRoots) {
    if (-not (Test-Path $root)) { continue }
    $dllMatches += Get-ChildItem -Path $root -Recurse -Filter "tobii_research.dll" -ErrorAction SilentlyContinue
}
if ($dllMatches.Count -gt 0) {
    $dll = $dllMatches | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    Copy-Item -Force $dll.FullName (Join-Path $TargetDir $dll.Name)
}

Write-Host "Copied native Tobii SDK files from $($source.FullName) to $TargetDir"
