@echo off
cd /d "%~dp0"
title Video Creative Studio - Test Stage 1 LivePortrait 1080p
echo ======================================================================
echo [TEST] Kiem tra do net 1080p Stage 1 - LivePortrait Pasteback
echo ======================================================================
echo.
python test_liveportrait_stage1.py --char male
pause
