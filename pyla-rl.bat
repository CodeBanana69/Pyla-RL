@echo off
setlocal EnableExtensions

cd /d "%~dp0"

set "BUNDLE=%~dp0app"
set "PYTHONPATH=%BUNDLE%"

set "OMP_NUM_THREADS=2"
set "OPENBLAS_NUM_THREADS=2"
set "MKL_NUM_THREADS=2"
set "NUMEXPR_NUM_THREADS=2"

title Pyla-RL

echo.
echo Pyla-RL launcher
echo Official free download: https://github.com/CodeBanana69/Pyla-RL
echo.

if exist "app\cfg\pyla_python.txt" (
    set /p PYLA_PY=<app\cfg\pyla_python.txt
    "%PYLA_PY%" -c "import cv2, pandas" >nul 2>&1
    if not errorlevel 1 (
        set "PY=%PYLA_PY%"
        goto :run
    )
    echo Pinned Python from setup is missing required packages; trying other interpreters...
    echo.
)

if exist "app\.venv\Scripts\python.exe" (
    "app\.venv\Scripts\python.exe" -c "import cv2, pandas" >nul 2>&1
    if not errorlevel 1 (
        set "PY=app\.venv\Scripts\python.exe"
        goto :run
    )
    echo Found .venv but required packages are missing there; trying other interpreters...
    echo.
)

where py >nul 2>&1
if not errorlevel 1 (
    py -3.11-64 -c "import sys" >nul 2>&1
    if not errorlevel 1 (
        set "PY=py -3.11-64"
        goto :precheck
    )
    py -3.11 -c "import sys" >nul 2>&1
    if not errorlevel 1 (
        set "PY=py -3.11"
        goto :precheck
    )
)

where python >nul 2>&1
if not errorlevel 1 (
    python -c "import sys; raise SystemExit(0 if sys.maxsize > 2**32 else 1)" >nul 2>&1
    if not errorlevel 1 (
        set "PY=python"
        goto :precheck
    )
)

echo Could not find a 64-bit Python 3.11 install.
echo Run setup.exe in this folder first, then try again.
echo.
pause
exit /b 1

:precheck
%PY% -c "import cv2, pandas" >nul 2>&1
if not errorlevel 1 goto :run

:run
echo Using: %PY%
echo.

%PY% -c "import cv2, pandas" >nul 2>&1
if errorlevel 1 (
    echo Dependencies are not installed for this Python.
    echo.
    if exist "setup.exe" (
        echo Run setup.exe in this folder again, then launch pyla-rl.bat.
    ) else (
        echo Run: %PY% app\setup.py --pyla-install
    )
    echo.
    echo Diagnostic: %PY% app\tools\check_runtime.py
    echo.
    pause
    exit /b 1
)

echo Make sure your emulator is running and Brawl Stars is open.
echo.

%PY% "%BUNDLE%\main.py"
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo Pyla-RL exited with code %EXIT_CODE%.
    echo.
    pause
)

exit /b %EXIT_CODE%
