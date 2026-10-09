@echo off
cd /d "%~dp0"
title Test Truc Tiep MuseTalk FP16
echo ======================================================================
echo [TEST] Kiem tra moi truong MuseTalk va GPU tren may Remote
echo ======================================================================
echo.

set PYTHON_CMD=python
if exist "C:\Program Files\Python310\python.exe" (
    set PYTHON_CMD="C:\Program Files\Python310\python.exe"
)

echo [1/3] Kiem tra GPU va CUDA...
%PYTHON_CMD% -c "import sys, torch; print('  Python:', sys.executable); print('  CUDA available:', torch.cuda.is_available()); print('  GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'No GPU')"
echo.

echo [2/3] Kiem tra thu vien AI (Diffusers, Transformers, MMPose, DWPose)...
%PYTHON_CMD% -c "import diffusers, transformers, accelerate, mmpose, mmengine; print('  Thư viện AI cơ bản: OK!')"
echo.

echo [3/3] Kiem tra nap mo hinh MuseTalk...
%PYTHON_CMD% -c "import sys; from pathlib import Path; p = Path('musetalk'); sys.path.insert(0, str(p)); sys.path.insert(0, str(p / 'musetalk' / 'utils')); sys.path.insert(0, str(p / 'musetalk' / 'utils' / 'face_detection')); import musetalk.utils.preprocessing as prep; print('  MuseTalk Preprocessing Module: OK!')"
echo.

echo ======================================================================
echo Hoan tat kiem tra!
echo ======================================================================
pause
