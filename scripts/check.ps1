Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$requiredFiles = @(
    "CLAUDE.md",
    "README.md",
    ".vscode/settings.json",
    ".vscode/extensions.json",
    "RepoScan Pro.code-workspace",
    "Open RepoScan Pro Dev.cmd",
    ".claude/settings.json",
    ".claude/settings.local.json",
    "package.json",
    "pyproject.toml",
    "docker-compose.yml",
    "scripts/create_desktop_launcher.ps1",
    "docs/PRODUCT.md",
    "docs/ARCHITECTURE.md",
    "docs/IMPLEMENTATION_BLUEPRINT.md",
    "docs/REQUIREMENTS.md",
    "docs/CAMERA_AND_IMAGING.md",
    "docs/MODELS.md",
    "docs/DATASETS.md",
    "docs/TRAINING.md",
    "docs/INFERENCE.md",
    "docs/DEPLOYMENT.md",
    "docs/API_CONTRACTS.md",
    "docs/UI_WORKFLOWS.md",
    "docs/DECISIONS.md"
)

$missing = @()
foreach ($relativePath in $requiredFiles) {
    $fullPath = Join-Path $RepoRoot $relativePath
    if (-not (Test-Path $fullPath)) {
        $missing += $relativePath
    }
}

if ($missing.Count -gt 0) {
    throw "Missing required files:`n$($missing -join "`n")"
}

$jsonFiles = @(
    (Join-Path $RepoRoot ".claude/settings.json"),
    (Join-Path $RepoRoot ".claude/settings.local.json"),
    (Join-Path $RepoRoot "package.json")
)

foreach ($jsonFile in $jsonFiles) {
    Get-Content -Raw $jsonFile | ConvertFrom-Json | Out-Null
}

$markdownFiles = Get-ChildItem -Path $RepoRoot -Recurse -File -Filter *.md
$linkPattern = '\[[^\]]+\]\(([^)]+)\)'
$brokenLinks = @()

foreach ($file in $markdownFiles) {
    $content = Get-Content -Raw $file.FullName
    foreach ($match in [regex]::Matches($content, $linkPattern)) {
        $target = $match.Groups[1].Value
        if (
            $target.StartsWith("http://") -or
            $target.StartsWith("https://") -or
            $target.StartsWith("mailto:") -or
            $target.StartsWith("#")
        ) {
            continue
        }

        $normalizedTarget = $target.Split("#")[0]
        if ([string]::IsNullOrWhiteSpace($normalizedTarget)) {
            continue
        }

        $resolvedPath = [System.IO.Path]::GetFullPath((Join-Path $file.DirectoryName $normalizedTarget))
        if (-not (Test-Path $resolvedPath)) {
            $brokenLinks += "$($file.FullName) -> $target"
        }
    }
}

if ($brokenLinks.Count -gt 0) {
    throw "Broken markdown links:`n$($brokenLinks -join "`n")"
}

& docker compose -f (Join-Path $RepoRoot "docker-compose.yml") config | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "docker compose config failed."
}

Write-Host "RepoScan Pro checks passed."
