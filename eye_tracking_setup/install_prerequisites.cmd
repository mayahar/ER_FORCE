@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_prerequisites.ps1" %*
exit /b %ERRORLEVEL%
