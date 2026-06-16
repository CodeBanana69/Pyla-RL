@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PYTHONPATH=%~dp0app"
if exist "%~dp0app\.venv\Scripts\python.exe" (
    "%~dp0app\.venv\Scripts\python.exe" "%~dp0app\tools\updater.py" %*
    exit /b %ERRORLEVEL%
)
py -3.11-64 "%~dp0app\tools\updater.py" %*
exit /b %ERRORLEVEL%
