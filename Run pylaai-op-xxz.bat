@echo off
cd /d %~dp0
set OMP_NUM_THREADS=2
set OPENBLAS_NUM_THREADS=2
set MKL_NUM_THREADS=2
set NUMEXPR_NUM_THREADS=2
py -3.11-64 main.py
pause
