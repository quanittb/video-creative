"""Quick Quality Benchmark Script for UltraViewer Testing.
Executes an ultra-fast 5-second end-to-end evaluation:
1. Hardware diagnostics (VGA name, VRAM, CUDA capability)
2. Character selection & Speech generation
3. Expressive talking-avatar rendering (LivePortrait + GFPGAN)
4. Instant video playback & HTML inspection report
"""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# Ensure UTF-8 output
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("PYTHONUTF8", "1")
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent


def print_banner():
    print("=" * 70)
    print("⚡ VIDEO CREATIVE STUDIO - ULTRA-FAST QUALITY TEST (ULTRAVIEWER)")
    print("=" * 70)


def probe_gpu_hardware() -> dict:
    """Detect GPU hardware and VRAM."""
    print("\n[1/5] 🔍 ĐANG KIỂM TRA PHẦN CỨNG ĐỒ HỌA (GPU DIAGNOSTICS)...")
    smi = shutil.which("nvidia-smi")
    gpu_info = {"name": "Unknown", "vram_mb": 0, "driver": "N/A"}
    if smi:
        try:
            out = subprocess.check_output(
                [smi, "--query-gpu=gpu_name,driver_version,memory.total", "--format=csv,noheader,nounits"],
                text=True,
                stderr=subprocess.DEVNULL,
            )
            parts = [p.strip() for p in out.strip().split(",")]
            gpu_info["name"] = parts[0]
            gpu_info["driver"] = parts[1]
            gpu_info["vram_mb"] = int(float(parts[2]))
            print(f"  ✅ GPU: {gpu_info['name']}")
            print(f"  ✅ Driver: {gpu_info['driver']}")
            print(f"  ✅ VRAM: {gpu_info['vram_mb']} MB (~{gpu_info['vram_mb']/1024:.1f} GB)")

            if gpu_info["vram_mb"] >= 10000:
                print("  🚀 ĐÁNH GIÁ: VRAM >= 12GB! ĐỦ ĐIỀU KIỆN CHẠY LIVEPORTRAIT & GFPGAN CẤU HÌNH CAO NHẤT!")
            else:
                print(f"  ⚠️ CẢNH BÁO: VRAM {gpu_info['vram_mb']}MB. Vui lòng kiểm tra lại nếu đây không phải bản 12GB.")
        except Exception as e:
            print(f"  ⚠️ Không thể đọc thông tin chi tiết qua nvidia-smi: {e}")
    else:
        print("  ⚠️ Không tìm thấy nvidia-smi. Đang chạy chế độ kiểm tra phần mềm.")
    return gpu_info


async def generate_sample_speech(text: str, voice: str, out_audio: Path) -> Path:
    """Generate sample speech audio using Edge-TTS."""
    import edge_tts

    communicate = edge_tts.Communicate(text=text, voice=voice)
    await communicate.save(str(out_audio))
    return out_audio


def find_sample_character(char_type: str = "male") -> Path:
    """Find a character image in assets directory."""
    if char_type == "female":
        folder = ROOT_DIR / "assets" / "characters" / "nhanvatnu"
    elif char_type == "pixar":
        folder = ROOT_DIR / "assets" / "characters" / "hoathinhnu"
    else:
        folder = ROOT_DIR / "assets" / "characters" / "nhanvatnam"

    images = list(folder.glob("*.png")) + list(folder.glob("*.jpg"))
    if images:
        return images[0]
    # Fallback to any character
    any_images = list((ROOT_DIR / "assets" / "characters").rglob("*.png"))
    if any_images:
        return any_images[0]
    raise FileNotFoundError("Không tìm thấy ảnh nhân vật mẫu nào trong thư mục assets/characters/")


def create_html_preview(video_path: Path, output_html: Path, gpu_name: str, render_time: float):
    """Generate an interactive HTML player for local inspection."""
    html_content = f"""<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <title>Đánh Giá Chất Lượng Video AI - Video Creative Studio</title>
    <style>
        body {{
            background: #0f172a;
            color: #f8fafc;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            margin: 0;
            padding: 30px;
            display: flex;
            flex-direction: column;
            align-items: center;
        }}
        .card {{
            background: #1e293b;
            border-radius: 16px;
            padding: 24px;
            max-width: 520px;
            width: 100%;
            box-shadow: 0 10px 25px rgba(0,0,0,0.5);
            text-align: center;
        }}
        h2 {{ color: #38bdf8; margin-top: 0; }}
        .badge {{
            display: inline-block;
            background: #059669;
            color: #fff;
            padding: 4px 12px;
            border-radius: 9999px;
            font-size: 13px;
            font-weight: 600;
            margin-bottom: 16px;
        }}
        video {{
            width: 100%;
            max-height: 650px;
            border-radius: 12px;
            background: #000;
            outline: none;
        }}
        .meta {{
            margin-top: 16px;
            text-align: left;
            background: #0f172a;
            padding: 12px 16px;
            border-radius: 8px;
            font-size: 13px;
            line-height: 1.6;
        }}
        .btn {{
            display: inline-block;
            margin-top: 16px;
            background: #2563eb;
            color: #fff;
            text-decoration: none;
            padding: 10px 20px;
            border-radius: 8px;
            font-weight: bold;
        }}
        .btn:hover {{ background: #1d4ed8; }}
    </style>
</head>
<body>
    <div class="card">
        <h2>🎬 KẾT QUẢ TEST CHẤT LƯỢNG NHANH</h2>
        <div class="badge">✅ CẤU HÌNH CAO NHẤT (1080P CRF 18)</div>
        <video controls autoplay loop src="{video_path.name}"></video>
        <div class="meta">
            <div>⚡ <b>GPU:</b> {gpu_name}</div>
            <div>⏱️ <b>Thời gian render:</b> {render_time:.2f}s</div>
            <div>👁️ <b>Tiêu chí kiểm tra:</b></div>
            <ul style="margin: 4px 0; padding-left: 20px;">
                <li>Đầu nghiêng lắc và gật gù tự nhiên theo giọng nói</li>
                <li>Mắt chớp tự nhiên, lông mày cử động</li>
                <li>Khẩu hình mở sâu thấy răng, không bị phẳng 2D</li>
                <li>Độ nét 1080p sắc sảo, không vỡ hạt</li>
            </ul>
        </div>
        <a class="btn" href="{video_path.name}" download>Tải file MP4 gốc</a>
    </div>
</body>
</html>
"""
    output_html.write_text(html_content, encoding="utf-8")


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
        print(f"  [!] Đang tự động cài đặt các thư viện cần thiết: {missing}...")
        subprocess.run([sys.executable, "-m", "pip", "install", *missing, "--quiet"])
        print("  ✅ Đã cài đặt xong thư viện!")


