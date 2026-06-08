@echo off
setlocal
cd /d "%~dp0\.."

if exist "%CD%\hardware_config_editor.exe" (
  start "" "%CD%\hardware_config_editor.exe"
  exit /b 0
)

set "PYW=%CD%\.venv-eye-tracking\Scripts\pythonw.exe"
set "PY=%CD%\.venv-eye-tracking\Scripts\python.exe"
if not exist "%PYW%" if not exist "%PY%" (
  set "PYW=%CD%\.venv\Scripts\pythonw.exe"
  set "PY=%CD%\.venv\Scripts\python.exe"
)
if not exist "%PYW%" if not exist "%PY%" (
  set "PYW=%CD%\venv\Scripts\pythonw.exe"
  set "PY=%CD%\venv\Scripts\python.exe"
)

if exist "%PYW%" (
  start "" /D "%CD%" "%PYW%" "Editors\hardware_config_editor.py"
  exit /b 0
)

if exist "%PY%" (
  start "" /D "%CD%" "%PY%" "Editors\hardware_config_editor.py"
  exit /b 0
)

powershell -NoProfile -Command "Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.MessageBox]::Show('Python environment was not found. Run eye_tracking_setup\setup_colleague.cmd first.','ERR Force Tools','OK','Error') | Out-Null"
exit /b 1
