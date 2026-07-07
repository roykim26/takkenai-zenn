@echo off
setlocal EnableExtensions

chcp 65001 >nul

set "PROJECT_DIR=%~dp0"
if "%PROJECT_DIR:~-1%"=="\" set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"
set "LOG_DIR=%PROJECT_DIR%\logs"
set "PID_FILE=%PROJECT_DIR%\.service.pid"
set "HEARTBEAT_FILE=%PROJECT_DIR%\.service.heartbeat"
set "SERVICE_SCRIPT=%PROJECT_DIR%\service_runner.ps1"
set "POWERSHELL_EXE=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
set "SERVICE_PID="

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%" >nul 2>&1

if not exist "%SERVICE_SCRIPT%" (
    echo [ERROR] service_runner.ps1 not found
    exit /b 1
)

if exist "%PID_FILE%" (
    for /f "usebackq delims=" %%P in ("%PID_FILE%") do set "SERVICE_PID=%%P"
    if defined SERVICE_PID (
        powershell -NoProfile -Command "$pidValue = %SERVICE_PID%; $heartbeat = '%HEARTBEAT_FILE%'; $proc = Get-Process -Id $pidValue -ErrorAction SilentlyContinue; if (-not $proc) { exit 1 }; if (-not (Test-Path $heartbeat)) { exit 1 }; $age = (New-TimeSpan -Start (Get-Item $heartbeat).LastWriteTime -End (Get-Date)).TotalMinutes; if ($age -le 30) { exit 0 } else { exit 1 }" >nul 2>&1
        if not errorlevel 1 (
            echo Service is already running, PID=%SERVICE_PID%
            exit /b 0
        )
        del /f /q "%PID_FILE%" >nul 2>&1
    )
)

start "" /min "%POWERSHELL_EXE%" -NoProfile -ExecutionPolicy Bypass -File "%SERVICE_SCRIPT%"

powershell -NoProfile -Command "Start-Sleep -Seconds 2" >nul 2>&1

if exist "%PID_FILE%" (
    set /p SERVICE_PID=<"%PID_FILE%"
    echo Service started, PID=%SERVICE_PID%
    echo Log file: %LOG_DIR%\service.log
    exit /b 0
)

echo [WARN] Start command sent, but PID file was not detected yet
echo Check log: %LOG_DIR%\service.log
exit /b 1

