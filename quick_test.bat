@echo off
cd /d "%~dp0"
title Video Creative Studio - Quick Test

echo ======================================================================
echo [TEST] Video Creative Studio - Quick Quality Benchmark
echo ======================================================================
echo.

set "PY_BIN=python"
if exist "venv\Scripts\python.exe" (
    venv\Scripts\python.exe -c "import sys" >nul 2>nul
    if not errorlevel 1 (
        set "PY_BIN=venv\Scripts\python.exe"
    )
) else if exist "D:\rustProject\prostudio-ai\musetalk-venv\Scripts\python.exe" (
    set "PY_BIN=D:\rustProject\prostudio-ai\musetalk-venv\Scripts\python.exe"
)

echo [1] Test Nam Doanh Nhan (Tieng Viet)
echo [2] Test Nu Chuyen Gia (Tieng Tay Ban Nha)
echo [3] Test Nu Hoat Hinh 3D Pixar (Tieng Anh)
echo [4] Tu dong test mac dinh
echo.
set /p opt="Chon so (1-4, Enter mac dinh la 1): "

if "%opt%"=="2" (
    "%PY_BIN%" quick_test.py --char female --lang es
) else if "%opt%"=="3" (
    "%PY_BIN%" quick_test.py --char pixar --lang en
) else (
    "%PY_BIN%" quick_test.py --char male --lang vi
)

echo.
echo Hoan tat! Bam phim bat ky de thoat...
pause > nul
