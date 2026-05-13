@echo off
setlocal
set "ROOT=%~dp0.."
set "ROOT=%ROOT:~0,-1%"
"%ROOT%\.venv-eye-tracking\Scripts\python.exe" -m streamlit run "%ROOT%\UI\streamlit_app.py" %*
exit /b %ERRORLEVEL%
