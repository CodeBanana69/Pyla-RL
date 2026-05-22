@echo off
setlocal EnableExtensions

cd /d "%~dp0"

set "OMP_NUM_THREADS=2"
set "OPENBLAS_NUM_THREADS=2"
set "MKL_NUM_THREADS=2"
set "NUMEXPR_NUM_THREADS=2"

title Pyla-RL

echo.
echo Pyla-RL launcher
echo Official free download: https://github.com/CodeBanana69/Pyla-RL
echo.

if exist ".venv\Scripts\python.exe" (
    set "PY=.venv\Scripts\python.exe"
    goto :run
)

where py >nul 2>&1
if not errorlevel 1 (
    py -3.11-64 -c "import sys" >nul 2>&1
    if not errorlevel 1 (
        set "PY=py -3.11-64"
        goto :run
    )
    py -3.11 -c "import sys" >nul 2>&1
    if not errorlevel 1 (
        set "PY=py -3.11"
        goto :run
    )
)

where python >nul 2>&1
if not errorlevel 1 (
    python -c "import sys; raise SystemExit(0 if sys.maxsize > 2**32 else 1)" >nul 2>&1
    if not errorlevel 1 (
        set "PY=python"
        goto :run
    )
)

echo Could not find a 64-bit Python 3.11 install.
echo Run setup.exe in this folder first, then try again.
echo.
pause
exit /b 1

:run
echo Using: %PY%
echo.
echo Make sure your emulator is running and Brawl Stars is open.
echo.

%PY% main.py
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo Pyla-RL exited with code %EXIT_CODE%.
    echo.
    pause
)

exit /b %EXIT_CODE%
