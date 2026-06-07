@echo off
setlocal
cd /d "%~dp0\.."
start "" explorer "%CD%\install"
exit /b 0
