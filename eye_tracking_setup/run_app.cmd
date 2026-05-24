@echo off
setlocal
cd /d "%~dp0.."
set "ROOT=%CD%"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
"%ROOT%\.venv\Scripts\python.exe" -m ui.app %*
exit /b %ERRORLEVEL%
