@echo off
setlocal
title ERR_FORCE Installer
echo.
echo ========================================
echo  ERR_FORCE - Windows one-click install
echo ========================================
echo.
echo This will install ERR_FORCE, Python 3.10, Python packages, game files,
echo and a Desktop shortcut with the ERR_FORCE icon.
echo.
call "%~dp0install_app.cmd" %*
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" (
    echo Done. You can start ERR_FORCE from the Desktop shortcut.
) else (
    echo Installation failed with exit code %RC%.
)
echo.
pause
exit /b %RC%
