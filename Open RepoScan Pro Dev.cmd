@echo off
where code >nul 2>nul
if errorlevel 1 (
  echo VS Code command line launcher not found on PATH.
  echo Open this workspace file manually:
  echo C:\Users\mark\Documents\Playground\reposcan-pro\RepoScan Pro.code-workspace
  pause
  exit /b 1
)
code "C:\Users\mark\Documents\Playground\reposcan-pro\RepoScan Pro.code-workspace"

