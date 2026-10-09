@echo off
@chcp 65001 >nul
cd /d "%~dp0"
title Video Creative Studio - Trinh duyet Web

echo ======================================================================
echo 🎬 VIDEO CREATIVE STUDIO - GIAO DIỆN TRÌNH DUYỆT (CHROME / EDGE)
echo ======================================================================
echo.
echo 👉 Đang khởi động Vite Dev Server và tự động mở trình duyệt...
echo.

call pnpm.cmd run dev --open

pause
