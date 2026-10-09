@echo off
cd /d "%~dp0"
title Video Creative Studio - Setup MuseTalk FP16 (RTX 3060 12GB)
echo ======================================================================
echo [SETUP] Tu dong cai dat mo hinh MuseTalk FP16 cho RTX 3060 12GB
echo ======================================================================
echo.

set PYTHON_CMD=python
if exist "C:\Program Files\Python310\python.exe" (
    set PYTHON_CMD="C:\Program Files\Python310\python.exe"
)

%PYTHON_CMD% setup_musetalk.py
echo.
pause
