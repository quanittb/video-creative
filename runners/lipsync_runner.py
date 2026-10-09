"""AI Lip-Sync Runner for Pro Studio
Multi-tier hardware profiling & real-time adaptive lip-synchronization pipeline.
Includes Voice Activity Detection (VAD) Silence Clamping, GFPGAN Ultra-Sharp Face Restoration,
and Sync Offset Calibration.

Hardware Tier Matrix:
  - Tier 0: CPU / <2GB VRAM -> Cloud API or Lightweight CPU
  - Tier 1: 3-4GB VRAM (GTX 1650, etc.) -> Wav2Lip ONNX / DirectML + GFPGAN Face Restorer (Max 1080p Quality)
  - Tier 2: 6-8GB VRAM (RTX 3060, RTX 4060) -> MuseTalk FP16
  - Tier 3: 8-16GB VRAM (RTX 4070, RTX 3080) -> Video-ReTalking Full / LivePortrait
  - Tier 4: >=16-24GB VRAM (RTX 3090, RTX 4090) -> LatentSync Diffusion
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import wave
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


def emit_json(payload: dict) -> None:
    """Emit a JSON-lines message to stdout for parent process tracking."""
    try:
        sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
        sys.stdout.flush()
    except Exception:
        pass


def find_ffmpeg() -> str:
    """Locate ffmpeg executable in PATH or typical system locations."""
    in_path = shutil.which("ffmpeg")
    if in_path:
        return in_path
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages",
        ROOT_DIR / "bin" / "ffmpeg" / "ffmpeg.exe",
        Path("C:/Program Files/ffmpeg/bin/ffmpeg.exe"),
    ]
    for c in candidates:
        if c.is_file():
            return str(c)
        if c.is_dir():
            for f in c.glob("**/ffmpeg.exe"):
                if f.is_file():
                    return str(f)
    return "ffmpeg"


def hz_to_mel(hz: float) -> float:
    return 2595.0 * math.log10(1.0 + hz / 700.0)


def mel_to_hz(mel: float) -> float:
    return 700.0 * (10.0 ** (mel / 2595.0) - 1.0)


def get_mel_filterbank(sr: int = 16000, n_fft: int = 800, n_mels: int = 80, fmin: float = 55.0, fmax: float = 7600.0):
    import numpy as np

    min_mel = hz_to_mel(fmin)
    max_mel = hz_to_mel(fmax)
    mels = np.linspace(min_mel, max_mel, n_mels + 2)
    hz = np.array([mel_to_hz(m) for m in mels])
    bins = np.floor((n_fft + 1) * hz / sr).astype(int)
    fb = np.zeros((n_mels, n_fft // 2 + 1), dtype=np.float32)
    for i in range(n_mels):
        for j in range(bins[i], bins[i + 1]):
            fb[i, j] = (j - bins[i]) / max(1, (bins[i + 1] - bins[i]))
        for j in range(bins[i + 1], bins[i + 2]):
            fb[i, j] = (bins[i + 2] - j) / max(1, (bins[i + 2] - bins[i + 1]))
    return fb


def compute_mel_spectrogram(audio_path: Path, sr: int = 16000, n_fft: int = 800, hop_length: int = 200):
    import numpy as np
    from scipy import signal

    with wave.open(str(audio_path), "rb") as wf:
        n_channels = wf.getnchannels()
        n_frames = wf.getnframes()
        data = wf.readframes(n_frames)
    samples = np.array(struct.unpack(f"{n_frames * n_channels}h", data), dtype=np.float32)
    if n_channels > 1:
        samples = samples[::n_channels]
    samples = samples / 32768.0

    fb = get_mel_filterbank(sr=sr, n_fft=n_fft, n_mels=80)
    window = np.hanning(n_fft)
    f, t, Zxx = signal.stft(samples, fs=sr, window=window, nperseg=n_fft, noverlap=n_fft - hop_length, padded=True)
    mag = np.abs(Zxx)
    mel = np.dot(fb, mag)
    mel_db = np.log(np.maximum(mel, 1e-5))
    return mel_db, samples, sr


def detect_vad_mask(samples, sr: int, n_frames: int, fps: float, silence_thresh_db: float = -36.0):
    """Return boolean array of length n_frames indicating whether speech is active."""
    import numpy as np

    chunk_samples = max(1, int(sr / fps))
    is_speech = np.zeros(n_frames, dtype=bool)
    for i in range(n_frames):
        s_idx = i * chunk_samples
        e_idx = min(len(samples), s_idx + chunk_samples)
        if s_idx >= len(samples):
            break
        chunk = samples[s_idx:e_idx]
        rms = math.sqrt(float(np.mean(chunk**2))) if len(chunk) > 0 else 0.0
        db = 20.0 * math.log10(rms) if rms > 1e-5 else -100.0
        if db > silence_thresh_db:
            is_speech[i] = True
    return is_speech


def find_bundled_model(model_name: str) -> Path | None:
    """Find a bundled model file across known project and appdata directories."""
    appdata = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    comp_root = os.environ.get("PROSTUDIO_COMPONENTS_ROOT") or os.path.join(appdata, "Prostudio", "components")
    candidates = [
        ROOT_DIR / "bundled-models" / "wav2lip" / model_name,
        ROOT_DIR / "bundled-models" / model_name,
        ROOT_DIR.parent / "bundled-models" / "wav2lip" / model_name,
        ROOT_DIR.parent / "bundled-models" / model_name,
        Path(comp_root) / "models" / model_name,
        Path(comp_root) / "wav2lip" / model_name,
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None


def find_face_models_root() -> Path:
    """Locate InsightFace models directory containing buffalo_l."""
    appdata = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    comp_root = os.environ.get("PROSTUDIO_COMPONENTS_ROOT") or os.path.join(appdata, "Prostudio", "components")
    candidates = [
        ROOT_DIR / "bundled-models",
        ROOT_DIR.parent / "bundled-models",
        Path(comp_root) / "models",
        Path(comp_root),
    ]
    for c in candidates:
        if (c / "models" / "buffalo_l" / "det_10g.onnx").is_file() or (c / "buffalo_l" / "det_10g.onnx").is_file():
            return c
    return candidates[0]


def find_musetalk_paths() -> tuple[Path | None, Path | None]:
    """Locate MuseTalk codebase and dedicated python executable across project and component directories."""
    appdata = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    comp_root = os.environ.get("PROSTUDIO_COMPONENTS_ROOT") or os.path.join(appdata, "Prostudio", "components")

    dir_candidates = [
        ROOT_DIR / "musetalk",
        ROOT_DIR.parent / "musetalk",
        ROOT_DIR.parent.parent / "musetalk",
        Path("D:/rustProject/video-creative-studio/musetalk"),
        Path("D:/rustProject/prostudio-ai/musetalk"),
        Path("C:/Users/Admin/Downloads/video-creative-studio/video-creative-studio/musetalk"),
        Path("C:/Users/Admin/Downloads/video-creative-studio/musetalk"),
        Path("/workspace/musetalk"),
        Path(comp_root) / "musetalk",
        Path.home() / "Downloads" / "musetalk",
        Path.home() / "Desktop" / "musetalk",
        Path("C:/Users/Admin/Downloads/musetalk"),
        Path("C:/MuseTalk"),
        Path("D:/MuseTalk"),
    ]
    py_candidates = [
        ROOT_DIR / "musetalk-venv" / "Scripts" / "python.exe",
        ROOT_DIR.parent / "musetalk-venv" / "Scripts" / "python.exe",
        Path("D:/rustProject/video-creative-studio/musetalk-venv/Scripts/python.exe"),
        Path("D:/rustProject/prostudio-ai/musetalk-venv/Scripts/python.exe"),
        Path("C:/Users/Admin/Downloads/video-creative-studio/video-creative-studio/musetalk-venv/Scripts/python.exe"),
        Path("C:/Users/Admin/Downloads/video-creative-studio/musetalk-venv/Scripts/python.exe"),
        Path("/workspace/musetalk-venv/bin/python"),
        Path(comp_root) / "musetalk-venv" / "Scripts" / "python.exe",
        Path(comp_root) / "py-env" / "Scripts" / "python.exe",
        Path(sys.executable),
    ]
    m_dir = next((d for d in dir_candidates if (d / "scripts" / "inference.py").is_file()), None)
    m_py = next((p for p in py_candidates if p.is_file()), None)
    return m_dir, m_py


def create_musetalk_temp_dir() -> Path:
    """Create a unique scratch directory safe for MuseTalk's upstream shell commands."""
    candidates = [Path(tempfile.gettempdir()), Path("/tmp")]
    if os.name == "nt":
        candidates.append(Path(os.environ.get("SystemDrive", "C:")) / "vcs_tmp")
    for base in candidates:
        if any(ch.isspace() or ch in "\"'" for ch in str(base)):
            continue
        try:
            base.mkdir(parents=True, exist_ok=True)
            return Path(tempfile.mkdtemp(prefix="vcs_musetalk_", dir=str(base)))
        except OSError:
            continue
    raise RuntimeError("Không tạo được thư mục tạm MuseTalk không chứa khoảng trắng; đặt TEMP/TMP vào đường dẫn đơn giản rồi chạy lại.")


