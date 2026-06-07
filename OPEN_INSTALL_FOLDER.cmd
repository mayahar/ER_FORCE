@echo off
setlocal
cd /d "%~dp0"
start "" explorer "%CD%"
exit /b 0
