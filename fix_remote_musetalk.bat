@echo off
cd /d "%~dp0"
title Fix MuseTalk Final Dependencies (RTX 3060)
echo ======================================================================
echo [FIX] Cap nhat ma nguon va thu vien MuseTalk cho RTX 3060
echo ======================================================================
echo.

set PYTHON_CMD=python
if exist "C:\Program Files\Python310\python.exe" (
    set PYTHON_CMD="C:\Program Files\Python310\python.exe"
)

echo [1/3] Giai nen ma nguon MuseTalk da duoc sua loi tu musetalk_src.zip...
%PYTHON_CMD% -c "import zipfile; from pathlib import Path; z = Path('assets/musetalk_src.zip') if Path('assets/musetalk_src.zip').is_file() else Path('musetalk_src.zip'); (zipfile.ZipFile(z).extractall('musetalk'), print('  ✅ Da giai nen ma nguon patch thanh cong!')) if z.is_file() else print('  [!] Khong tim thay musetalk_src.zip')"

echo.
echo [2/3] Cai dat numpy 1.26.4, librosa, soundfile, einops, omegaconf, mmdet va transformers...
%PYTHON_CMD% -m pip install "numpy==1.26.4" librosa soundfile einops omegaconf ffmpeg-python accelerate "mmdet>=3.1.0" "transformers==4.44.2" "opencv-python==4.9.0.80" --user

echo.
echo [3/3] Kiem tra toan dien tat ca thanh phan MuseTalk tren GPU RTX 3060:
%PYTHON_CMD% -c "import torch; print('  PyTorch:', torch.__version__, '| CUDA:', torch.cuda.is_available(), '| GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'None')"
%PYTHON_CMD% -c "import transformers, diffusers; print('  Transformers:', transformers.__version__, '| Diffusers:', diffusers.__version__)"
%PYTHON_CMD% -c "import librosa, soundfile, einops, omegaconf; print('  Audio Processor Libs (librosa, soundfile, einops, omegaconf): OK!')"
%PYTHON_CMD% -c "import sys; from pathlib import Path; p = Path('musetalk'); [sys.path.insert(0, str(x)) for x in [p, p / 'musetalk' / 'utils', p / 'musetalk' / 'utils' / 'face_detection'] if str(x) not in sys.path]; import musetalk.utils.preprocessing as prep; print('  DWPose & Preprocessing Module: OK!')"
%PYTHON_CMD% -c "import sys; from pathlib import Path; p = Path('musetalk'); [sys.path.insert(0, str(x)) for x in [p, p / 'musetalk' / 'utils', p / 'musetalk' / 'utils' / 'face_detection'] if str(x) not in sys.path]; from musetalk.utils.audio_processor import AudioProcessor; from musetalk.utils.face_parsing import FaceParsing; from musetalk.utils.blending import get_image; from musetalk.utils.utils import get_file_type, datagen, load_all_model; print('  >>> CHUC MUNG! Tat ca module va thu vien MuseTalk da san sang 100% tren RTX 3060!')"

echo.
echo ======================================================================
echo Hoan tat! Bay gio ban co the chay ngay test_option_b.bat!
echo ======================================================================
pause
