@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

"%PYTHON_EXE%" -m voice.microphone_calibration_gui
if errorlevel 1 (
    echo.
    echo Microphone calibration could not start.
    echo Make sure ERR Force was installed successfully and Python packages are available.
    echo.
    pause
)
