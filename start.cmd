@echo off
REM Start the web workbench; prepare the local Python environment if needed.
cd /d "%~dp0"
REM Loopback relay requests must stay local; preserve external proxy rules.
if defined NO_PROXY (
  set "NO_PROXY=127.0.0.1,localhost,::1,%NO_PROXY%"
) else (
  set "NO_PROXY=127.0.0.1,localhost,::1"
)
if not exist ".venv\Scripts\python.exe" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup.ps1" -ProjectLocal
  if errorlevel 1 (
    pause
    exit /b 1
  )
)
".venv\Scripts\python.exe" -B -m plc_agent web --port 18765 --open-browser %*
if errorlevel 1 pause
