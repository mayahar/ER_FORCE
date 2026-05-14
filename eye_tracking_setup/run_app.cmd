@echo off
setlocal
cd /d "%~dp0.."
set "ROOT=%CD%"
"%ROOT%\.venv-eye-tracking\Scripts\python.exe" -m streamlit run "%ROOT%\UI\streamlit_app.py" %*
exit /b %ERRORLEVEL%
