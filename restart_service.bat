@echo off
setlocal EnableExtensions

call "%~dp0stop_service.bat"
powershell -NoProfile -Command "Start-Sleep -Seconds 1" >nul 2>&1
call "%~dp0start_service.bat"
exit /b %errorlevel%

