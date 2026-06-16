@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PYTHONPATH=%~dp0app"
py -3.11-64 "%~dp0app\tools\setup_bootstrap.py" %*
exit /b %ERRORLEVEL%
