param(
    [switch]$SkipVenv,
    [switch]$SkipDockerCheck
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Write-Host "RepoScan Pro bootstrap"
Write-Host "Repo root: $RepoRoot"

$pythonVersions = (& py -0p) -join "`n"
if ($LASTEXITCODE -ne 0 -or $pythonVersions -notmatch "3\.11") {
    throw "Python 3.11 is required. Install it and rerun this script."
}

if (-not $SkipVenv) {
    $venvPath = Join-Path $RepoRoot ".venv"
    if (-not (Test-Path $venvPath)) {
        & py -3.11 -m venv $venvPath
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to create the Python 3.11 virtual environment."
        }
        Write-Host "Created Python 3.11 virtual environment at $venvPath"
    } else {
        Write-Host "Virtual environment already exists at $venvPath"
    }
}

$runtimeDirs = @("data", "artifacts", "media", "logs", "runtime")
foreach ($dir in $runtimeDirs) {
    New-Item -ItemType Directory -Force -Path (Join-Path $RepoRoot $dir) | Out-Null
}
Write-Host "Ensured local runtime directories exist."

if (-not $SkipDockerCheck) {
    & docker compose version | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose is required for local infrastructure services."
    }
    Write-Host "Docker Compose is available."
}

Write-Host "Bootstrap complete."
Write-Host "Next step: review CLAUDE.md and docs before writing implementation code."
