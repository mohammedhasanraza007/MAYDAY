@echo off
set "ROOT_DIR=%~dp0"
if "%ROOT_DIR:~-1%"=="\" set "ROOT_DIR=%ROOT_DIR:~0,-1%"
set "RUNTIME_PY=%ROOT_DIR%\runtime\python\python.exe"
if not exist "%RUNTIME_PY%" (
  echo [ERROR] Embedded runtime missing. Run build.bat from this folder.
  pause
  exit /b 1
)
echo [INFO] Verifying Model Backend...
"%RUNTIME_PY%" "%ROOT_DIR%\main.py" --verify
if %ERRORLEVEL% NEQ 0 (
  echo [ERROR] Model verification FAILED. Check logs/startup_trace.log.
  pause
  exit /b 1
)

echo [SUCCESS] Model Backend Verified. Launching UI...
start "" "%RUNTIME_PY%" "%ROOT_DIR%\main.py" %*