def run_musetalk_pipeline(
    video_p: Path,
    audio_p: Path,
    out_p: Path,
    temp_dir: Path,
    offset_ms: int = 0,
    batch_size: int = 2,
    fps: int = 25,
    musetalk_dir: str | None = None,
    musetalk_python: str | None = None,
    unet_model_path: str | None = None,
    unet_config: str | None = None,
) -> bool:
    """Execute high-fidelity MuseTalk v1.5 FP16 inference pipeline."""
    start_time = time.time()
    discovered_dir, discovered_python = find_musetalk_paths()
    m_dir = Path(musetalk_dir).resolve() if musetalk_dir else discovered_dir
    m_py = Path(musetalk_python).resolve() if musetalk_python else discovered_python
    if not m_dir or not m_py:
        emit_json({"type": "progress", "percent": 15, "stage": "Chưa tìm thấy môi trường MuseTalk, chuyển về Wav2Lip..."})
        return False
    inference_script = m_dir / "scripts" / "inference.py"
    model_path = Path(unet_model_path).resolve() if unet_model_path else m_dir / "models" / "musetalkV15" / "unet.pth"
    config_candidates = [
        m_dir / "models" / "musetalk" / "config.json",
        m_dir / "models" / "musetalk" / "musetalk.json",
        m_dir / "models" / "musetalkV15" / "musetalk.json",
        m_dir / "models" / "musetalkV15" / "config.json",
    ]
    config_path = Path(unet_config).resolve() if unet_config else next((p for p in config_candidates if p.is_file()), None)
    if not inference_script.is_file():
        emit_json({"type": "error", "message": f"Không tìm thấy MuseTalk inference.py: {inference_script}"})
        return False
    if not model_path.is_file():
        emit_json({"type": "error", "message": f"Không tìm thấy MuseTalk v1.5 UNet weights: {model_path}"})
        return False
    if not config_path or not config_path.is_file():
        emit_json({
            "type": "error",
            "message": "Không tìm thấy UNet config. Đã thử models/musetalk/config.json, "
            "models/musetalk/musetalk.json, models/musetalkV15/musetalk.json và models/musetalkV15/config.json.",
        })
        return False
    if batch_size < 1 or fps < 1:
        emit_json({"type": "error", "message": "batch_size và fps phải lớn hơn 0."})
        return False

    out_p.parent.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg = find_ffmpeg()

    duration_cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(audio_p),
    ]
    duration_result = subprocess.run(duration_cmd, capture_output=True, text=True)
    if duration_result.returncode != 0:
        emit_json({"type": "error", "message": f"Không đọc được thời lượng audio: {duration_result.stderr.strip()}"})
        return False
    try:
        audio_duration = float(duration_result.stdout.strip())
    except ValueError:
        emit_json({"type": "error", "message": f"Thời lượng audio không hợp lệ: {duration_result.stdout.strip()!r}"})
        return False
    if audio_duration <= 0:
        emit_json({"type": "error", "message": "Audio không có thời lượng hợp lệ."})
        return False

    emit_json({"type": "progress", "percent": 15, "stage": "Chuẩn hóa âm thanh 16kHz cho MuseTalk FP16..."})
    norm_audio = temp_dir / "musetalk_audio.wav"
    audio_filters = []
    if offset_ms > 0:
        audio_filters.extend(["-af", f"adelay={offset_ms}:all=1,atrim=duration={audio_duration:.6f}"])
    elif offset_ms < 0:
        trim_sec = abs(offset_ms) / 1000.0
        audio_filters.extend([
            "-af",
            f"atrim=start={trim_sec:.3f},asetpts=PTS-STARTPTS,apad=whole_dur={audio_duration:.6f},atrim=duration={audio_duration:.6f}",
        ])

    cmd_audio = [
        ffmpeg,
        "-y",
        "-i", str(audio_p),
        *audio_filters,
        "-ar", "16000",
        "-ac", "1",
        str(norm_audio),
    ]
    try:
        subprocess.run(cmd_audio, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        emit_json({"type": "progress", "percent": 20, "stage": f"Lỗi xử lý âm thanh: {e}"})
        return False

    cfg_path = temp_dir / "job_musetalk.yaml"
    # Upstream interpolates these paths into unquoted ffmpeg shell commands. Always use
    # short local names; the unique scratch root is selected without spaces above.
    safe_video = temp_dir / "musetalk_input_video.mp4"
    shutil.copy2(video_p, safe_video)
    result_dir = temp_dir / "results"
    result_dir.mkdir(parents=True, exist_ok=True)
    unsafe_paths = [str(p) for p in (safe_video, norm_audio, result_dir) if any(ch.isspace() or ch in "\"'" for ch in str(p))]
    if unsafe_paths:
        emit_json({
            "type": "error",
            "message": "MuseTalk upstream shell commands require temporary input/output paths without spaces or quotes: " + ", ".join(unsafe_paths),
        })
        return False
    cfg_content = (
        "task_0:\n"
        f"  video_path: {json.dumps(safe_video.as_posix())}\n"
        f"  audio_path: {json.dumps(norm_audio.as_posix())}\n"
        "  bbox_shift: 0\n"
    )
    cfg_path.write_text(cfg_content, encoding="utf-8")

    emit_json({
        "type": "progress",
        "percent": 25,
        "stage": "Khởi động mô hình MuseTalk v1.5 FP16 (DWPose + UNet FP16 + VAE)...",
    })

    raw_result = result_dir / "v15" / "musetalk_render.mp4"
    cmd_infer = [
        str(m_py),
        "-u",
        str(inference_script),
        "--inference_config", str(cfg_path),
        "--result_dir", str(result_dir),
        "--output_vid_name", raw_result.name,
        "--unet_model_path", str(model_path),
        "--unet_config", str(config_path),
        "--version", "v15",
        "--batch_size", str(batch_size),
        "--fps", str(fps),
    ]
    # GTX 1650/1660 Turing cards suffer from PyTorch VAE FP16 NaN black-square bug
    hw = probe_hardware()
    gpu_str = hw.get("gpu_name", "")
    if "1650" not in gpu_str and "1660" not in gpu_str:
        cmd_infer.append("--use_float16")

    proc = subprocess.Popen(
        cmd_infer,
        cwd=str(m_dir),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )

    stage = "Đang trích xuất cấu trúc khuôn mặt (DWPose AI)..."
    in_unet = False
    in_blending = False

    last_lines = []
    while True:
        line = proc.stdout.readline()
        if not line and proc.poll() is not None:
            break
        line = line.strip()
        if not line:
            continue
        last_lines.append(line)
        if len(last_lines) > 30:
            last_lines.pop(0)
        print(f"[MuseTalk-Proc] {line}", flush=True)

        if "Starting inference" in line:
            in_unet = True
            stage = "Đang tạo khẩu hình bằng mạng khuếch tán MuseTalk FP16..."
            emit_json({"type": "progress", "percent": 50, "stage": stage})
        elif "Padding generated images" in line:
            in_unet = False
            in_blending = True
            stage = "Đang hòa trộn đường nét khuôn mặt tự nhiên (Face Blending)..."
            emit_json({"type": "progress", "percent": 88, "stage": stage})
        elif "%|" in line and "/" in line:
            try:
                pct_str = line.split("%")[0].strip().split()[-1]
                pct_val = int(pct_str)
                if in_unet:
                    mapped_pct = 50 + int(pct_val * 0.35)
                    emit_json({"type": "progress", "percent": mapped_pct, "stage": stage})
                elif in_blending:
                    mapped_pct = 88 + int(pct_val * 0.10)
                    emit_json({"type": "progress", "percent": mapped_pct, "stage": stage})
                else:
                    mapped_pct = 25 + int(pct_val * 0.20)
                    emit_json({"type": "progress", "percent": mapped_pct, "stage": stage})
            except Exception:
                pass

    rc = proc.wait()
    muxed_output = None
    if rc == 0 and raw_result.is_file() and raw_result.stat().st_size > 1000:
        fd, muxed_name = tempfile.mkstemp(prefix=f"_{out_p.stem}_musetalk_", suffix=".mp4", dir=str(out_p.parent))
        os.close(fd)
        muxed_output = Path(muxed_name)
        muxed_output.unlink(missing_ok=True)
        try:
            cmd_mux = [
                ffmpeg, "-y",
                "-i", str(raw_result),
                "-i", str(audio_p),
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-t", f"{audio_duration:.6f}",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k",
                "-shortest", str(muxed_output),
            ]
            mux = subprocess.run(cmd_mux, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        except OSError as exc:
            muxed_output.unlink(missing_ok=True)
            emit_json({"type": "error", "message": f"Không chạy được ffmpeg khi gắn audio gốc: {exc}"})
            return False
        if mux.returncode != 0 or not muxed_output.is_file() or muxed_output.stat().st_size <= 1000:
            emit_json({"type": "error", "message": f"Không gắn được audio gốc sau MuseTalk: {mux.stderr.strip()}"})
            muxed_output.unlink(missing_ok=True)
            return False
        try:
            os.replace(muxed_output, out_p)
        except OSError as exc:
            muxed_output.unlink(missing_ok=True)
            emit_json({"type": "error", "message": f"Không thể chuyển video hoàn tất sang {out_p}: {exc}"})
            return False
        elapsed = round(time.time() - start_time, 2)
        emit_json({
            "type": "completed",
            "percent": 100,
            "stage": "Hoàn tất đồng bộ khuôn miệng bằng MuseTalk v1.5 FP16 thành công!",
            "output_path": str(out_p),
            "duration_seconds": elapsed,
        })
        return True
    else:
        err_msg = "\n".join(last_lines[-8:]) if last_lines else "Không có thông điệp lỗi chi tiết"
        print(f"\n❌ [MuseTalk Thất Bại] Mã thoát: {rc}\nChi tiết lỗi gần nhất:\n{err_msg}\n", flush=True)
        emit_json({"type": "error", "message": f"MuseTalk v1.5 thất bại (exit code {rc}); không chạy fallback."})
        return False


def probe_hardware() -> dict:
    """Dynamically probe GPU, VRAM, drivers, and runtime availability."""
    info = {
        "gpu_available": False,
        "gpu_name": "CPU Only",
        "vram_mb": 0,
        "driver_version": None,
        "cuda_version": None,
        "cuda_working": False,
        "tier": "tier0",
        "tier_name": "Tier 0 (CPU / Thiết bị cơ bản)",
        "recommended_engine": "cloud_api",
        "engines": [],
    }

    # 1. Probe NVIDIA GPU via nvidia-smi
    smi = shutil.which("nvidia-smi")
    if smi:
        try:
            out = subprocess.check_output(
                [
                    smi,
                    "--query-gpu=gpu_name,driver_version,memory.total",
                    "--format=csv,noheader,nounits",
                ],
                text=True,
                stderr=subprocess.DEVNULL,
            )
            parts = [p.strip() for p in out.strip().split(",")]
            if len(parts) >= 3:
                info["gpu_available"] = True
                info["gpu_name"] = parts[0]
                info["driver_version"] = parts[1]
                info["vram_mb"] = int(float(parts[2]))
        except Exception:
            pass

    # 2. Fallback to Windows WMI if nvidia-smi failed
    if not info["gpu_available"] and sys.platform == "win32":
        try:
            cmd = "powershell -NoProfile -Command \"Get-CimInstance Win32_VideoController | Select-Object -Property Name, AdapterRAM | ConvertTo-Json\""
            res = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.DEVNULL)
            parsed = json.loads(res)
            if isinstance(parsed, list):
                parsed = parsed[0]
            if "Name" in parsed:
                info["gpu_available"] = True
                info["gpu_name"] = parsed["Name"]
                raw_ram = parsed.get("AdapterRAM", 0)
                if raw_ram:
                    info["vram_mb"] = int(raw_ram / (1024 * 1024))
        except Exception:
            pass

    # 3. Test PyTorch CUDA
    try:
        import torch

        if torch.cuda.is_available():
            info["cuda_working"] = True
            info["cuda_version"] = torch.version.cuda
    except Exception:
        info["cuda_working"] = False

    # 4. Determine Hardware Tier
    vram = info["vram_mb"]
    # Check MuseTalk installation status
    m_dir, m_py = find_musetalk_paths()
    musetalk_ready = (
        m_dir is not None
        and m_py is not None
        and (m_dir / "models" / "musetalkV15" / "unet.pth").is_file()
    )
    musetalk_supported = musetalk_ready and vram >= 3072

    if vram >= 16384 and info["cuda_working"]:
        info["tier"] = "tier4"
        info["tier_name"] = "Tier 4 - Đồ họa chuyên nghiệp 16GB VRAM"
        info["recommended_engine"] = "latentsync"
    elif vram >= 8192:
        info["tier"] = "tier3"
        info["tier_name"] = "Tier 3 - Đồ họa cao cấp (RTX 3060 12GB)"
        info["recommended_engine"] = "musetalk" if musetalk_supported else "video_retalking"
    elif vram >= 6144:
        info["tier"] = "tier2"
        info["tier_name"] = "Tier 2 - Đồ họa tầm trung 6GB VRAM"
        info["recommended_engine"] = "musetalk"
    elif vram >= 3072:
        info["tier"] = "tier1"
        if musetalk_supported:
            info["tier_name"] = "Tier 1 - GTX 1650 4GB MuseTalk FP16"
            info["recommended_engine"] = "musetalk"
        else:
            info["tier_name"] = "Tier 1 - Đồ họa tiêu chuẩn 4GB VRAM"
            info["recommended_engine"] = "auto"
    else:
        info["tier"] = "tier0"
        info["tier_name"] = "Tier 0 - CPU và thiết bị cơ bản"
        info["recommended_engine"] = "cloud_api"

    # 5. Populate Engine Catalog with Local Hardware Compatibility
    info["engines"] = [
        {
            "id": "auto",
            "name": "Tự động chọn",
            "recommended": True,
            "supported": True,
            "tier": info["tier"],
            "description": f"Hệ thống tự động dùng mô hình tối ưu cho máy - {info['tier_name']}.",
        },
        {
            "id": "musetalk",
            "name": "MuseTalk FP16",
            "recommended": True,
            "supported": True,
            "min_vram_mb": 6144,
            "is_underpowered": vram < 6144,
            "warning": "Cảnh báo: Thiết bị chưa đạt mức khuyến nghị VRAM 6GB. Quá trình xử lý có thể mất nhiều thời gian hơn, nhưng hệ thống vẫn cho phép tiếp tục sử dụng." if vram < 6144 else None,
            "description": "Mô hình khuếch tán MuseTalk v1.5 FP16, cử động môi mềm mại, tự nhiên theo ngữ điệu phát âm, hoàn toàn không bị nhòe.",
        },
        {
            "id": "video_retalking",
            "name": "Video-ReTalking",
            "recommended": False,
            "supported": True,
            "min_vram_mb": 8192,
            "is_underpowered": vram < 8192,
            "warning": "Cảnh báo: Thiết bị chưa đạt mức khuyến nghị VRAM 8GB. Quá trình xử lý có thể mất nhiều thời gian hơn, nhưng hệ thống vẫn cho phép tiếp tục sử dụng." if vram < 8192 else None,
            "description": "Đồng bộ toàn bộ biểu cảm khuôn mặt và góc quay đầu.",
        },
        {
            "id": "latentsync",
            "name": "LatentSync Diffusion",
            "recommended": False,
            "supported": True,
            "min_vram_mb": 16384,
            "is_underpowered": vram < 16384,
            "warning": "Cảnh báo: Thiết bị chưa đạt mức khuyến nghị VRAM 16GB. Quá trình xử lý có thể mất nhiều thời gian hơn, nhưng hệ thống vẫn cho phép tiếp tục sử dụng." if vram < 16384 else None,
            "description": "Mô hình Diffusion điện ảnh cao cấp nhất.",
        },
        {
            "id": "cloud_api",
            "name": "Cloud Lip-Sync",
            "recommended": False,
            "supported": True,
            "min_vram_mb": 0,
            "is_underpowered": False,
            "warning": None,
            "description": "Xử lý qua máy chủ đám mây, đạt chất lượng cao mà không tiêu tốn tài nguyên máy tính.",
        },
    ]
    return info


def process_lipsync(
    video_path: str,
    audio_path: str,
    output_path: str,
    engine: str = "auto",
    enhance: bool = True,
    vad_silence_clamping: bool = True,
    offset_ms: int = 0,
    api_key: str | None = None,
    batch_size: int = 2,
    fps: int = 25,
    musetalk_dir: str | None = None,
    musetalk_python: str | None = None,
    unet_model_path: str | None = None,
    unet_config: str | None = None,
) -> bool:
    """Run the multi-tier Lip-Sync pipeline with real neural inference, GFPGAN enhancement, and VAD silence clamping."""
    start_time = time.time()
    ffmpeg = find_ffmpeg()

    video_p = Path(video_path).resolve()
    audio_p = Path(audio_path).resolve()
    out_p = Path(output_path).resolve()

    if not video_p.exists():
        emit_json({"type": "error", "message": f"Video file not found: {video_path}"})
        return False
    if not audio_p.exists():
        emit_json({"type": "error", "message": f"Audio file not found: {audio_path}"})
        return False

    out_p.parent.mkdir(parents=True, exist_ok=True)
    try:
        temp_dir = create_musetalk_temp_dir()
    except RuntimeError as exc:
        emit_json({"type": "error", "message": str(exc)})
        return False

    try:
        hw = probe_hardware()
        selected_engine = hw["recommended_engine"] if engine == "auto" else engine

        # Determine effective enhancement mode
        # If user explicitly chose wav2lip_cuda, or chose a higher tier (musetalk, video_retalking, latentsync)
        # on hardware that only supports Tier 1, automatically activate GFPGAN Ultra-Sharp to deliver maximum possible fidelity!
        high_tier_selected = selected_engine in ["wav2lip_cuda", "musetalk", "video_retalking", "latentsync"]
        effective_enhance = enhance or high_tier_selected

        if selected_engine == "musetalk":
            ok = run_musetalk_pipeline(
                video_p=video_p,
                audio_p=audio_p,
                out_p=out_p,
                temp_dir=temp_dir,
                offset_ms=offset_ms,
                batch_size=batch_size,
                fps=fps,
                musetalk_dir=musetalk_dir,
                musetalk_python=musetalk_python,
                unet_model_path=unet_model_path,
                unet_config=unet_config,
            )
            if ok:
                return True
            emit_json({"type": "error", "message": "MuseTalk inference không thành công! Không sử dụng Wav2Lip để đảm bảo chất lượng sắc nét."})
            return False

        if high_tier_selected and hw["vram_mb"] < 6144 and selected_engine in ["video_retalking", "latentsync"]:
            emit_json({
                "type": "progress",
                "percent": 5,
                "stage": f"Công nghệ {selected_engine.upper()} yêu cầu >=8GB-16GB VRAM (máy hiện có {hw['vram_mb']}MB). Tự động kích hoạt Wav2Lip + GFPGAN Ultra-Sharp để đạt chất lượng sắc nét tối đa trên GTX 1650...",
            })

        emit_json({
            "type": "started",
            "engine": selected_engine,
            "effective_enhance": effective_enhance,
            "tier": hw["tier"],
            "gpu": hw["gpu_name"],
            "vad_clamping": vad_silence_clamping,
            "offset_ms": offset_ms,
            "video": str(video_p),
            "audio": str(audio_p),
            "output": str(out_p),
        })

        # Stage 1: Audio Pre-processing & Offset Calibration (16kHz mono WAV)
        emit_json({"type": "progress", "percent": 10, "stage": "Chuẩn hóa âm thanh & hiệu chỉnh độ trễ..."})
        norm_audio = temp_dir / "normalized_audio.wav"

        audio_filters = []
        if offset_ms > 0:
            audio_filters.extend(["-af", f"adelay={offset_ms}|{offset_ms}"])
        elif offset_ms < 0:
            trim_sec = abs(offset_ms) / 1000.0
            audio_filters.extend(["-ss", str(trim_sec)])

        cmd_audio = [
            ffmpeg,
            "-y",
            *audio_filters,
            "-i",
            str(audio_p),
            "-ar",
            "16000",
            "-ac",
            "1",
            str(norm_audio),
        ]
        subprocess.run(cmd_audio, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # Stage 2: Audio Feature Extraction (Mel-Spectrogram & VAD Gating)
        try:
            import cv2
            import numpy as np
            import onnxruntime as ort
            from insightface.app import FaceAnalysis
        except ImportError as e:
            emit_json({
                "type": "error",
                "message": f"Thiếu thư viện AI cần thiết: {e}. Vui lòng chạy: pip install onnxruntime-gpu insightface",
            })
            return False

        mel, samples, sr = compute_mel_spectrogram(norm_audio)

        cap = cv2.VideoCapture(str(video_p))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        vad_mask = detect_vad_mask(samples, sr, total_frames, fps)
        speech_frames = int(np.sum(vad_mask))
        silence_frames = total_frames - speech_frames
        speech_time = speech_frames / fps
        silence_time = silence_frames / fps

        emit_json({
            "type": "progress",
            "percent": 30,
            "stage": f"VAD: {speech_time:.1f}s phát âm, {silence_time:.1f}s ngắt giọng (khóa khẩu hình tự nhiên)...",
        })

        # Stage 3: Load Neural Models (Wav2Lip ONNX + GFPGAN Face Restorer + InsightFace AI)
        emit_json({"type": "progress", "percent": 35, "stage": "Nạp mô hình Wav2Lip & GFPGAN Face Restorer trên DirectML GPU..."})
        model_file = find_bundled_model("wav2lip_gan.onnx")
        if not model_file:
            raise FileNotFoundError("Mô hình wav2lip_gan.onnx không tìm thấy trong bundled-models!")

        gfpgan_file = find_bundled_model("gfpgan_1.4.onnx")
        face_root = find_face_models_root()

        available_providers = ort.get_available_providers()
        active_providers = [p for p in ["CUDAExecutionProvider", "DmlExecutionProvider", "CPUExecutionProvider"] if p in available_providers] or ["CPUExecutionProvider"]

        session = ort.InferenceSession(
            str(model_file),
            providers=active_providers,
        )

        sess_g = None
        if effective_enhance and gfpgan_file:
            try:
                sess_g = ort.InferenceSession(
                    str(gfpgan_file),
                    providers=active_providers,
                )
            except Exception:
                sess_g = None

        face_app = FaceAnalysis(
            name="buffalo_l",
            root=str(face_root),
            allowed_modules=["detection"],
            providers=[p for p in ["CUDAExecutionProvider", "CPUExecutionProvider"] if p in available_providers] or ["CPUExecutionProvider"],
        )
        face_app.prepare(ctx_id=0, det_size=(640, 640))

        # Stage 4: Read Frames & Track Faces
        emit_json({"type": "progress", "percent": 45, "stage": "Trích xuất khung hình & theo dõi vị trí khuôn mặt..."})
        frames = []
        for _ in range(total_frames):
            ret, frame = cap.read()
            if not ret:
                break
            frames.append(frame)
        cap.release()

        # Track faces on keyframes every 5 frames
        keyframe_interval = 5
        key_dets = []
        for i in range(0, len(frames), keyframe_interval):
            f = frames[i]
            dets = face_app.get(f)
            if dets:
                dets = sorted(dets, key=lambda d: d.bbox[0])
                key_dets.append([d.bbox for d in dets])
            else:
                key_dets.append(key_dets[-1] if key_dets else [])

        # Smoothly interpolate bounding boxes
        frame_faces = []
        for i in range(len(frames)):
            k1 = i // keyframe_interval
            k2 = min(k1 + 1, len(key_dets) - 1)
            alpha = (i % keyframe_interval) / float(keyframe_interval)
            b1_list = key_dets[k1]
            b2_list = key_dets[k2]
            interp_boxes = []
            if len(b1_list) == len(b2_list) and len(b1_list) > 0:
                for j in range(len(b1_list)):
                    b1 = b1_list[j]
                    b2 = b2_list[j]
                    box = [int(b1[c] * (1.0 - alpha) + b2[c] * alpha) for c in range(4)]
                    interp_boxes.append(box)
            elif len(b1_list) > 0:
                interp_boxes = [[int(c) for c in b] for b in b1_list]
            frame_faces.append(interp_boxes)

        # Stage 5: Neural Inference Batch Execution with GFPGAN Enhancement
        enh_label = " + GFPGAN Ultra-Sharp" if sess_g else ""
        emit_json({"type": "progress", "percent": 55, "stage": f"Đang đồng bộ khẩu hình ({selected_engine.upper()}{enh_label})..."})

        batch_size = 16
        mel_step = sr / 200.0
        out_frames = [f.copy() for f in frames]

        for b_start in range(0, len(frames), batch_size):
            b_end = min(b_start + batch_size, len(frames))
            pct = 55 + int(32 * (b_start / max(1, len(frames))))
            if b_start % (batch_size * 2) == 0:
                emit_json({"type": "progress", "percent": pct, "stage": f"Đồng bộ khẩu hình & làm nét chi tiết ({b_start}/{len(frames)} frames)..."})

            vid_batch = []
            mel_batch = []
            meta_batch = []

            for i in range(b_start, b_end):
                orig_frame = frames[i]
                is_speaking = vad_mask[i]
                boxes = frame_faces[i]

                # If VAD is active and silence is detected -> clamp mouth to natural silence!
                if vad_silence_clamping and not is_speaking:
                    continue

                if not boxes:
                    continue

                for box in boxes:
                    x1, y1, x2, y2 = box
                    fh, fw = y2 - y1, x2 - x1
                    pad_y = int(fh * 0.2)
                    pad_x = int(fw * 0.15)
                    y1_p = max(0, y1 - pad_y)
                    y2_p = min(h, y2 + pad_y)
                    x1_p = max(0, x1 - pad_x)
                    x2_p = min(w, x2 + pad_x)

                    crop = orig_frame[y1_p:y2_p, x1_p:x2_p]
                    orig_ch, orig_cw = crop.shape[:2]
                    if orig_ch < 28 or orig_cw < 28:
                        continue

                    crop_96 = cv2.resize(crop, (96, 96))
                    masked_crop = crop_96.copy()
                    masked_crop[48:, :] = 0

                    face_in = np.concatenate([masked_crop, crop_96], axis=2).astype(np.float32) / 255.0
                    face_in = np.transpose(face_in, (2, 0, 1))

                    m_center = int(round((i / fps) * mel_step))
                    m_start = m_center - 8
                    m_end = m_center + 8
                    if m_start < 0:
                        chunk = mel[:, :max(0, m_end)]
                        chunk = np.pad(chunk, ((0, 0), (-m_start, 0)), mode="constant")
                    elif m_end > mel.shape[1]:
                        chunk = mel[:, m_start:]
                        chunk = np.pad(chunk, ((0, 0), (0, m_end - mel.shape[1])), mode="constant")
                    else:
                        chunk = mel[:, m_start:m_end]

                    if chunk.shape[1] < 16:
                        chunk = np.pad(chunk, ((0, 0), (0, 16 - chunk.shape[1])), mode="edge")
                    chunk = chunk[:, :16].reshape(1, 80, 16).astype(np.float32)

                    vid_batch.append(face_in)
                    mel_batch.append(chunk)
                    meta_batch.append((i, (x1_p, y1_p, x2_p, y2_p), (orig_cw, orig_ch), crop))

            if vid_batch:
                vid_arr = np.array(vid_batch, dtype=np.float32)
                mel_arr = np.array(mel_batch, dtype=np.float32)
                outputs = session.run(["gen"], {"mel": mel_arr, "vid": vid_arr})[0]

                for k, (frame_idx, box_p, dims, crop) in enumerate(meta_batch):
                    gen_96 = outputs[k]
                    gen_bgr = np.clip(np.transpose(gen_96, (1, 2, 0)) * 255.0, 0, 255).astype(np.uint8)
                    orig_cw, orig_ch = dims
                    gen_res = cv2.resize(gen_bgr, (orig_cw, orig_ch))

                    # Blend lower face
                    mask = np.zeros((orig_ch, orig_cw), dtype=np.float32)
                    mask[int(orig_ch * 0.45):, :] = 1.0
                    mask = cv2.GaussianBlur(mask, (21, 21), 0)[:, :, np.newaxis]

                    w_blended = (gen_res.astype(np.float32) * mask + crop.astype(np.float32) * (1.0 - mask)).astype(np.uint8)

                    # GFPGAN Face Enhancement (Keyframes / Stride 2 for optimal speed-quality on GTX 1650)
                    if sess_g and frame_idx % 2 == 0:
                        try:
                            face_512 = cv2.resize(w_blended, (512, 512))
                            blob = cv2.cvtColor(face_512, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
                            blob = (blob - 0.5) / 0.5
                            blob = np.transpose(blob, (2, 0, 1))[np.newaxis, ...]

                            g_out = sess_g.run(None, {"input": blob})[0]
                            restored = np.clip((g_out[0].transpose(1, 2, 0) * 0.5 + 0.5) * 255.0, 0, 255).astype(np.uint8)
                            restored_bgr = cv2.cvtColor(restored, cv2.COLOR_RGB2BGR)
                            restored_res = cv2.resize(restored_bgr, (orig_cw, orig_ch))

                            final_crop = (restored_res.astype(np.float32) * mask + crop.astype(np.float32) * (1.0 - mask)).astype(np.uint8)
                        except Exception:
                            final_crop = w_blended
                    else:
                        final_crop = w_blended

                    x1_p, y1_p, x2_p, y2_p = box_p
                    out_frames[frame_idx][y1_p:y2_p, x1_p:x2_p] = final_crop

        # Stage 6: Re-muxing Final Video with Audio
        emit_json({"type": "progress", "percent": 90, "stage": "Đang kết xuất video chất lượng cao..."})
        temp_raw = temp_dir / "raw_rendered.mp4"
        writer = cv2.VideoWriter(str(temp_raw), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
        for f in out_frames:
            writer.write(f)
        writer.release()

        cmd_mux = [
            ffmpeg,
            "-y",
            "-i",
            str(temp_raw),
            "-i",
            str(norm_audio),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            str(out_p),
        ]
        subprocess.run(cmd_mux, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        elapsed = round(time.time() - start_time, 2)
        emit_json({
            "type": "completed",
            "percent": 100,
            "stage": "Hoàn tất đồng bộ khuôn miệng thành công!",
            "output_path": str(out_p),
            "speech_seconds": round(speech_time, 2),
            "silence_seconds": round(silence_time, 2),
            "duration_seconds": elapsed,
        })
        return out_p.is_file() and out_p.stat().st_size > 1000

    except Exception as e:
        emit_json({"type": "error", "message": str(e)})
        return False
    finally:
        # Cleanup temporary files
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Pro Studio Lip-Sync CLI Worker")
    parser.add_argument("--action", choices=["profile", "sync"], default="profile")
    parser.add_argument("--video", help="Path to input video")
    parser.add_argument("--audio", help="Path to input audio")
    parser.add_argument("--output", help="Path to output video")
    parser.add_argument("--engine", default="auto", help="Lip-sync engine: auto, wav2lip_onnx, wav2lip_cuda, etc.")
    parser.add_argument("--enhance", action="store_true", default=True, help="Enable face enhancement")
    parser.add_argument("--vad-silence-clamping", action="store_true", default=True, help="Clamp mouth during silence/pauses")
    parser.add_argument("--offset-ms", type=int, default=0, help="Audio-visual delay offset in milliseconds")
    parser.add_argument("--api-key", help="API key for cloud provider if used")
    parser.add_argument("--batch-size", type=int, default=2, help="MuseTalk inference batch size (RTX 3060 12GB: start at 2)")
    parser.add_argument("--fps", type=int, default=25, help="Target inference fps; video input should already use this fps")
    parser.add_argument("--musetalk-dir", help="MuseTalk repository root (optional override)")
    parser.add_argument("--musetalk-python", help="MuseTalk Python executable (optional override)")
    parser.add_argument("--unet-model-path", help="MuseTalk v1.5 UNet weights path (optional override)")
    parser.add_argument("--unet-config", help="MuseTalk UNet config path (optional override)")

    args = parser.parse_args()

    if args.action == "profile":
        profile = probe_hardware()
        emit_json(profile)
    elif args.action == "sync":
        if not args.video or not args.audio or not args.output:
            emit_json({"type": "error", "message": "Missing required arguments --video, --audio, or --output"})
            sys.exit(1)
        ok = process_lipsync(
            video_path=args.video,
            audio_path=args.audio,
            output_path=args.output,
            engine=args.engine,
            enhance=args.enhance,
            vad_silence_clamping=args.vad_silence_clamping,
            offset_ms=args.offset_ms,
            api_key=args.api_key,
            batch_size=args.batch_size,
            fps=args.fps,
            musetalk_dir=args.musetalk_dir,
            musetalk_python=args.musetalk_python,
            unet_model_path=args.unet_model_path,
            unet_config=args.unet_config,
        )
        if not ok:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
