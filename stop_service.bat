@echo off
setlocal EnableExtensions

chcp 65001 >nul

set "PROJECT_DIR=%~dp0"
if "%PROJECT_DIR:~-1%"=="\" set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"
set "PID_FILE=%PROJECT_DIR%\.service.pid"
set "SERVICE_SCRIPT=%PROJECT_DIR%\service_runner.ps1"
set "SERVICE_PID="

if exist "%PID_FILE%" (
    set /p SERVICE_PID=<"%PID_FILE%"
)

if defined SERVICE_PID (
    powershell -NoProfile -Command "Stop-Process -Id %SERVICE_PID% -Force -ErrorAction SilentlyContinue" >nul 2>&1
    powershell -NoProfile -Command "Start-Sleep -Seconds 1" >nul 2>&1
)

powershell -NoProfile -Command ^
    "$servicePath = [System.IO.Path]::GetFullPath('%SERVICE_SCRIPT%');" ^
    "$targets = Get-CimInstance Win32_Process -Filter ""Name = 'powershell.exe' OR Name = 'pwsh.exe'"" | Where-Object { $_.CommandLine -and $_.CommandLine.Contains($servicePath) };" ^
    "foreach ($proc in $targets) { Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1

if exist "%PID_FILE%" del /f /q "%PID_FILE%" >nul 2>&1

echo Service stopped
exit /b 0

