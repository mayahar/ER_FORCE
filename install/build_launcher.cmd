@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_launcher.ps1" -RepoRoot "%~dp0.."
exit /b %ERRORLEVEL%
