@echo off
cd /d "%~dp0"
title Video Creative Studio - Setup

echo ======================================================================
echo [SETUP] Video Creative Studio - Machine Bootstrap
echo Current Directory: %cd%
echo ======================================================================
echo.

REM 1. Check Python
echo [1/4] Checking Python installation...
python -c "import sys; print('Python version:', sys.version.split()[0])" 2>nul
if %errorlevel% equ 0 goto PYTHON_OK

echo [!] Python is NOT installed or pointing to Microsoft Store shortcut.
echo [!] Downloading official Python 3.10.11 installer (approx 27MB)...
curl -L -o "%temp%\python_installer.exe" https://www.python.org/ftp/python/3.10.11/python-3.10.11-amd64.exe
if not exist "%temp%\python_installer.exe" goto DOWNLOAD_FAIL

echo [!] Installing Python 3.10 with PATH enabled...
"%temp%\python_installer.exe" /passive InstallAllUsers=1 PrependPath=1 Include_test=0
del "%temp%\python_installer.exe" 2>nul
echo.
echo ======================================================================
echo [OK] Python 3.10 installation finished!
echo Please CLOSE this window and RUN setup_new_machine.bat again!
echo ======================================================================
pause
exit /b 0

:DOWNLOAD_FAIL
echo [ERROR] Could not download Python automatically.
echo Please download and install Python manually from:
echo https://www.python.org/ftp/python/3.10.11/python-3.10.11-amd64.exe
echo Make sure to check the box: Add Python 3.10 to PATH
pause
exit /b 1

:PYTHON_OK
echo [OK] Python is ready.
echo.

REM 2. Create virtual environment
echo [2/4] Setting up Python virtual environment (venv)...
if exist "venv\Scripts\python.exe" goto VENV_OK
echo Creating venv...
python -m venv venv
if exist "venv\Scripts\python.exe" goto VENV_OK
echo [ERROR] Failed to create venv.
pause
exit /b 1

:VENV_OK
echo [OK] Virtual environment ready.
echo.

REM 3. Install PyTorch CUDA 12.1 and dependencies
echo [3/4] Installing PyTorch CUDA 12.1 for RTX 3060 12GB...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip --quiet
echo Downloading and installing PyTorch with CUDA...
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
echo Installing project dependencies...
pip install -r requirements.txt
echo [OK] Dependencies installed.
echo.

REM 4. Check GPU
echo [4/4] Verifying NVIDIA GPU...
python -c "import torch; print('CUDA Available:', torch.cuda.is_available()); print('Device Name:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'None')"
echo.

echo ======================================================================
echo [SUCCESS] Setup complete! You are ready to run quick_test.bat!
echo ======================================================================
echo.
pause
