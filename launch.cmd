@echo off
where pwsh >nul 2>nul
if %errorlevel% equ 0 (
  pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\launch.ps1"
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\launch.ps1"
)
if errorlevel 1 pause
