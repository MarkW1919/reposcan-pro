Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$DesktopPath = [Environment]::GetFolderPath("Desktop")
$DevHomePath = Join-Path $DesktopPath "RepoScan Pro Dev Home"
$StartHerePath = Join-Path $DevHomePath "START HERE.txt"
$DesktopCmdPath = Join-Path $DevHomePath "OPEN REPOSCAN PRO DEV.cmd"
$DesktopShortcutPath = Join-Path $DesktopPath "RepoScan Pro Dev.lnk"
$RepoLauncherPath = Join-Path $RepoRoot "Open RepoScan Pro Dev.cmd"
$WorkspacePath = Join-Path $RepoRoot "RepoScan Pro.code-workspace"

if (-not (Test-Path $RepoLauncherPath)) {
    throw "Missing repo launcher: $RepoLauncherPath"
}

if (-not (Test-Path $WorkspacePath)) {
    throw "Missing VS Code workspace file: $WorkspacePath"
}

New-Item -ItemType Directory -Force -Path $DevHomePath | Out-Null

$startHere = @"
REPOSCAN PRO DEV HOME

This is the current project launcher for RepoScan Pro.

Double-click:
OPEN REPOSCAN PRO DEV.cmd

Repo root:
$RepoRoot

VS Code workspace:
$WorkspacePath

GitHub repo:
https://github.com/MarkW1919/reposcan-pro

This launcher uses the repo-owned workspace and launcher files so the setup stays aligned with the Git repo.
"@
[System.IO.File]::WriteAllText($StartHerePath, $startHere)

$desktopCmd = @"
@echo off
call "$RepoLauncherPath"
"@
[System.IO.File]::WriteAllText($DesktopCmdPath, $desktopCmd)

$wsh = New-Object -ComObject WScript.Shell
$shortcut = $wsh.CreateShortcut($DesktopShortcutPath)
$shortcut.TargetPath = $DesktopCmdPath
$shortcut.WorkingDirectory = $RepoRoot
$shortcut.Description = "Open RepoScan Pro in VS Code"
$shortcut.Save()

Write-Host "Created desktop launcher assets:"
Write-Host " - $DevHomePath"
Write-Host " - $DesktopShortcutPath"

