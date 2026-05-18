@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_probe.ps1" %*
exit /b %ERRORLEVEL%
