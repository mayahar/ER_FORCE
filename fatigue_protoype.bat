@echo off
REM Launch the PySide6 app from virtual environment

cd /d "%~dp0"

if not exist "venv" (
    echo Virtual environment not found. Creating one...
    python -m venv venv
)

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Install requirements if needed
pip install -r requirements.txt

REM Set PYTHONPATH to include local TobiiPro_SDK
set PYTHONPATH=%CD%\TobiiPro_SDK;%PYTHONPATH%

REM Run the app
python -m ui.app

pause
