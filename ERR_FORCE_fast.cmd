@echo off
REM Fast launcher: runs the venv interpreter directly (no PyInstaller unpack).

setlocal
cd /d "%~dp0"
set "ROOT=%CD%"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

if exist "%ROOT%\game\sivaks_logging_version\" (
  set "SIVAKS_FG_ROOT=%ROOT%\game\sivaks_logging_version"
)
set "ERR_FORCE_HOME=%ROOT%"
set "ER_FORCE_HOME=%ROOT%"
if exist "%ROOT%\TobiiPro_SDK\" (
  set "PYTHONPATH=%ROOT%\TobiiPro_SDK;%PYTHONPATH%"
)

set "PYW=%ROOT%\.venv-eye-tracking\Scripts\pythonw.exe"
set "PY=%ROOT%\.venv-eye-tracking\Scripts\python.exe"

if not exist "%PYW%" if not exist "%PY%" (
  if exist "%ROOT%\ERR_FORCE.exe" (
    start "" "%ROOT%\ERR_FORCE.exe"
    exit /b 0
  )
  if exist "%ROOT%\ER_FORCE.exe" (
    start "" "%ROOT%\ER_FORCE.exe"
    exit /b 0
  )
  powershell -NoProfile -Command "Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.MessageBox]::Show('Run eye_tracking_setup\setup_colleague.cmd first to set up the environment.','ERR Force - setup required','OK','Error') | Out-Null"
  exit /b 1
)

if exist "%PYW%" (
  start "" /D "%ROOT%" "%PYW%" -m ui.app %*
  exit /b 0
)

"%PY%" -m ui.app %*
exit /b %ERRORLEVEL%
