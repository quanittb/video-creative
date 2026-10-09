@echo off
set "LAUNCH_DIR=%~dp0"
title Video Creative Studio - Setup LivePortrait (RTX 3060)

echo ======================================================================
echo [INSTALL] Tu dong cai dat mo hinh LivePortrait (RTX 3060 12GB)
echo ======================================================================
echo.

set PYTHON_CMD=python
if exist "C:\Program Files\Python310\python.exe" (
    set PYTHON_CMD="C:\Program Files\Python310\python.exe"
)

REM 1. Chuyen vao thu muc du an video-creative-studio
if exist "C:\Users\Admin\Downloads\video-creative-studio\video-creative-studio\test_option_b_avatar.py" (
    cd /d "C:\Users\Admin\Downloads\video-creative-studio\video-creative-studio"
) else if exist "%USERPROFILE%\Downloads\video-creative-studio\video-creative-studio\test_option_b_avatar.py" (
    cd /d "%USERPROFILE%\Downloads\video-creative-studio\video-creative-studio"
) else if exist "%USERPROFILE%\Downloads\video-creative-studio\test_option_b_avatar.py" (
    cd /d "%USERPROFILE%\Downloads\video-creative-studio"
) else (
    cd /d "%LAUNCH_DIR%"
)

echo Thu muc lam viec: %CD%
echo.

REM 2. Tu dong copy setup_liveportrait.py vao thu muc du an neu chua co
if not exist "setup_liveportrait.py" (
    if exist "%LAUNCH_DIR%setup_liveportrait.py" (
        copy /Y "%LAUNCH_DIR%setup_liveportrait.py" "setup_liveportrait.py" >nul
        echo Da tu dong copy setup_liveportrait.py tu %LAUNCH_DIR%
    ) else if exist "%USERPROFILE%\Dropbox\PC\Downloads\setup_liveportrait.py" (
        copy /Y "%USERPROFILE%\Dropbox\PC\Downloads\setup_liveportrait.py" "setup_liveportrait.py" >nul
        echo Da tu dong copy setup_liveportrait.py tu Dropbox
    ) else if exist "C:\Users\Admin\Dropbox\PC\Downloads\setup_liveportrait.py" (
        copy /Y "C:\Users\Admin\Dropbox\PC\Downloads\setup_liveportrait.py" "setup_liveportrait.py" >nul
        echo Da tu dong copy setup_liveportrait.py tu Dropbox Admin
    )
)

REM Tu dong cap nhat runners/liveportrait_runner.py neu co ban moi tu Dropbox
if not exist "runners" mkdir "runners" 2>nul
if exist "%LAUNCH_DIR%liveportrait_runner.py" (
    copy /Y "%LAUNCH_DIR%liveportrait_runner.py" "runners\liveportrait_runner.py" >nul
) else if exist "liveportrait_runner.py" (
    copy /Y "liveportrait_runner.py" "runners\liveportrait_runner.py" >nul
) else if exist "%USERPROFILE%\Dropbox\PC\Downloads\liveportrait_runner.py" (
    copy /Y "%USERPROFILE%\Dropbox\PC\Downloads\liveportrait_runner.py" "runners\liveportrait_runner.py" >nul
)

REM 3. Kiem tra va khoi chay setup
if exist "setup_liveportrait.py" (
    %PYTHON_CMD% setup_liveportrait.py
) else (
    echo [!] Khong tim thay setup_liveportrait.py, dang khoi chay trinh cai dat tich hop...
    %PYTHON_CMD% -c "import os, sys, shutil, subprocess, urllib.request, zipfile; from pathlib import Path; root = Path.cwd(); lp = root / 'LivePortrait'; weights = lp / 'pretrained_weights'; print('[1/4] Kiem tra ma nguon LivePortrait...'); (subprocess.run(['git', 'clone', '--depth', '1', 'https://github.com/KwaiVGI/LivePortrait.git', str(lp)], check=True) if shutil.which('git') else (urllib.request.urlretrieve('https://github.com/KwaiVGI/LivePortrait/archive/refs/heads/main.zip', 'lp.zip'), zipfile.ZipFile('lp.zip').extractall(root), (root / 'LivePortrait-main').rename(lp) if (root / 'LivePortrait-main').exists() else None, os.remove('lp.zip'))) if not (lp / 'inference.py').is_file() else print('  Ma nguon da co san!'); print('[2/4] Cai dat thu vien...'); subprocess.run([sys.executable, '-m', 'pip', 'install', 'pykalman', 'tyro', 'onnxruntime-gpu', 'insightface', 'pyyaml', 'scipy', 'imageio', 'imageio-ffmpeg', 'rich', 'pyyaml-include', 'huggingface_hub', 'dill', 'ffmpeg-python', 'scikit-image', '--user', '--quiet']); print('[3/4] Tai model weights...'); weights.mkdir(parents=True, exist_ok=True); from huggingface_hub import snapshot_download; snapshot_download('KlingTeam/LivePortrait', local_dir=str(weights), ignore_patterns=['*.md', '*.git*', 'docs/*']) if not (weights / 'base_models' / 'appearance_feature_extractor.pth').is_file() else print('  Weights da co san!'); print('[4/4] Kich hoat Pipeline 2 Chang...'); runner = root / 'test_option_b_avatar.py'; subprocess.run([sys.executable, str(runner), '--char', 'male']) if runner.is_file() else None"
)

if %errorlevel% neq 0 (
    echo.
    echo ======================================================================
    echo [!] Co loi trong qua trinh thuc thi. Vui long kiem tra log o tren.
    echo ======================================================================
)
echo.
pause
