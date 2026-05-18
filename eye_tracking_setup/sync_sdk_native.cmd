@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0sync_sdk_native.ps1" %*
exit /b %ERRORLEVEL%
