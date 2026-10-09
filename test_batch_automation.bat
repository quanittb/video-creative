@echo off
@chcp 65001 >nul
cd /d "%~dp0"
title Video Creative Studio - Test Batch Automation

echo ======================================================================
echo 🎬 VIDEO CREATIVE STUDIO - KIỂM TRA BATCH AUTOMATION & HÀNG ĐỢI TUẦN TỰ
echo ======================================================================
echo.

set PYTHON_CMD=python
if exist "C:\Program Files\Python310\python.exe" (
    set PYTHON_CMD="C:\Program Files\Python310\python.exe"
)

echo [1/3] Đang nạp danh sách công việc từ file manifest sample_batch_manifest.csv...
%PYTHON_CMD% core\job_manager.py import-csv sample_batch_manifest.csv
if errorlevel 1 (
    echo ❌ Lỗi khi import manifest!
    pause
    exit /b 1
)

echo.
echo [2/3] Danh sách các job hiện tại trong hàng đợi:
%PYTHON_CMD% core\job_manager.py list

echo.
echo ======================================================================
echo [3/3] Bạn có muốn chạy thử nghiệm Sequential Worker ngay bây giờ?
echo       (Nhấn phím bất kỳ để kích hoạt worker xử lý tuần tự 1 job)
echo ======================================================================
pause

%PYTHON_CMD% core\job_manager.py start-worker --once

echo.
echo Hoàn tất kiểm tra!
pause