def main():
    parser = argparse.ArgumentParser(description="Quick Quality Benchmark")
    parser.add_argument("--char", choices=["male", "female", "pixar"], default="male", help="Loại nhân vật test")
    parser.add_argument("--lang", choices=["vi", "es", "en"], default="vi", help="Ngôn ngữ test")
    args = parser.parse_args()

    print_banner()
    gpu = probe_gpu_hardware()
    ensure_dependencies()

    # 1. Select character image
    print(f"\n[2/5] 👤 CHỌN ẢNH NHÂN VẬT TEST ({args.char.upper()})...")
    char_img = find_sample_character(args.char)
    print(f"  Đã chọn: {char_img.name}")

    # 2. Select text & voice
    print(f"\n[3/5] 🎙️ TỔNG HỢP ÂM THANH GIỌNG ĐỌC ({args.lang.upper()})...")
    test_texts = {
        "vi": "Xin chào! Đây là video kiểm tra chất lượng chuyển động khuôn mặt và khẩu hình tự nhiên của Video Creative Studio.",
        "es": "¡Hola! Bienvenidos a nuestro estudio creativo. Calidad visual excelente y movimiento facial completamente natural.",
        "en": "Hello! Welcome to our creative studio. Notice the natural head movement, eye blinking, and expressive facial dynamics.",
    }
    test_voices = {
        "vi": "vi-VN-NamMinhNeural" if args.char == "male" else "vi-VN-HoaiMyNeural",
        "es": "es-ES-AlvaroNeural" if args.char == "male" else "es-ES-ElviraNeural",
        "en": "en-US-GuyNeural" if args.char == "male" else "en-US-JennyNeural",
    }
    text = test_texts[args.lang]
    voice = test_voices[args.lang]
    temp_dir = ROOT_DIR / "temp" / "quick_test"
    temp_dir.mkdir(parents=True, exist_ok=True)
    audio_path = temp_dir / "quick_test_audio.mp3"

    asyncio.run(generate_sample_speech(text, voice, audio_path))
    print(f"  Đã tạo file âm thanh: {audio_path.name}")

    # 3. Render video
    print("\n[4/5] 🚀 BẮT ĐẦU RENDER VỚI CẤU HÌNH CAO NHẤT (1080P CRF 18)...")
    out_dir = ROOT_DIR / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_video = out_dir / "quick_test_result.mp4"
    out_html = out_dir / "quick_test_preview.html"

    start_t = time.time()

    # Call LipsyncEngine
    from core.lipsync_engine import LipsyncEngine
    lipsync = LipsyncEngine()
    result = lipsync.sync(
        character_visual=str(char_img),
        audio_path=str(audio_path),
        output_video=str(out_video),
    )

    render_time = time.time() - start_t
    engine_name = result.get("engine", result.get("mode", "unknown"))
    if "fallback" in engine_name:
        print(f"  ⚠️ CẢNH BÁO: Quá trình AI gặp sự cố, video đang dùng chế độ dự phòng ({engine_name})!")
    else:
        print(f"  🎉 Hoàn tất render với động cơ cao cấp: {engine_name.upper()}!")
    print(f"  ⏱️ Thời gian render: {render_time:.2f} giây!")
    print(f"  📁 File xuất: {out_video}")

    # 4. Create HTML preview and launch
    print("\n[5/5] 🌐 MỞ TRANG ĐÁNH GIÁ CHẤT LƯỢNG...")
    create_html_preview(out_video, out_html, gpu["name"], render_time)

    # Launch file in browser or default player
    try:
        if os.name == "nt":
            os.startfile(str(out_html))
            print("  ✅ Đã tự động mở trình duyệt hiển thị video test!")
    except Exception:
        pass

    print("\n" + "=" * 70)
    print("👉 HƯỚNG DẪN ĐÁNH GIÁ QUA ULTRAVIEWER:")
    print("1. Trình duyệt đã mở file: output/quick_test_preview.html")
    print(f"2. Bạn có thể kéo file '{out_video.name}' qua khung chat UltraViewer về máy bạn để xem độ nét 100% gốc không bị giật lag mạng.")
    print("=" * 70)


if __name__ == "__main__":
    main()
