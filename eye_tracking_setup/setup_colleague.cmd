@echo off
setlocal
cd /d "%~dp0.."
set "ROOT=%CD%"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

echo.
echo ========================================
echo  ER_FORCE - colleague setup (all-in-one)
echo ========================================
echo  Repo: %ROOT%
echo.
echo  First time on this PC?
echo    setup_colleague.cmd -FirstTime
echo.
echo  Already installed Tobii software?
echo    setup_colleague.cmd
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_colleague.ps1" %*
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" (
    echo SUCCESS. Start the fatigue app:
    echo   eye_tracking_setup\run_app.cmd
    echo.
    echo In-game: blue "eye recording active" after start.
    echo Raw gaze files: eye_tracking_analysis\recordings\
) else if "%RC%"=="2" (
    echo Software OK - connect/calibrate Tobii, then run setup_colleague.cmd again.
) else (
    echo Setup failed. Fix errors above and re-run.
    echo First time? Use: eye_tracking_setup\setup_colleague.cmd -FirstTime
)

exit /b %RC%
