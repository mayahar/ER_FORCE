@echo off
setlocal
cd /d "%~dp0"
if not exist "scores_reports" mkdir "scores_reports"
start "" explorer "%CD%\scores_reports"
exit /b 0
