@echo off
setlocal
cd /d "%~dp0"
if not exist "sessions" mkdir "sessions"
start "" explorer "%CD%\sessions"
exit /b 0
