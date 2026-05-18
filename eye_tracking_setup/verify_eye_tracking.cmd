@echo off
setlocal
cd /d "%~dp0.."
set "ROOT=%CD%"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

echo.
echo ER_FORCE - eye tracking verify (quick re-check)
echo For full colleague setup use: eye_tracking_setup\setup_colleague.cmd
echo Repo: %ROOT%
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0verify_eye_tracking.ps1" %*
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" (
    echo All checks passed. Run the app: eye_tracking_setup\run_app.cmd
) else if "%RC%"=="2" (
    echo Software is ready; connect/calibrate the Tobii and run this script again.
) else (
    echo Fix the errors above, then run this script again.
    echo First-time PC? Run: eye_tracking_setup\setup_colleague.cmd -FirstTime
)

exit /b %RC%
