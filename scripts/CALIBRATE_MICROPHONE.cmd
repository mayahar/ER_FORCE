@echo off
setlocal
cd /d "%~dp0\.."
call CALIBRATE_MICROPHONE.cmd
exit /b %ERRORLEVEL%
