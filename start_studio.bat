@echo off
@chcp 65001 >nul
cd /d "%~dp0"
title Video Creative Studio - Desktop Suite

echo ======================================================================
echo 🎬 VIDEO CREATIVE STUDIO - LOCAL AI PRODUCTION SUITE
echo ======================================================================
echo.
echo 👉 Đang khởi chạy ứng dụng Desktop (Release Native Engine)...
echo.

if exist "video-creative-studio.exe" (
    start "" "video-creative-studio.exe"
) else (
    start "" "src-tauri\target\release\video-creative-studio.exe"
)

exit /b 0
