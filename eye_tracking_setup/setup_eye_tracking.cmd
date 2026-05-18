@echo off
REM Alias for first-time colleague setup (opens Tobii download pages + full verify)
setlocal
call "%~dp0setup_colleague.cmd" -FirstTime %*
exit /b %ERRORLEVEL%
