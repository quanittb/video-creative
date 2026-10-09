"""Direct Verification for Stage 1: LivePortrait 1080p Full-Resolution Pasteback.
Animates a character portrait with natural 3D head motion, eye blinking,
and subtle gestures from natural_driving_template.mp4, maintaining 1080p/4K crispness.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent


def find_character_image(char_type: str = "male") -> Path:
    if char_type == "female":
        folder = ROOT_DIR / "assets" / "characters" / "nhanvatnu"
    elif char_type == "pixar":
        folder = ROOT_DIR / "assets" / "characters" / "hoathinhnu"
    else:
        folder = ROOT_DIR / "assets" / "characters" / "nhanvatnam"
    images = list(folder.glob("*.png")) + list(folder.glob("*.jpg"))
    if images:
        return images[0]
    any_images = list((ROOT_DIR / "assets" / "characters").rglob("*.png"))
    if any_images:
        return any_images[0]
    raise FileNotFoundError("Không tìm thấy ảnh nhân vật trong assets/characters/")


def ensure_dependencies():
    packages = {
        "tyro": "tyro",
        "pykalman": "pykalman",
        "yaml": "pyyaml",
        "scipy": "scipy",
        "imageio": "imageio",
        "onnxruntime": "onnxruntime-gpu",
        "insightface": "insightface",
        "ffmpeg": "ffmpeg-python",
    }
    missing = []
    for mod, pkg in packages.items():
        try:
            __import__(mod)
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"[!] Đang tự động cài đặt các gói còn thiếu: {missing}...")
        subprocess.run([sys.executable, "-m", "pip", "install", *missing, "--quiet"])
        print("  ✅ Đã cài đặt thành công!")


def main():
    print("=" * 70)
    print("🎬 KIỂM TRA ĐỘ NÉT 1080P - LIVEPORTRAIT STAGE 1 (FULL PASTEBACK)")
    print("=" * 70)
    ensure_dependencies()

    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--char", choices=["male", "female", "pixar"], default="male", help="Loại nhân vật test")
    args, _ = parser.parse_known_args()

    char_img = find_character_image(args.char)
    driving = ROOT_DIR / "assets" / "driving_templates" / "natural_driving_template.mp4"
    out_dir = ROOT_DIR / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_vid = out_dir / "stage1_liveportrait_1080p.mp4"

    print(f"\n[1/3] 👤 Ảnh nhân vật nguồn: {char_img.name}")
    print(f"[2/3] 🎥 Mẫu chuyển động tự nhiên: {driving.name}")

    # Extract audio from driving template so the test video has real voice matching lip motion
    temp_dir = ROOT_DIR / "temp" / "stage1_test"
    temp_dir.mkdir(parents=True, exist_ok=True)
    test_audio = temp_dir / "test_speech.wav"
    subprocess.run([
        "ffmpeg", "-y", "-i", str(driving), "-vn", "-t", "8",
        "-ar", "16000", "-ac", "1", str(test_audio)
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not test_audio.is_file() or test_audio.stat().st_size < 1000:
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono", "-t", "8",
            str(test_audio)
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    from core.lipsync_engine import LipsyncEngine
    lp_dir = LipsyncEngine._find_liveportrait_dir()
    if not lp_dir:
        print("\n❌ CHƯA TÌM THẤY THƯ MỤC LIVEPORTRAIT!")
        print("Vui lòng đảm bảo LivePortrait đã được tải về trên máy (Downloads, Desktop, hoặc thư mục gốc dự án).")
        return

    print(f"[3/3] 🚀 Đang render LivePortrait tại: {lp_dir}...")
    from runners.liveportrait_runner import run_liveportrait
    start_t = time.time()
    ok = run_liveportrait(
        source_img=str(char_img),
        driving_video=str(driving),
        audio_path=str(test_audio),
        output_path=str(out_vid),
        liveportrait_dir=str(lp_dir),
    )

    dur = time.time() - start_t
    if ok and out_vid.is_file():
        print(f"\n🎉 THÀNH CÔNG RENDER XONG TRONG: {dur:.2f}s!")
        print(f"📁 Video xuất: {out_vid}")
        try:
            res = subprocess.check_output([
                "ffprobe", "-v", "error", "-show_entries", "stream=width,height",
                "-of", "default=noprint_wrappers=1", str(out_vid)
            ], text=True)
            print(f"📐 Độ phân giải xuất: {res.strip()}")
        except Exception:
            pass

        # Tự động đồng bộ sang Dropbox nếu có để xem ngay trên máy chính
        dropbox_dirs = [
            Path.home() / "Dropbox" / "PC" / "Downloads",
            Path("C:/Users/Admin/Dropbox/PC/Downloads"),
            Path("C:/Users/quant/Dropbox/PC/Downloads"),
        ]
        for dp in dropbox_dirs:
            if dp.is_dir():
                try:
                    target_file = dp / out_vid.name
                    shutil.copy2(str(out_vid), str(target_file))
                    print(f"🚀 Đã tự động đồng bộ sang Dropbox: {target_file}")
                    break
                except Exception:
                    pass

        if os.name == "nt":
            os.startfile(str(out_vid))
    else:
        print("\n❌ Render chưa thành công. Vui lòng kiểm tra nhật ký log.")


if __name__ == "__main__":
    main()
