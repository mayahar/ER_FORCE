@echo off
REM Launch the PySide6 app from the Python 3.10 virtual environment.

cd /d "%~dp0"

set "VENV=.venv"
set "PYTHON=%VENV%\Scripts\python.exe"

if not exist "%PYTHON%" (
    echo Python 3.10 virtual environment not found. Creating %VENV%...
    py -3.10 -m venv "%VENV%"
    if errorlevel 1 (
        echo Python 3.10 is required. Install it or run eye_tracking_setup\setup_colleague.cmd
        pause
        exit /b 1
    )
)

REM Install requirements if needed
"%PYTHON%" -m pip install -r requirements.txt
if errorlevel 1 (
    echo Failed to install requirements.
    pause
    exit /b 1
)

REM Run the app
"%PYTHON%" -m ui.app

pause
