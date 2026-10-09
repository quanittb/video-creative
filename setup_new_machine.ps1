# Setup script for brand-new machine via PowerShell
$ErrorActionPreference = "Stop"

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "[SETUP] Video Creative Studio - Machine Bootstrap (PowerShell)" -ForegroundColor Cyan
Write-Host "Directory: $PSScriptRoot" -ForegroundColor Gray
Write-Host "======================================================================"

Set-Location $PSScriptRoot

# 1. Check Python
$pyOk = $false
try {
    $pyVer = & python -c "import sys; print(sys.version.split()[0])" 2>$null
    if ($LASTEXITCODE -eq 0 -and $pyVer) {
        Write-Host "[1/4] Found Python: $pyVer" -ForegroundColor Green
        $pyOk = $true
    }
} catch {
    $pyOk = $false
}

if (-not $pyOk) {
    Write-Host "[!] Python not installed or pointing to Microsoft Store shortcut." -ForegroundColor Yellow
    Write-Host "[!] Downloading official Python 3.10.11 installer (~27MB)..." -ForegroundColor Yellow
    $installerPath = "$env:TEMP\python_installer.exe"
    Invoke-WebRequest -Uri "https://www.python.org/ftp/python/3.10.11/python-3.10.11-amd64.exe" -OutFile $installerPath
    Write-Host "[!] Running Python installer with PATH enabled..." -ForegroundColor Yellow
    Start-Process -FilePath $installerPath -ArgumentList "/passive", "InstallAllUsers=1", "PrependPath=1", "Include_test=0" -Wait
    Remove-Item $installerPath -Force -ErrorAction SilentlyContinue
    Write-Host "[OK] Python 3.10 installed successfully!" -ForegroundColor Green
    Write-Host "Please close this PowerShell window and run setup again." -ForegroundColor Magenta
    Read-Host "Press Enter to exit"
    exit 0
}

# 2. Virtual environment
Write-Host "`n[2/4] Setting up Python virtual environment (venv)..." -ForegroundColor Cyan
if (-not (Test-Path "venv\Scripts\python.exe")) {
    python -m venv venv
    Write-Host "[OK] Virtual environment created." -ForegroundColor Green
} else {
    Write-Host "[OK] Virtual environment already exists." -ForegroundColor Green
}

# 3. Install PyTorch with CUDA 12.1
Write-Host "`n[3/4] Installing PyTorch CUDA 12.1 and dependencies..." -ForegroundColor Cyan
& "venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
Write-Host "Downloading PyTorch CUDA from pytorch.org..." -ForegroundColor Yellow
& "venv\Scripts\pip.exe" install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
Write-Host "Installing dependencies from requirements.txt..." -ForegroundColor Yellow
& "venv\Scripts\pip.exe" install -r requirements.txt

# 4. Check GPU
Write-Host "`n[4/4] Verifying GPU and CUDA support..." -ForegroundColor Cyan
& "venv\Scripts\python.exe" -c "import torch; print('  >>> CUDA Available:', torch.cuda.is_available()); print('  >>> Device Name:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'None')"

Write-Host "`n======================================================================" -ForegroundColor Green
Write-Host "[SUCCESS] Setup complete! You can now run quick_test.bat!" -ForegroundColor Green
Write-Host "======================================================================"
Read-Host "Press Enter to finish"
