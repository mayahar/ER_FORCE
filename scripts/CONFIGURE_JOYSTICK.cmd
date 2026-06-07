@echo off
setlocal
cd /d "%~dp0\.."
echo.
echo ERR Force - Joystick Configuration
echo.
echo FlightGear will open with the menu visible.
echo Use File -^> Joystick Configuration.
echo If the menu is hidden, press F10.
echo.
pause
call "game\sivaks_logging_version\configure_joystick.cmd"
set "RC=%ERRORLEVEL%"
echo.
echo Joystick configuration session ended.
echo.
pause
exit /b %RC%
