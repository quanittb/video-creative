@echo off
@chcp 65001 >nul
cd /d "%~dp0"
title Đóng gói Video Creative Studio cho máy RTX 3060

echo ======================================================================
echo 📦 ĐÓNG GÓI VIDEO CREATIVE STUDIO ĐỂ CHUYỂN SANG MÁY RTX 3060
echo ======================================================================
echo.
echo Thư mục xuất: D:\video-creative-studio-rtx3060-package
echo (Tự động loại trừ node_modules và target để dung lượng siêu gọn nhẹ)
echo.

set TARGET_DIR=D:\video-creative-studio-rtx3060-package

if not exist "%TARGET_DIR%" mkdir "%TARGET_DIR%"

echo 👉 Đang sao chép các thành phần thực thi và pipeline AI...
xcopy /E /I /Y "assets" "%TARGET_DIR%\assets"
xcopy /E /I /Y "config" "%TARGET_DIR%\config"
xcopy /E /I /Y "core" "%TARGET_DIR%\core"
xcopy /E /I /Y "runners" "%TARGET_DIR%\runners"
xcopy /E /I /Y "LivePortrait" "%TARGET_DIR%\LivePortrait"
xcopy /E /I /Y "musetalk" "%TARGET_DIR%\musetalk"

copy /Y "video-creative-studio.exe" "%TARGET_DIR%\"
copy /Y "start_studio.bat" "%TARGET_DIR%\"
copy /Y "test_option_b_avatar.py" "%TARGET_DIR%\"
copy /Y "requirements.txt" "%TARGET_DIR%\"
copy /Y "sample_10_styles_batch.csv" "%TARGET_DIR%\"
copy /Y "sample_batch_manifest.json" "%TARGET_DIR%\"
copy /Y "HUONG_DAN_CHUYEN_MAY_RTX3060.md" "%TARGET_DIR%\"

if not exist "%TARGET_DIR%\output" mkdir "%TARGET_DIR%\output"
if not exist "%TARGET_DIR%\temp" mkdir "%TARGET_DIR%\temp"

echo.
echo ======================================================================
echo ✅ ĐÃ ĐÓNG GÓI THÀNH CÔNG!
echo 👉 Vị trí: %TARGET_DIR%
echo 👉 Bạn chỉ cần nén thư mục này hoặc copy qua máy RTX 3060 để sử dụng!
echo ======================================================================
pause
