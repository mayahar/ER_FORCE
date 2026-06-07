@echo off
setlocal
cd /d "%~dp0\.."
echo.
echo ERR Force - Eye Tracker Check
echo.
call "eye_tracking_setup\verify_eye_tracking.cmd"
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" (
    echo Eye tracker is ready.
) else if "%RC%"=="2" (
    echo Software is installed, but no Tobii tracker was detected.
    echo Open Tobii Eye Tracker Manager, connect/calibrate the tracker, then try again.
) else (
    echo Eye tracker check failed.
)
echo.
pause
exit /b %RC%
