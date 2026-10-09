@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title Video Creative Studio - RTX 3060 12GB Tests

set "PYTHON_CMD=python"
if defined VCS_PYTHON set "PYTHON_CMD=%VCS_PYTHON%"
set "MODE=%~1"
set "RUN_SUFFIX="
set "DRY_RUN_FLAG="
set "PAUSE_AT_END="
if "%~1"=="" set "PAUSE_AT_END=1"
if not defined MODE set "MODE=all"
if /I "%MODE%"=="dry-run" set "RUN_SUFFIX=_dryrun"
if /I "%MODE%"=="dry-run" set "DRY_RUN_FLAG=--dry-run"
if /I "%MODE%"=="shoulders" if /I "%~2"=="dry-run" set "RUN_SUFFIX=_dryrun"
if /I "%MODE%"=="shoulders" if /I "%~2"=="dry-run" set "DRY_RUN_FLAG=--dry-run"

echo ================================================================
echo RTX 3060 12GB - LivePortrait + MuseTalk config tests
echo Mode: %MODE%
echo Python: %PYTHON_CMD%
echo Logs and outputs: output\rtx3060\
echo ================================================================

set "SOURCE_IMAGE=assets\characters\nhanvatnam\asian_male_office_1080p.png"
if not exist "%SOURCE_IMAGE%" if exist "asian_male_office_1080p.png" set "SOURCE_IMAGE=asian_male_office_1080p.png"
echo Source image: %SOURCE_IMAGE%
if not exist "%SOURCE_IMAGE%" (
    echo ERROR: Khong tim thay anh nguon o ca hai vi tri:
    echo   assets\characters\nhanvatnam\asian_male_office_1080p.png
    echo   asian_male_office_1080p.png
    echo Hay ap dung output\rtx3060_pipeline_patch_v3.zip vao thu muc goc project.
    goto :failed
)

"%PYTHON_CMD%" --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Khong chay duoc Python. Hay cai dat Python vao PATH hoac dat VCS_PYTHON.
    goto :failed
)
where ffmpeg >nul 2>&1
if errorlevel 1 (
    echo ERROR: Khong tim thay ffmpeg trong PATH.
    goto :failed
)
where ffprobe >nul 2>&1
if errorlevel 1 (
    echo ERROR: Khong tim thay ffprobe trong PATH.
    goto :failed
)

for %%F in (
    "test_option_b_avatar.py"
    "runners\liveportrait_runner.py"
    "runners\lipsync_runner.py"
    "runners\apply_conversational_motion.py"
    "assets\driving_templates\reference_head_driving.mp4"
    "sample_script_1min.mp3"
) do (
    if not exist "%%~F" (
        echo ERROR: Thieu file can thiet: %%~F
        goto :failed
    )
)

if not exist "output\rtx3060" mkdir "output\rtx3060"

if /I "%MODE%"=="all" goto :run_all
if /I "%MODE%"=="dry-run" goto :run_all
if /I "%MODE%"=="A1" goto :run_a1
if /I "%MODE%"=="A2" goto :run_a2
if /I "%MODE%"=="A3" goto :run_a3
if /I "%MODE%"=="B" goto :run_b
if /I "%MODE%"=="B1" goto :run_b1
if /I "%MODE%"=="B2" goto :run_b2
if /I "%MODE%"=="shoulders" goto :run_shoulders
echo Usage: test_rtx3060.bat [all^|dry-run^|shoulders [dry-run]^|A1^|A2^|A3^|B^|B1^|B2]
goto :failed

:run_all
call :run_case A1 0.40 off
if errorlevel 1 goto :failed
call :run_case A2 0.55 off
if errorlevel 1 goto :failed
call :run_case A3 0.70 off
if errorlevel 1 goto :failed
call :run_case B 0.55 coupled
if errorlevel 1 goto :failed
goto :success

:run_a1
call :run_case A1 0.40 off
if errorlevel 1 goto :failed
goto :success

:run_a2
call :run_case A2 0.55 off
if errorlevel 1 goto :failed
goto :success

:run_a3
call :run_case A3 0.70 off
if errorlevel 1 goto :failed
goto :success

:run_b
call :run_case B 0.55 coupled
if errorlevel 1 goto :failed
goto :success

:run_b1
call :run_case B1 0.55 silhouette 4 0.65 0.18
if errorlevel 1 goto :failed
goto :success

:run_b2
call :run_case B2 0.55 silhouette 6 0.65 0.18
if errorlevel 1 goto :failed
goto :success

