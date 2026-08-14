@echo off
setlocal

fltmc >nul 2>&1
if errorlevel 1 (
  powershell.exe -NoProfile -WindowStyle Hidden -Command "Start-Process -FilePath '%~f0' -Verb RunAs -WindowStyle Hidden"
  exit /b 0
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0start-monitor-admin.ps1"
exit /b %errorlevel%
