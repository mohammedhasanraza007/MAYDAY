@echo off
setlocal
title M.A.Y.D.A.Y v4.5 DEBUG LAUNCHER

set "ROOT_DIR=%~dp0"
set "RUNTIME_PY=%ROOT_DIR%runtime\python\python.exe"
set "LOG_FILE=%ROOT_DIR%logs\runtime_crash.log"

echo ============================================================
echo  M.A.Y.D.A.Y v4.5 DEBUG LAUNCHER
echo ============================================================
echo [DEBUG] ROOT: %ROOT_DIR%
echo [DEBUG] EXEC: %RUNTIME_PY%
echo [DEBUG] CWD:  %CD%

if not exist "%RUNTIME_PY%" (
    echo [ERROR] Embedded runtime NOT FOUND at %RUNTIME_PY%
    echo Please run build.bat first.
    pause
    exit /b 1
)

echo [DEBUG] Launching with unbuffered output...
:: Force unbuffered output (-u) and verbose imports (-v if needed, but -u is better for logs)
"%RUNTIME_PY%" -u main.py 2> "%LOG_FILE%"

if %errorlevel% neq 0 (
    echo.
    echo ============================================================
    echo  CRITICAL FAILURE DETECTED (Exit Code: %errorlevel%)
    echo ============================================================
    echo Traceback might be in: %LOG_FILE%
    echo.
    echo Printing last 20 lines of crash log:
    if exist "%LOG_FILE%" (
        powershell -Command "Get-Content '%LOG_FILE%' -Tail 20"
    )
    echo ============================================================
    pause
)
