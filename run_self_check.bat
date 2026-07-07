@echo off
setlocal EnableExtensions

chcp 65001 >nul

set "PROJECT_DIR=%~dp0"
if "%PROJECT_DIR:~-1%"=="\" set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"
set "LOG_DIR=%PROJECT_DIR%\logs"
set "LOG_FILE=%LOG_DIR%\self_check.log"
set "LOCK_FILE=%PROJECT_DIR%\.publish.lock"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%" >nul 2>&1

for /f "usebackq delims=" %%T in (`powershell -NoProfile -Command "Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz'"`) do set "RUN_START=%%T"

>> "%LOG_FILE%" echo.
>> "%LOG_FILE%" echo ===== self-check run start %RUN_START% =====
>> "%LOG_FILE%" echo project_dir=%PROJECT_DIR%

cd /d "%PROJECT_DIR%"
if errorlevel 1 (
    >> "%LOG_FILE%" echo ERROR: failed to cd into project_dir
    goto :fail
)

if not exist "main.py" (
    >> "%LOG_FILE%" echo ERROR: main.py not found in project_dir
    goto :fail
)

if exist "venv\Scripts\python.exe" (
    set "PYTHON_EXE=%PROJECT_DIR%\venv\Scripts\python.exe"
) else if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=%PROJECT_DIR%\.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

>> "%LOG_FILE%" echo python_exe=%PYTHON_EXE%
>> "%LOG_FILE%" echo python_version:
"%PYTHON_EXE%" --version >> "%LOG_FILE%" 2>&1

>> "%LOG_FILE%" echo lock_state_before:
if exist "%LOCK_FILE%" (
    for %%F in ("%LOCK_FILE%") do >> "%LOG_FILE%" echo exists=yes size=%%~zF modified=%%~tF
    >> "%LOG_FILE%" echo lock_content:
    type "%LOCK_FILE%" >> "%LOG_FILE%" 2>&1
    >> "%LOG_FILE%" echo.
) else (
    >> "%LOG_FILE%" echo exists=no
)

>> "%LOG_FILE%" echo visible_python_processes_before:
powershell -NoProfile -Command "Get-Process python,python3,py -ErrorAction SilentlyContinue | Select-Object Id,ProcessName,Path,StartTime | Format-Table -AutoSize" >> "%LOG_FILE%" 2>&1

>> "%LOG_FILE%" echo main.py --self-check output:
"%PYTHON_EXE%" main.py --self-check >> "%LOG_FILE%" 2>&1
set "EXIT_CODE=%errorlevel%"

>> "%LOG_FILE%" echo main.py --self-check exit code=%EXIT_CODE%
>> "%LOG_FILE%" echo lock_state_after:
if exist "%LOCK_FILE%" (
    for %%F in ("%LOCK_FILE%") do >> "%LOG_FILE%" echo exists=yes size=%%~zF modified=%%~tF
    >> "%LOG_FILE%" echo lock_content:
    type "%LOCK_FILE%" >> "%LOG_FILE%" 2>&1
    >> "%LOG_FILE%" echo.
) else (
    >> "%LOG_FILE%" echo exists=no
)

>> "%LOG_FILE%" echo visible_python_processes_after:
powershell -NoProfile -Command "Get-Process python,python3,py -ErrorAction SilentlyContinue | Select-Object Id,ProcessName,Path,StartTime | Format-Table -AutoSize" >> "%LOG_FILE%" 2>&1

for /f "usebackq delims=" %%T in (`powershell -NoProfile -Command "Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz'"`) do set "RUN_END=%%T"
>> "%LOG_FILE%" echo ===== self-check run end %RUN_END% exit=%EXIT_CODE% =====

exit /b %EXIT_CODE%

:fail
set "EXIT_CODE=1"
for /f "usebackq delims=" %%T in (`powershell -NoProfile -Command "Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz'"`) do set "RUN_END=%%T"
>> "%LOG_FILE%" echo ===== self-check run end %RUN_END% exit=%EXIT_CODE% =====
exit /b %EXIT_CODE%
