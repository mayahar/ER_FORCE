@echo off
setlocal
cd /d "%~dp0.."
set "ROOT=%CD%"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
"%ROOT%\.venv-eye-tracking\Scripts\python.exe" -m streamlit run "%ROOT%\UI\streamlit_app.py" %*
exit /b %ERRORLEVEL%
