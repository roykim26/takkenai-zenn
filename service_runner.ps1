$ErrorActionPreference = "Stop"

$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$logsDir = Join-Path $projectDir "logs"
$pidFile = Join-Path $projectDir ".service.pid"
$heartbeatFile = Join-Path $projectDir ".service.heartbeat"
$runScript = Join-Path $projectDir "run_publish.bat"
$serviceLog = Join-Path $logsDir "service.log"

if (-not (Test-Path $logsDir)) {
    New-Item -ItemType Directory -Path $logsDir | Out-Null
}

function Write-ServiceLog {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss zzz"
    Add-Content -Path $serviceLog -Value "$timestamp | $Message"
}

function Write-Heartbeat {
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss zzz"
    Set-Content -Path $heartbeatFile -Value $timestamp -Encoding ascii
}

function Remove-PidFileIfOwned {
    if (-not (Test-Path $pidFile)) {
        return
    }

    try {
        $currentPidText = [string]$PID
        $savedPidText = (Get-Content -Path $pidFile -ErrorAction Stop | Select-Object -First 1).Trim()
        if ($savedPidText -eq $currentPidText) {
            Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
        }
    } catch {
        Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
    }
}

if (-not (Test-Path $runScript)) {
    Write-ServiceLog "ERROR: run_publish.bat not found, service start aborted"
    throw "run_publish.bat not found: $runScript"
}

if (Test-Path $pidFile) {
    try {
        $existingPid = (Get-Content -Path $pidFile -ErrorAction Stop | Select-Object -First 1).Trim()
        if ($existingPid) {
            $existingProc = Get-Process -Id ([int]$existingPid) -ErrorAction SilentlyContinue
            if ($existingProc) {
                Write-ServiceLog "Service already running with pid=$existingPid, current start request ignored"
                exit 0
            }
        }
    } catch {
    }

    Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
}

Set-Content -Path $pidFile -Value ([string]$PID) -Encoding ascii
Write-Heartbeat
Write-ServiceLog "Service loop started pid=$PID"

$intervalSeconds = 600
if ($env:SERVICE_INTERVAL_SECONDS) {
    $parsedInterval = 0
    if ([int]::TryParse($env:SERVICE_INTERVAL_SECONDS, [ref]$parsedInterval) -and $parsedInterval -ge 60) {
        $intervalSeconds = $parsedInterval
    }
}

try {
    while ($true) {
        Write-Heartbeat
        Write-ServiceLog "Running publish cycle via run_publish.bat"
        $process = Start-Process -FilePath $runScript -WorkingDirectory $projectDir -PassThru -Wait -WindowStyle Hidden
        Write-ServiceLog "Publish cycle finished exit_code=$($process.ExitCode)"
        Write-Heartbeat
        Start-Sleep -Seconds $intervalSeconds
    }
} finally {
    Write-ServiceLog "Service loop stopped pid=$PID"
    Remove-PidFileIfOwned
}
