@echo off
setlocal ENABLEDELAYEDEXPANSION
REM ===== MAYDAY portable build.bat =====
REM Works from any folder. No hardcoded paths.

set "MAYDAY_ROOT=%~dp0"
set "MAYDAY_ROOT=%MAYDAY_ROOT:~0,-1%"
cd /d "%MAYDAY_ROOT%"

echo [MAYDAY] Root: %MAYDAY_ROOT%

if not exist "%MAYDAY_ROOT%\bootstrap\gui.py" (
    echo SKIPPED_MISSING_SOURCE
)

REM --- 1. Locate system Python for local .venv bootstrap ---
set "SYSTEM_PY="
where py >nul 2>&1
if not errorlevel 1 (
    for /f "delims=" %%I in ('py -3.10 -c "import sys; print(sys.executable)" 2^>nul') do set "SYSTEM_PY=%%I"
    if not defined SYSTEM_PY (
        for /f "delims=" %%I in ('py -3 -c "import sys; print(sys.executable)" 2^>nul') do set "SYSTEM_PY=%%I"
    )
)

if not defined SYSTEM_PY (
    where python >nul 2>&1
    if not errorlevel 1 set "SYSTEM_PY=python"
)

if not defined SYSTEM_PY (
    echo [ERROR] No usable system Python found.
    echo         Install Python 3.10+ and retry.
    exit /b 1
)

echo [MAYDAY] Using system Python: %SYSTEM_PY%

if not exist "%MAYDAY_ROOT%\runtime\python\python.exe" (
    echo [MAYDAY] Embedded runtime missing - continuing with system Python bootstrap.
)

REM --- 2. Verify / create local .venv ---
set "VENV_DIR=%MAYDAY_ROOT%\.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
if not exist "%VENV_PY%" (
    echo [MAYDAY] .venv missing - creating...
    "%SYSTEM_PY%" -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo [ERROR] Failed to create .venv with system Python.
        exit /b 1
    )
)

if not exist "%VENV_PY%" (
    echo [ERROR] .venv creation did not produce %VENV_PY%.
    exit /b 1
)

REM --- 3. Verify / install requirements ---
"%VENV_PY%" "%MAYDAY_ROOT%\scripts\bootstrap_check.py" --check-deps
if errorlevel 1 (
    echo [MAYDAY] Dependencies missing - installing...
    "%VENV_PY%" -m pip install --upgrade pip
    if errorlevel 1 exit /b 1
    "%VENV_PY%" -m pip install --upgrade setuptools wheel
    if errorlevel 1 exit /b 1
    "%VENV_PY%" -m pip install llama-cpp-python==0.2.76 --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
    if errorlevel 1 (
        echo [MAYDAY] Prebuilt llama-cpp-python wheel unavailable; attempting standard install...
        "%VENV_PY%" -m pip install llama-cpp-python==0.2.76
        if errorlevel 1 exit /b 1
    )
    "%VENV_PY%" -m pip install -r "%MAYDAY_ROOT%\requirements.txt"
    if errorlevel 1 exit /b 1
    "%VENV_PY%" -m playwright install chromium
    if errorlevel 1 exit /b 1
)

REM --- 4. Verify / download models ---
"%VENV_PY%" "%MAYDAY_ROOT%\scripts\bootstrap_check.py" --check-models
if errorlevel 1 (
    echo [MAYDAY] Models missing - downloading...
    "%VENV_PY%" "%MAYDAY_ROOT%\scripts\models_downloader.py"
    if errorlevel 1 (
        echo [ERROR] Model download failed.
        exit /b 1
    )
)

REM --- 5. Launch app ---
echo [MAYDAY] Launching app...
"%VENV_PY%" "%MAYDAY_ROOT%\main.py"
endlocal
