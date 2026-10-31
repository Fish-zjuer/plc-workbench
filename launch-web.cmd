@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -B -m plc_agent web --port 18765 --open-browser %*
) else (
  python -B -m plc_agent web --port 18765 --open-browser %*
)
if errorlevel 1 pause
