@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch_local_demo.ps1"
if errorlevel 1 (
  echo RepoScan local demo launcher failed.
  echo Check runtime\dev-ui logs for details.
  pause
  exit /b 1
)
endlocal
