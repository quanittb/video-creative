"""Automated Setup for MuseTalk FP16 on Windows (RTX 3060 12GB).
Installs codebase, dependencies, and downloads official model weights.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
MUSE_DIR = ROOT_DIR / "musetalk"
MODELS_DIR = MUSE_DIR / "models"


def unpack_codebase():
    infer_py = MUSE_DIR / "scripts" / "inference.py"
    if infer_py.is_file():
        print("[1/3] ✅ Mã nguồn MuseTalk đã sẵn sàng.")
        return

    candidates = [
        ROOT_DIR / "assets" / "musetalk_src.zip",
        ROOT_DIR / "musetalk_src.zip",
        Path.home() / "Dropbox" / "PC" / "Downloads" / "assets" / "musetalk_src.zip",
        Path.home() / "Dropbox" / "PC" / "Downloads" / "musetalk_src.zip",
        Path("C:/Users/Admin/Dropbox/PC/Downloads/assets/musetalk_src.zip"),
        Path("C:/Users/Admin/Dropbox/PC/Downloads/musetalk_src.zip"),
    ]
    src_zip = next((c for c in candidates if c.is_file()), None)
    if src_zip:
        print(f"      👉 Đang giải nén mã nguồn từ {src_zip.name} ({src_zip})...")
        MUSE_DIR.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(src_zip, "r") as zf:
            zf.extractall(MUSE_DIR)
        print("      ✅ Đã giải nén mã nguồn MuseTalk thành công!")
    else:
        print("      👉 Đang tải mã nguồn từ GitHub (TMElyralab/MuseTalk)...")
        try:
            subprocess.run(["git", "clone", "https://github.com/TMElyralab/MuseTalk.git", str(MUSE_DIR)], check=True)
            print("      ✅ Đã tải mã nguồn thành công!")
        except Exception as e:
            print(f"      ❌ Không thể tải mã nguồn: {e}")


def install_deps():
    print("\n[2/3] 📦 Đang cài đặt thư viện cần thiết cho MuseTalk...")
    pkgs = [
        "numpy==1.26.4",
        "diffusers==0.30.2",
        "accelerate==0.28.0",
        "transformers==4.44.2",
        "opencv-python==4.9.0.80",
        "huggingface_hub",
        "edge-tts",
        "soundfile",
        "librosa",
        "einops",
        "ffmpeg-python",
        "scipy",
        "omegaconf",
        "face-alignment",
        "mmengine",
        "mmdet>=3.1.0",
        "mmpose",
    ]
    subprocess.run([sys.executable, "-m", "pip", "install", *pkgs])

    # Cài đặt mmcv cho mmpose
    try:
        import mmcv
        print("      ✅ mmcv đã có sẵn!")
    except ImportError:
        print("      👉 Đang cài đặt mmcv cho mmpose...")
        subprocess.run([sys.executable, "-m", "pip", "install", "openmim"])
        r = subprocess.run([sys.executable, "-m", "mim", "install", "mmcv>=2.0.1"])
        if r.returncode != 0:
            subprocess.run([
                sys.executable, "-m", "pip", "install", "mmcv==2.0.1",
                "-f", "https://download.openmmlab.com/mmcv/dist/cu118/torch2.0/index.html",
            ])
    print("      ✅ Hoàn tất cài đặt thư viện!")


def download_weights():
    print("\n[3/3] ⬇️ Đang kiểm tra và tải model weights cho MuseTalk...")
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    files_to_download = [
        ("yzd-v/DWPose", "dw-ll_ucoco_384.pth", "dwpose"),
        ("ManyOtherFunctions/face-parse-bisent", "79999_iter.pth", "face-parse-bisent"),
        ("ManyOtherFunctions/face-parse-bisent", "resnet18-5c106cde.pth", "face-parse-bisent"),
        ("openai/whisper-tiny", "config.json", "whisper"),
        ("openai/whisper-tiny", "pytorch_model.bin", "whisper"),
        ("openai/whisper-tiny", "preprocessor_config.json", "whisper"),
        ("stabilityai/sd-vae-ft-mse", "config.json", "sd-vae"),
        ("stabilityai/sd-vae-ft-mse", "diffusion_pytorch_model.bin", "sd-vae"),
        ("TMElyralab/MuseTalk", "musetalkV15/unet.pth", "musetalkV15"),
        ("TMElyralab/MuseTalk", "musetalk/musetalk.json", "musetalk"),
    ]

    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "huggingface_hub", "--quiet"])
        from huggingface_hub import hf_hub_download

    # Check local dropbox cache if available
    dropbox_models = [
        Path.home() / "Dropbox" / "PC" / "Downloads" / "musetalk_models",
        Path("C:/Users/Admin/Dropbox/PC/Downloads/musetalk_models"),
    ]

    for repo_id, filename, subfolder in files_to_download:
        target_dir = MODELS_DIR / subfolder
        target_dir.mkdir(parents=True, exist_ok=True)
        dest_file = target_dir / Path(filename).name

        if dest_file.is_file() and dest_file.stat().st_size > 1000:
            print(f"  [OK] {subfolder}/{dest_file.name} ({dest_file.stat().st_size / (1024*1024):.1f} MB)")
            continue

        # Check Dropbox cache first
        found_cache = False
        for dm in dropbox_models:
            cache_cand = dm / subfolder / Path(filename).name
            if cache_cand.is_file() and cache_cand.stat().st_size > 1000:
                print(f"  👉 Sao chép từ Dropbox cache: {subfolder}/{dest_file.name}...")
                shutil.copy2(cache_cand, dest_file)
                found_cache = True
                break

        if found_cache:
            continue

        print(f"  [DOWNLOADING] {subfolder}/{dest_file.name} từ {repo_id}...")
        try:
            hf_hub_download(
                repo_id=repo_id,
                filename=filename,
                local_dir=str(target_dir if "/" not in filename else MODELS_DIR),
                local_dir_use_symlinks=False,
            )
            print(f"  ✅ Đã tải: {dest_file.name}")
        except Exception as e:
            print(f"  ❌ Lỗi tải {filename}: {e}")

    # Copy config for musetalkV15 if missing
    cfg_src = MODELS_DIR / "musetalk" / "musetalk.json"
    cfg_dst = MODELS_DIR / "musetalkV15" / "musetalk.json"
    if cfg_src.is_file() and not cfg_dst.is_file():
        shutil.copy2(cfg_src, cfg_dst)

    print("\n🎉 Tất cả mã nguồn & mô hình MuseTalk đã sẵn sàng 100%!")


if __name__ == "__main__":
    unpack_codebase()
    install_deps()
    download_weights()