:run_shoulders
call :run_case B1 0.55 silhouette 4 0.65 0.18
if errorlevel 1 goto :failed
call :run_case B2 0.55 silhouette 6 0.65 0.18
if errorlevel 1 goto :failed
goto :success

:run_case
set "LOG_READY="
set "LOG_FILE="
set "CASE_NAME=%~1"
set "MULTIPLIER=%~2"
set "MOTION_MODE=%~3"
set "PIPELINE_MOTION_MODE=%MOTION_MODE%"
set "OUTPUT_FILE=output\rtx3060\%CASE_NAME%%RUN_SUFFIX%.mp4"
set "LOG_FILE=output\rtx3060\%CASE_NAME%%RUN_SUFFIX%.log"
set "MOTION_ARGS="
set "MOTION_SUMMARY=%MOTION_MODE%"
if /I "%MOTION_MODE%"=="coupled" (
    if not exist "assets\driving_templates\office_torso_motion_mask.png" (
        echo ERROR: Thieu mask cho cau hinh B: assets\driving_templates\office_torso_motion_mask.png
        exit /b 1
    )
    set "MOTION_ARGS=--body-mask assets\driving_templates\office_torso_motion_mask.png --face-roi 360 490 320 460 --max-displacement-px 2.5"
    set "MOTION_SUMMARY=coupled, interior, max 2.5px, strength 0.25, lag 0.14s"
)
if /I "%MOTION_MODE%"=="silhouette" (
    if not exist "assets\driving_templates\office_torso_silhouette_mask.png" (
        echo ERROR: Thieu silhouette mask cho %CASE_NAME%: assets\driving_templates\office_torso_silhouette_mask.png
        exit /b 1
    )
    set "PIPELINE_MOTION_MODE=coupled"
    set "MOTION_ARGS=--body-mask assets\driving_templates\office_torso_silhouette_mask.png --face-roi 360 490 320 460 --max-displacement-px %~4 --body-render-mode silhouette --coupling-strength %~5 --head-motion-lag-seconds %~6"
    set "MOTION_SUMMARY=coupled, silhouette, max %~4px, strength %~5, lag %~6s"
)

echo.
echo [%CASE_NAME%] multiplier=%MULTIPLIER%, motion=%MOTION_SUMMARY%, duration=12s
echo Log: %LOG_FILE%
set "LOG_READY=1"
"%PYTHON_CMD%" -u test_option_b_avatar.py --char office --source "%SOURCE_IMAGE%" --driving "assets\driving_templates\reference_head_driving.mp4" --audio "sample_script_1min.mp3" --duration 12 --output "%OUTPUT_FILE%" --fps 25 --source-max-dim 1280 --multiplier %MULTIPLIER% --driving-policy hold --motion-mode %PIPELINE_MOTION_MODE% --batch-size 2 --offset-ms 0 %MOTION_ARGS% %DRY_RUN_FLAG% > "%LOG_FILE%" 2>&1
set "RUN_RC=%ERRORLEVEL%"
type "%LOG_FILE%"
if not "%RUN_RC%"=="0" (
    echo [%CASE_NAME%] FAILED, exit code %RUN_RC%.
    exit /b 1
)
if not defined DRY_RUN_FLAG echo [%CASE_NAME%] OK: %OUTPUT_FILE%
exit /b 0

:success
echo.
if defined DRY_RUN_FLAG (
    echo Dry-run hoan tat. Xem cac file *_dryrun.log trong output\rtx3060\.
) else (
    echo Cac cau hinh da chay xong. Xem video va log trong output\rtx3060\.
)
set "FINAL_RC=0"
goto :finish

:failed
if defined LOG_READY goto :failed_after_start
echo.
if defined LOG_FILE goto :failed_preflight_with_case
echo Co loi truoc khi chay test; chua co log de xem.
goto :failed_exit

:failed_preflight_with_case
echo Loi preflight; chua tao log cho cau hinh: %LOG_FILE%
goto :failed_exit

:failed_after_start
if exist "%LOG_FILE%" goto :failed_with_log
echo.
echo Loi khi bat dau cau hinh nhung chua tao duoc log: %LOG_FILE%
goto :failed_exit

:failed_with_log
echo.
echo Co loi; xem log cua cau hinh vua chay: %LOG_FILE%

:failed_exit
set "FINAL_RC=1"
goto :finish

:finish
if defined PAUSE_AT_END pause
exit /b %FINAL_RC%
