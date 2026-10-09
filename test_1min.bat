@echo off
@chcp 65001 >nul
cd /d "%~dp0"
title Video Creative Studio - Test Mau Video 1 Phut (LivePortrait + MuseTalk FP16)
echo ======================================================================
echo [TEST 1 MINUTE] PIPELINE CHAT LUONG CAO VOI KICH BAN 1 PHUT CHUAN
echo ======================================================================
echo.

set PYTHON_CMD=python
if exist "C:\Program Files\Python310\python.exe" (
    set PYTHON_CMD="C:\Program Files\Python310\python.exe"
)

REM Tu dong cap nhat file ma nguon va kich ban moi nhat tu Dropbox neu file da dong bo day du (>1KB)
for %%D in ("%USERPROFILE%\Dropbox\PC\Downloads" "C:\Users\Admin\Dropbox\PC\Downloads" "C:\Users\quant\Dropbox\PC\Downloads") do (
    if exist "%%~D\liveportrait_runner.py" (
        for %%F in ("%%~D\liveportrait_runner.py") do (
            if %%~zF gtr 5000 (
                if not exist "runners" mkdir "runners" 2>nul
                copy /Y "%%~F" "runners\liveportrait_runner.py" >nul
            )
        )
    )
    if exist "%%~D\apply_conversational_motion.py" (
        for %%F in ("%%~D\apply_conversational_motion.py") do (
            if %%~zF gtr 2000 (
                if not exist "runners" mkdir "runners" 2>nul
                copy /Y "%%~F" "runners\apply_conversational_motion.py" >nul
            )
        )
    )
    if exist "%%~D\conversational_kinematics.py" (
        for %%F in ("%%~D\conversational_kinematics.py") do (
            if %%~zF gtr 2000 (
                if not exist "runners" mkdir "runners" 2>nul
                copy /Y "%%~F" "runners\conversational_kinematics.py" >nul
            )
        )
    )
    if exist "%%~D\test_option_b_avatar.py" (
        for %%F in ("%%~D\test_option_b_avatar.py") do (
            if %%~zF gtr 5000 (
                copy /Y "%%~F" "test_option_b_avatar.py" >nul
            )
        )
    )
    if exist "%%~D\test_option_b_avatar.py.bak" (
        for %%F in ("%%~D\test_option_b_avatar.py.bak") do (
            if %%~zF gtr 5000 (
                copy /Y "%%~F" "test_option_b_avatar.py.bak" >nul
            )
        )
    )
    if exist "%%~D\live_portrait_pipeline.py" (
        for %%F in ("%%~D\live_portrait_pipeline.py") do (
            if %%~zF gtr 10000 (
                if exist "LivePortrait\src" copy /Y "%%~F" "LivePortrait\src\live_portrait_pipeline.py" >nul
            )
        )
    )
    if exist "%%~D\sample_script_1min.txt" (
        for %%F in ("%%~D\sample_script_1min.txt") do (
            if %%~zF gtr 50 (
                copy /Y "%%~F" "sample_script_1min.txt" >nul
            )
        )
    )
    if exist "%%~D\sample_script_1min.mp3" (
        for %%F in ("%%~D\sample_script_1min.mp3") do (
            if %%~zF gtr 10000 (
                copy /Y "%%~F" "sample_script_1min.mp3" >nul
            )
        )
    )
    if exist "%%~D\asian_male_office_1080p.png" (
        for %%F in ("%%~D\asian_male_office_1080p.png") do (
            if %%~zF gtr 10000 (
                if not exist "assets\characters\nhanvatnam" mkdir "assets\characters\nhanvatnam" 2>nul
                copy /Y "%%~F" "assets\characters\nhanvatnam\asian_male_office_1080p.png" >nul
            )
        )
    )
)

REM Kiem tra tinh toan ven file truoc khi chay
if not exist "test_option_b_avatar.py" (
    if exist "test_option_b_avatar.py.bak" copy /Y "test_option_b_avatar.py.bak" "test_option_b_avatar.py" >nul
)
for %%F in ("test_option_b_avatar.py") do (
    if %%~zF lss 2000 (
        if exist "test_option_b_avatar.py.bak" copy /Y "test_option_b_avatar.py.bak" "test_option_b_avatar.py" >nul
    )
)

%PYTHON_CMD% test_option_b_avatar.py --char office --script-file sample_script_1min.txt
echo.
pause
