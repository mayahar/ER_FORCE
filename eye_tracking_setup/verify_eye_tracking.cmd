@echo off
setlocal
cd /d "%~dp0.."
set "ROOT=%CD%"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

echo.
echo ER_FORCE - one-shot eye tracking setup and verify
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
    echo First-time PC? Also run: eye_tracking_setup\install_prerequisites.cmd
    echo   then install Tobii Fusion + Eye Tracker Manager + Tobii Pro SDK from the browser.
)

exit /b %RC%
