@echo off
setlocal
cd /d "%~dp0.."
echo.
echo Creating ERR Force Desktop shortcut...
echo App folder: %CD%
echo.

set "PY="
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY if exist ".venv-eye-tracking\Scripts\python.exe" set "PY=.venv-eye-tracking\Scripts\python.exe"
if not defined PY if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"
if not defined PY (
    where python >nul 2>&1
    if errorlevel 1 (
        echo No Python found. Run eye_tracking_setup\setup_colleague.cmd first.
        echo.
        pause
        exit /b 1
    )
    set "PY=python"
)

"%PY%" install\create_desktop_shortcut.py
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" (
    echo Done.
) else (
    echo Shortcut creation failed with exit code %RC%.
)
echo.
pause
exit /b %RC%
