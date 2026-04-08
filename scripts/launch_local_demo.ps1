$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$logsRoot = Join-Path $repoRoot "runtime/dev-ui"

New-Item -ItemType Directory -Force -Path $logsRoot | Out-Null

function Get-ListeningProcessId {
  param(
    [Parameter(Mandatory = $true)]
    [int] $Port
  )

  $connection = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($null -eq $connection) {
    return $null
  }

  return [int] $connection.OwningProcess
}

function Start-RepoScanProcess {
  param(
    [Parameter(Mandatory = $true)]
    [string] $Name,

    [Parameter(Mandatory = $true)]
    [int] $Port,

    [Parameter(Mandatory = $true)]
    [string] $Command,

    [Parameter(Mandatory = $true)]
    [string] $StdoutLog,

    [Parameter(Mandatory = $true)]
    [string] $StderrLog,

    [Parameter(Mandatory = $true)]
    [string] $PidFile
  )

  $existingPid = Get-ListeningProcessId -Port $Port
  if ($null -ne $existingPid) {
    Write-Host "$Name already running on port $Port (PID $existingPid)."
    Set-Content -Path $PidFile -Value $existingPid -Encoding ascii
    return
  }

  $process = Start-Process `
    -FilePath "$env:SystemRoot\System32\cmd.exe" `
    -ArgumentList "/c", $Command `
    -WorkingDirectory $repoRoot `
    -RedirectStandardOutput $StdoutLog `
    -RedirectStandardError $StderrLog `
    -WindowStyle Hidden `
    -PassThru

  Set-Content -Path $PidFile -Value $process.Id -Encoding ascii
  Write-Host "Started $Name on port $Port (PID $($process.Id))."
}

function Wait-ForPort {
  param(
    [Parameter(Mandatory = $true)]
    [int] $Port,

    [int] $TimeoutSeconds = 60
  )

  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  while ((Get-Date) -lt $deadline) {
    $listeningPid = Get-ListeningProcessId -Port $Port
    if ($null -ne $listeningPid) {
      return $true
    }
    Start-Sleep -Seconds 1
  }

  return $false
}

$uiStdout = Join-Path $logsRoot "ui.stdout.log"
$uiStderr = Join-Path $logsRoot "ui.stderr.log"
$uiPid = Join-Path $logsRoot "ui.pid"
$apiStdout = Join-Path $logsRoot "api.stdout.log"
$apiStderr = Join-Path $logsRoot "api.stderr.log"
$apiPid = Join-Path $logsRoot "api.pid"

Start-RepoScanProcess `
  -Name "RepoScan API" `
  -Port 8000 `
  -Command "npm run api:dev" `
  -StdoutLog $apiStdout `
  -StderrLog $apiStderr `
  -PidFile $apiPid

Start-RepoScanProcess `
  -Name "RepoScan UI" `
  -Port 4173 `
  -Command "npm run ui:dev" `
  -StdoutLog $uiStdout `
  -StderrLog $uiStderr `
  -PidFile $uiPid

if (-not (Wait-ForPort -Port 4173 -TimeoutSeconds 90)) {
  throw "The UI did not start listening on port 4173 within 90 seconds. Check runtime/dev-ui/ui.stderr.log."
}

Start-Process "http://localhost:4173/"
Write-Host "RepoScan Pro local demo opened at http://localhost:4173/."
