"""Automated Setup for LivePortrait on Windows (RTX 3060 12GB).
Installs LivePortrait repository, required dependencies, and downloads model weights (~1.5GB).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

def find_project_root() -> Path:
    candidates = [
        Path.cwd(),
        Path(__file__).resolve().parent,
        Path("C:/Users/Admin/Downloads/video-creative-studio/video-creative-studio"),
        Path("C:/Users/Admin/Downloads/video-creative-studio"),
        Path.home() / "Downloads" / "video-creative-studio" / "video-creative-studio",
        Path.home() / "Downloads" / "video-creative-studio",
        Path("D:/rustProject/video-creative-studio"),
    ]
    for c in candidates:
        if (c / "test_option_b_avatar.py").is_file():
            return c
    return Path(__file__).resolve().parent

ROOT_DIR = find_project_root()
LP_DIR = ROOT_DIR / "LivePortrait"
WEIGHTS_DIR = LP_DIR / "pretrained_weights"


def log(msg: str):
    print(msg, flush=True)


def setup_codebase() -> bool:
    infer_py = LP_DIR / "inference.py"
    if infer_py.is_file():
        log("[1/4] ✅ Mã nguồn LivePortrait đã có sẵn tại thư mục dự án.")
        return True

    log("[1/4] 🔍 Đang tìm kiếm mã nguồn LivePortrait...")
    candidates = [
        Path.home() / "Downloads" / "LivePortrait",
        Path.home() / "Desktop" / "LivePortrait",
        Path("C:/Users/Admin/Downloads/LivePortrait"),
        Path("C:/Users/Admin/Desktop/LivePortrait"),
        Path("C:/LivePortrait"),
        Path("D:/LivePortrait"),
    ]
    for c in candidates:
        if (c / "inference.py").is_file():
            log(f"      👉 Đã tìm thấy LivePortrait tại {c}, đang sao chép...")
            try:
                shutil.copytree(str(c), str(LP_DIR), dirs_exist_ok=True)
                log("      ✅ Đã sao chép LivePortrait thành công!")
                return True
            except Exception as e:
                log(f"      [!] Lỗi khi sao chép từ {c}: {e}")

    # Clone via git or download zip via urllib
    git_bin = shutil.which("git")
    if git_bin:
        log("      👉 Đang tải mã nguồn LivePortrait từ GitHub bằng Git...")
        try:
            subprocess.run([git_bin, "clone", "--depth", "1", "https://github.com/KwaiVGI/LivePortrait.git", str(LP_DIR)], check=True)
            if (LP_DIR / "inference.py").is_file():
                log("      ✅ Tải mã nguồn qua Git thành công!")
                return True
        except Exception as e:
            log(f"      [!] Git clone thất bại: {e}, chuyển sang tải qua HTTP...")

    # Fallback to direct zip download
    zip_url = "https://github.com/KwaiVGI/LivePortrait/archive/refs/heads/main.zip"
    zip_dest = ROOT_DIR / "LivePortrait.zip"
    log(f"      👉 Đang tải mã nguồn từ {zip_url}...")
    try:
        urllib.request.urlretrieve(zip_url, str(zip_dest))
        with zipfile.ZipFile(zip_dest, "r") as zf:
            zf.extractall(ROOT_DIR)
        extracted = ROOT_DIR / "LivePortrait-main"
        if extracted.is_dir():
            if LP_DIR.exists():
                shutil.rmtree(LP_DIR, ignore_errors=True)
            extracted.rename(LP_DIR)
        zip_dest.unlink(missing_ok=True)
        log("      ✅ Đã giải nén mã nguồn LivePortrait thành công!")
        return True
    except Exception as e:
        log(f"      ❌ Không thể tải mã nguồn LivePortrait: {e}")
        return False


def install_dependencies():
    log("\n[2/4] 📦 Đang kiểm tra và cài đặt thư viện cho LivePortrait...")
    pkgs = [
        "pykalman",
        "tyro",
        "onnxruntime-gpu",
        "insightface",
        "pyyaml",
        "scipy",
        "imageio",
        "imageio-ffmpeg",
        "rich",
        "pyyaml-include",
        "huggingface_hub",
        "dill",
        "ffmpeg-python",
        "scikit-image",
    ]
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", *pkgs, "--user", "--quiet"], check=True)
        # Always pin numpy 1.26.4 to prevent NumPy 2.x ABI conflicts with mmcv/cv2/xtcocotools
        subprocess.run([sys.executable, "-m", "pip", "install", "numpy==1.26.4", "librosa", "soundfile", "einops", "omegaconf", "--user", "--quiet"], check=True)
        log("      ✅ Đã cài đặt đầy đủ các thư viện cần thiết (khóa numpy==1.26.4)!")
    except Exception as e:
        log(f"      [!] Cài đặt gói tự động: {e}")


def check_weights_exist() -> bool:
    check_files = [
        WEIGHTS_DIR / "liveportrait" / "base_models" / "appearance_feature_extractor.pth",
        WEIGHTS_DIR / "base_models" / "appearance_feature_extractor.pth",
    ]
    return any(f.is_file() and f.stat().st_size > 1_000_000 for f in check_files)


def download_weights() -> bool:
    log("\n[3/4] 📥 Đang kiểm tra mô hình LivePortrait pretrained weights...")
    WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)
    if check_weights_exist():
        log("      ✅ Model weights LivePortrait đã có sẵn đầy đủ 100%!")
        return True

    log("      👉 Đang tải model weights LivePortrait từ Hugging Face (~1.5GB)...")
    log("      (Quá trình này chỉ chạy 1 lần duy nhất, vui lòng giữ kết nối mạng)")
    try:
        from huggingface_hub import snapshot_download
        repo_names = ["KlingTeam/LivePortrait", "KwaiVGI/LivePortrait"]
        success = False
        for repo in repo_names:
            try:
                log(f"      -> Đang tải từ Hugging Face repository '{repo}'...")
                snapshot_download(
                    repo_id=repo,
                    local_dir=str(WEIGHTS_DIR),
                    ignore_patterns=["*.md", "*.git*", "docs/*"],
                )
                if check_weights_exist():
                    success = True
                    break
            except Exception as ex:
                log(f"      [!] Không tải được từ {repo}: {ex}")

        if success:
            log("      ✅ Tải toàn bộ model weights thành công!")
            return True
        else:
            log("      ❌ Chưa hoàn tất tải model weights.")
            return False
    except ImportError:
        log("      [!] Chưa có huggingface_hub, đang cài đặt...")
        subprocess.run([sys.executable, "-m", "pip", "install", "huggingface_hub", "--user"])
        return download_weights()


def ensure_driving_template():
    log("\n[4/4] 🎥 Đang kiểm tra driving template...")
    dest_dir = ROOT_DIR / "assets" / "driving_templates"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_file = dest_dir / "natural_driving_template.mp4"
    if dest_file.is_file() and dest_file.stat().st_size > 10000:
        log("      ✅ Driving template natural_driving_template.mp4 đã sẵn sàng.")
        return

    candidates = [
        ROOT_DIR / "assets" / "natural_driving_template.mp4",
        ROOT_DIR / "natural_driving_template.mp4",
        Path.home() / "Dropbox" / "PC" / "Downloads" / "natural_driving_template.mp4",
        Path("C:/Users/Admin/Dropbox/PC/Downloads/natural_driving_template.mp4"),
        Path("C:/Users/quant/Dropbox/PC/Downloads/natural_driving_template.mp4"),
        Path.home() / "Downloads" / "natural_driving_template.mp4",
        Path("C:/Users/Admin/Downloads/natural_driving_template.mp4"),
    ]
    for c in candidates:
        if c.is_file() and c.stat().st_size > 10000:
            try:
                shutil.copy2(str(c), str(dest_file))
                log(f"      ✅ Đã sao chép driving template từ {c} sang {dest_file}")
                return
            except Exception as e:
                log(f"      [!] Lỗi copy: {e}")
    log("      [!] Chưa tìm thấy natural_driving_template.mp4 trong thư mục, vui lòng copy vào assets/driving_templates/")


def main():
    log("=" * 70)
    log("🎬 CÀI ĐẶT TỰ ĐỘNG LIVEPORTRAIT (CHẶNG 1: CỬ ĐỘNG ĐẦU 3D & BIỂU CẢM)")
    log("=" * 70)
    log(f"Python: {sys.executable}")

    ok_code = setup_codebase()
    if not ok_code:
        log("❌ Cài đặt thất bại ở bước mã nguồn!")
        return

    install_dependencies()
    ok_weights = download_weights()
    ensure_driving_template()

    log("\n" + "=" * 70)
    if ok_weights:
        log("🎉 CHÚC MỪNG! LivePortrait đã được cài đặt và cấu hình hoàn tất 100%!")
        log("🚀 Đang tự động kích hoạt Pipeline 2 Chặng (Cử động đầu 3D + Khớp khẩu hình tiếng Việt)...")
        log("=" * 70 + "\n")
        runner_script = ROOT_DIR / "test_option_b_avatar.py"
        if runner_script.is_file():
            subprocess.run([sys.executable, str(runner_script), "--char", "male"])
    else:
        log("⚠️ Đã cài đặt mã nguồn nhưng weights chưa hoàn tất. Vui lòng kiểm tra kết nối mạng và thử lại.")
        log("=" * 70)


if __name__ == "__main__":
    main()
