@echo off
REM Alias: full first-time setup (opens Tobii download pages) + verify
setlocal
call "%~dp0verify_eye_tracking.cmd" -OpenDownloads %*
exit /b %ERRORLEVEL%
