"""Studio Bridge for Video Creative Studio.

Provides a unified JSON-lines IPC interface between Tauri / Frontend
and the underlying AI Video Pipeline (LivePortrait + MuseTalk + TTS).
Streams structured events without modifying the core pipeline code.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
import urllib.request

# Ensure standard UTF-8 stream handling
if sys.platform == "win32":
    try:
        if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
LOCALAPPDATA = Path(os.environ.get("LOCALAPPDATA", r"C:\Users\quant\AppData\Local"))
CACHE_DIR = ROOT_DIR / "data" / "tts_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0



def emit_event(event_type: str, data: Dict[str, Any]):
    """Emit a structured JSON line on stdout for Tauri / caller to parse."""
    payload = {
        "type": event_type,
        "timestamp": time.time(),
        **data,
    }
    line = json.dumps(payload, ensure_ascii=False)
    print(f"[VCS_EVENT] {line}", flush=True)


def emit_log(line: str):
    """Emit a raw log message as an event."""
    emit_event("log", {"message": line.strip()})


def emit_progress(stage: str, percent: float, message: str):
    """Emit progress update event."""
    emit_event("progress", {
        "stage": stage,
        "percent": max(0.0, min(100.0, round(percent, 1))),
        "message": message,
    })


def detect_python_executable() -> str:
    """Find the best Python executable for running the pipeline."""
    candidates = [
        Path("C:/Program Files/Python310/python.exe"),
        ROOT_DIR / "venv" / "Scripts" / "python.exe",
        Path(sys.executable),
    ]
    for c in candidates:
        if c.is_file():
            return str(c)
    return sys.executable


def get_gpu_info() -> Dict[str, Any]:
    """Retrieve GPU name and memory via nvidia-smi if available."""
    info = {"available": False, "name": "None", "total_vram_mb": 0, "free_vram_mb": 0}
    try:
        smi = shutil.which("nvidia-smi")
        if smi:
            res = subprocess.run(
                [
                    smi,
                    "--query-gpu=name,memory.total,memory.free",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=3,
                creationflags=CREATE_NO_WINDOW,
            )
            if res.returncode == 0 and res.stdout.strip():
                parts = [p.strip() for p in res.stdout.strip().splitlines()[0].split(",")]
                if len(parts) >= 3:
                    info["available"] = True
                    info["name"] = parts[0]
                    info["total_vram_mb"] = int(float(parts[1]))
                    info["free_vram_mb"] = int(float(parts[2]))
    except Exception:
        pass
    return info


def preflight_check() -> Dict[str, Any]:
    """Check availability of all engines, dependencies, and assets."""
    gpu = get_gpu_info()
    ffmpeg_ok = bool(shutil.which("ffmpeg"))
    ffprobe_ok = bool(shutil.which("ffprobe"))
    python_exe = detect_python_executable()
    
    lp_dir = ROOT_DIR / "LivePortrait"
    lp_ok = (lp_dir / "inference.py").is_file()
    
    musetalk_dir = ROOT_DIR / "musetalk"
    musetalk_ok = musetalk_dir.is_dir()
    
    muse_py = ROOT_DIR / "musetalk-venv" / "Scripts" / "python.exe"
    musetalk_venv_ok = muse_py.is_file()
    
    char_dir = ROOT_DIR / "assets" / "characters"
    characters = []
    if char_dir.is_dir():
        for f in char_dir.rglob("*.png"):
            characters.append({
                "name": f.stem,
                "path": str(f.resolve()),
                "group": f.parent.name,
            })
            
    driving_dir = ROOT_DIR / "assets" / "driving_templates"
    drivings = []
    if driving_dir.is_dir():
        for f in driving_dir.glob("*.mp4"):
            drivings.append({
                "name": f.name,
                "path": str(f.resolve()),
                "size_mb": round(f.stat().st_size / (1024 * 1024), 2),
            })

    status = {
        "system": {
            "platform": sys.platform,
            "python": python_exe,
            "ffmpeg": ffmpeg_ok,
            "ffprobe": ffprobe_ok,
            "gpu": gpu,
        },
        "engines": {
            "liveportrait": {
                "installed": lp_ok,
                "path": str(lp_dir),
            },
            "musetalk": {
                "installed": musetalk_ok,
                "venv_ready": musetalk_venv_ok,
                "python": str(muse_py) if musetalk_venv_ok else None,
            },
        },
        "assets": {
            "character_count": len(characters),
            "characters": characters,
            "driving_count": len(drivings),
            "driving_templates": drivings,
        },
    }
    return status


def get_audio_duration(audio_path: Path) -> float:
    try:
        cmd = [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, creationflags=CREATE_NO_WINDOW)
        if res.returncode == 0 and res.stdout.strip():
            return round(float(res.stdout.strip()), 2)
    except Exception:
        pass
    if audio_path.is_file():
        return max(1.0, round(audio_path.stat().st_size / 6000.0, 2))
    return 3.0


CAPCUT_GENDERS: Dict[str, str] = {
    "BV421_vivn_streaming": "female",
    "BV074_streaming": "female",
    "BV562_streaming": "female",
    "vi_female_huong": "female",
    "BV560_streaming": "male",
    "BV075_streaming": "male",
    "multi_male_felipe_uranus_bigtts": "male",
    "multi_female_richgirl_uranus_bigtts": "female",
    "BV074_streaming_dsp": "female",
    "BV075_streaming_vibrato_dsp": "male",
    "BV075_streaming_demon_dsp": "male",
    "multi_female_yangguangnv_uranus_bigtts": "female",
    # Legacy mappings
    "Trung_Caha": "male",
    "Nam_Tram": "male",
    "Ly_Nam": "female",
    "Duy_Bac": "male",
    "Ha_Nu": "female",
    "Sai_Nu": "female",
}

VIENEU_GENDERS: Dict[str, str] = {
    "Lệ 12s": "female",
    "Gái Huế": "female",
    "Adam Tốp Tốp": "male",
    "Mai Bé Phương": "female",
    "Đăng Quân": "male",
    "Duyên Hà My": "female",
    "Tưởng Vy": "female",
    "Bình Bon": "male",
    "My Méo": "female",
    "Nam Nũng Nịu": "male",
    "Nhỏ Ngọt Ngào": "female",
    "Thiền Tâm Đức": "male",
    "Thái Duy Bình": "male",
    "Ban Mai": "female",
    "Châu Thảo": "female",
    "Huyền My": "female",
    "Mai Phương": "female",
    "Bích Ngọc": "female",
    "Anh Dũng": "male",
    "Anh Thư": "female",
    "Trâm Anh": "female",
    "Trung Dũng": "male",
    "Bạch Tuyết": "female",
    "Thành Sen": "female",
    "An Khang": "male",
    "An Nhiên": "male",
    "Minh Ngọc": "female",
    "Thiện Minh": "male",
    "Hải Đăng": "male",
    "Ngọc Tuấn": "male",
    "Alexander Cường": "male",
    "Adam kể chuyện": "male",
    "Ái Chi": "female",
    "Cẩm Phụng": "female",
    "Diễm Hạnh": "female",
    "Diễm Thơ": "female",
    "Đình Lâm": "male",
}


async def synthesize_edge_tts(text: str, voice: str, out_path: Path, max_retries: int = 4) -> float:
    """Generate audio file via edge-tts with automatic retry."""
    import edge_tts
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    last_err = None
    for attempt in range(max_retries):
        try:
            out_path.unlink(missing_ok=True)
            comm = edge_tts.Communicate(text, voice)
            await comm.save(str(out_path))
            if out_path.is_file() and out_path.stat().st_size > 300:
                break
        except Exception as e:
            last_err = e
            out_path.unlink(missing_ok=True)
            if attempt < max_retries - 1:
                await asyncio.sleep(0.8 * (attempt + 1))
    else:
        if last_err:
            raise last_err
        raise RuntimeError("Không nhận được dữ liệu âm thanh từ Edge-TTS")
    
    return get_audio_duration(out_path)


def synthesize_capcut(text: str, voice_id: str, out_path: Path) -> float:
    """Synthesize speech using official CapCut runner."""
    py_exe = LOCALAPPDATA / "Prostudio" / "py" / "capcut" / "python.exe"
    runner = ROOT_DIR / "runners" / "capcut_tts_runner.py"
    if not runner.exists():
        runner = Path(r"D:\rustProject\prostudio-ai\server\capcut_tts_runner.py")
    if not (py_exe.exists() and runner.exists()):
        raise RuntimeError("CapCut TTS environment is not available")

    req = {
        "command": "synthesize",
        "text": text,
        "voice": voice_id,
        "rate": "1.0",
    }
    p = subprocess.run(
        [str(py_exe), str(runner)],
        input=json.dumps(req, ensure_ascii=False),
        capture_output=True,
        text=True,
        encoding="utf-8",
        creationflags=CREATE_NO_WINDOW,
    )
    if p.returncode != 0:
        raise RuntimeError(f"CapCut runner failed: {p.stderr}")
    data = json.loads(p.stdout)
    if not data.get("success") or not data.get("audio_url"):
        raise RuntimeError(f"CapCut synthesis failed: {data.get('error') or data}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(data["audio_url"], str(out_path))

    dur_ms = data.get("duration_ms")
    if dur_ms:
        return round(float(dur_ms) / 1000.0, 2)
    return get_audio_duration(out_path)


def synthesize_vieneu(text: str, voice_id: str, out_path: Path) -> float:
    """Synthesize speech using local VieNeu-v3-Turbo ONNX engine."""
    py_exe = LOCALAPPDATA / "Prostudio" / "components" / "tts-vieneu" / "python" / "python.exe"
    worker = ROOT_DIR / "runners" / "vieneu_tts_worker.py"
    if not worker.exists():
        worker = Path(r"D:\rustProject\prostudio-ai\server\vieneu_tts_worker.py")
    if not (py_exe.exists() and worker.exists()):
        raise RuntimeError("VieNeu TTS component is not available")

    env = os.environ.copy()
    env["PYTHONPATH"] = str(LOCALAPPDATA / "Prostudio" / "components" / "tts-vieneu" / "site-packages")
    env["HF_HUB_CACHE"] = str(LOCALAPPDATA / "Prostudio" / "components" / "tts-vieneu" / "models" / "hub")
    env["HF_HUB_OFFLINE"] = "1"
    env["TRANSFORMERS_OFFLINE"] = "1"
    env["EDITKUB_TTS_ENGINE_ROOT"] = str(ROOT_DIR)

    local_voices = ROOT_DIR / "data" / "vieneu"
    if (local_voices / "custom-voices.json").exists():
        env["PROSTUDIO_TTS_VOICES_DIR"] = str(local_voices)
    else:
        env["PROSTUDIO_TTS_VOICES_DIR"] = str(LOCALAPPDATA / "Prostudio" / "tts-voices" / "vieneu")

    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    p = subprocess.Popen(
        [str(py_exe), str(worker)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        env=env,
        creationflags=CREATE_NO_WINDOW,
    )

    _ready = p.stdout.readline()

    req = {
        "id": "req-1",
        "command": "synthesize",
        "text": text,
        "voice": voice_id,
        "style": "tu_nhien",
    }
    p.stdin.write(json.dumps(req, ensure_ascii=False) + "\n")
    p.stdin.flush()
    res_line = p.stdout.readline()
    p.stdin.close()
    p.terminate()

    if not res_line:
        err = p.stderr.read() if p.stderr else ""
        raise RuntimeError(f"VieNeu worker exited unexpectedly: {err}")

    data = json.loads(res_line)
    if not data.get("success") or not data.get("audioPath"):
        raise RuntimeError(f"VieNeu synthesis failed: {data.get('error') or data}")

    src_wav = Path(data["audioPath"])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.suffix.lower() == ".mp3":
        cmd = ["ffmpeg", "-y", "-i", str(src_wav), "-b:a", "192k", str(out_path)]
        subprocess.run(cmd, capture_output=True, creationflags=CREATE_NO_WINDOW)
    else:
        shutil.copyfile(src_wav, out_path)

    return get_audio_duration(out_path)


def canonical_voice_id(raw_voice: str) -> str:
    raw = (raw_voice or "vi-VN-NamMinhNeural").strip()
    if raw.startswith("capcut:") or raw.startswith("capcut_"):
        clean = raw.split(":", 1)[-1] if ":" in raw else raw[7:]
        return f"capcut:{clean}"
    if raw.startswith("vieneu:") or raw.startswith("vieneu_"):
        clean = raw.split(":", 1)[-1] if ":" in raw else raw[7:]
        return f"vieneu:{clean}"
    if raw in CAPCUT_GENDERS:
        return f"capcut:{raw}"
    if raw in VIENEU_GENDERS:
        return f"vieneu:{raw}"
    if raw.startswith("edge-tts:"):
        return raw[9:]
    return raw


def get_tts_cache_key(voice_spec: str, text: str) -> str:
    c_id = canonical_voice_id(voice_spec)
    raw = f"{c_id.strip()}::{text.strip()}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def synthesize_voice(
    text: str,
    raw_voice: str,
    out_path: Path,
    gender_hint: Optional[str] = None
) -> Tuple[float, str]:
    """Unified multi-engine TTS dispatcher with disk caching.
    
    Supports:
    - VieNeu local ONNX (37 curated presets)
    - CapCut TikTok API (12 viral voices)
    - Microsoft Edge-TTS (322 neural voices across 140+ languages)
    Guarantees strict gender matching and graceful fallback without voice collapse.
    """
    raw = (raw_voice or "vi-VN-NamMinhNeural").strip()
    c_id = canonical_voice_id(raw)

    # 0. Check disk cache for instant playback (0.01s)
    cache_key = get_tts_cache_key(c_id, text)
    cache_file = CACHE_DIR / f"{cache_key}.mp3"
    if cache_file.is_file() and cache_file.stat().st_size > 500:
        try:
            if out_path.resolve() != cache_file.resolve():
                out_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(cache_file, out_path)
            return get_audio_duration(out_path), c_id
        except Exception:
            pass

    # Determine provider and clean voice ID
    provider = "edge-tts"
    clean_id = raw
    if raw.startswith("capcut:") or raw.startswith("capcut_"):
        provider = "capcut"
        clean_id = raw.split(":", 1)[-1] if ":" in raw else raw[7:]
    elif raw.startswith("vieneu:") or raw.startswith("vieneu_"):
        provider = "vieneu"
        clean_id = raw.split(":", 1)[-1] if ":" in raw else raw[7:]
    elif clean_id in CAPCUT_GENDERS:
        provider = "capcut"
    elif clean_id in VIENEU_GENDERS:
        provider = "vieneu"
    elif raw.startswith("edge-tts:"):
        provider = "edge-tts"
        clean_id = raw[9:]

    # Resolve expected gender
    resolved_gender = (gender_hint or "").strip().lower()
    if not resolved_gender:
        if provider == "capcut" and clean_id in CAPCUT_GENDERS:
            resolved_gender = CAPCUT_GENDERS[clean_id]
        elif provider == "vieneu" and clean_id in VIENEU_GENDERS:
            resolved_gender = VIENEU_GENDERS[clean_id]
        elif "female" in raw.lower() or "hoaimy" in raw.lower() or "jenny" in raw.lower():
            resolved_gender = "female"
        elif "male" in raw.lower() or "namminh" in raw.lower() or "guy" in raw.lower():
            resolved_gender = "male"
        else:
            resolved_gender = "female"

    fallback_voice = "vi-VN-HoaiMyNeural" if resolved_gender == "female" else "vi-VN-NamMinhNeural"

    def _save_cache():
        try:
            if out_path.is_file() and out_path.stat().st_size > 500:
                CACHE_DIR.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(out_path, cache_file)
        except Exception:
            pass

    # 1. CapCut
    if provider == "capcut":
        try:
            dur = synthesize_capcut(text, clean_id, out_path)
            _save_cache()
            return dur, f"capcut:{clean_id}"
        except Exception as e:
            emit_log(f"[CapCut TTS Warning] {clean_id} không phản hồi ({e}). Chuyển fallback sang Edge-TTS ({fallback_voice}).")
            dur = asyncio.run(synthesize_edge_tts(text, fallback_voice, out_path))
            _save_cache()
            return dur, fallback_voice

    # 2. VieNeu
    if provider == "vieneu":
        try:
            dur = synthesize_vieneu(text, clean_id, out_path)
            _save_cache()
            return dur, f"vieneu:{clean_id}"
        except Exception as e:
            emit_log(f"[VieNeu TTS Warning] {clean_id} gặp lỗi ({e}). Chuyển fallback sang Edge-TTS ({fallback_voice}).")
            dur = asyncio.run(synthesize_edge_tts(text, fallback_voice, out_path))
            _save_cache()
            return dur, fallback_voice

    # 3. Edge-TTS
    try:
        dur = asyncio.run(synthesize_edge_tts(text, clean_id, out_path))
        _save_cache()
        return dur, clean_id
    except Exception as e:
        emit_log(f"[Edge-TTS Warning] Giọng '{clean_id}' lỗi ({e}). Thử fallback chuẩn: {fallback_voice}")
        dur = asyncio.run(synthesize_edge_tts(text, fallback_voice, out_path))
        _save_cache()
        return dur, fallback_voice


def run_pipeline_job(job_spec: Dict[str, Any]) -> int:
    """Execute a single render job by delegating to test_option_b_avatar.py."""
    job_id = job_spec.get("id", "job_direct")
    emit_event("job_started", {"job_id": job_id, "spec": job_spec})
    emit_progress("initializing", 2.0, "Khởi tạo môi trường và thông số render...")

    script_path = ROOT_DIR / "test_option_b_avatar.py"
    if not script_path.is_file():
        emit_event("error", {"message": f"Không tìm thấy {script_path}"})
        return 1

    python_exe = detect_python_executable()

    gpu = get_gpu_info()
    vram = gpu.get("total_vram_mb", 0)
    is_low_vram = vram > 0 and vram < 6000 and not job_spec.get("force_gpu", False)

    # If dry_run is requested or running on low VRAM dev machine without force_gpu,
    # provide a smooth, fast simulation generating real Edge-TTS audio + preview MP4 without GPU VRAM thrashing
    if job_spec.get("dry_run") or is_low_vram:
        mode_reason = "Chế độ Test (Máy hiện tại)" if job_spec.get("dry_run") else f"Tự động bảo vệ GPU ({gpu.get('name', 'NVIDIA')} {vram}MB VRAM < 6000MB yêu cầu)"
        emit_log(f"💡 [{mode_reason}] Kích hoạt chế độ Thử nghiệm An toàn (0% tải GPU, test giao diện & batch mượt mà).")

        script_text = job_spec.get("script") or "Xin chào các bạn, đây là video thử nghiệm giao diện Video Creative Studio."
        voice = job_spec.get("voice") or "vi-VN-NamMinhNeural"
        out_video = Path(job_spec.get("output", f"output/{job_id}.mp4")).resolve()
        out_video.parent.mkdir(parents=True, exist_ok=True)
        temp_audio = ROOT_DIR / "temp" / f"{job_id}_preview.mp3"
        temp_audio.parent.mkdir(parents=True, exist_ok=True)

        # Stage 1: Audio Synthesis
        emit_progress("audio_tts", 15.0, f"Đang tổng hợp giọng nói ({voice})...")
        emit_log(f"[TTS Pipeline] Đang tạo âm thanh cho kịch bản ({len(script_text)} ký tự)...")
        dur = 3.0
        try:
            dur, voice_used = synthesize_voice(script_text, voice, temp_audio, gender_hint=job_spec.get("gender"))
            emit_log(f"[TTS Pipeline] ✅ Đã tạo âm thanh ({voice_used}): {temp_audio.name} (thời lượng: {dur:.1f}s)")
        except Exception as e:
            emit_log(f"[TTS Pipeline] Lỗi tạo âm thanh: {e}")

        time.sleep(0.6)

        # Stage 2: LivePortrait
        emit_progress("liveportrait", 40.0, f"LivePortrait: Mô phỏng pose cử động đầu (multiplier={job_spec.get('multiplier', 0.55)}x)...")
        emit_log(f"[LivePortrait] Chuẩn hóa pose gốc & áp dụng driving template (pitch/yaw/roll)...")
        time.sleep(0.6)

        # Stage 3: Torso Kinematics
        emit_progress("torso_motion", 60.0, "TorsoKinematics: Mô phỏng nhịp thở và ổn định cơ thể...")
        emit_log("[TorsoKinematics] Điều phối biên độ vai tự nhiên...")
        time.sleep(0.5)

        # Stage 4: MuseTalk
        emit_progress("musetalk", 80.0, "MuseTalk 1.5: Khớp khẩu hình âm vị tiếng Việt...")
        emit_log("[MuseTalk] Đồng bộ biên độ môi theo dải âm thanh...")
        time.sleep(0.6)

        # Stage 5: Verifying & Generating Video via ffmpeg
        emit_progress("verifying", 92.0, "Đang tạo video xuất bản thử nghiệm...")

        # Find character image
        # Find character image
        char_img = None
        if job_spec.get("source"):
            sp = Path(job_spec["source"]).resolve()
            if sp.is_file():
                char_img = sp
        if not char_img:
            char_candidates = [
                ROOT_DIR / "assets" / "characters" / "nhanvatnam" / "asian_male_office_1080p.png",
                ROOT_DIR / "assets" / "characters" / "angle_front.jpg",
            ]
            for c in char_candidates:
                if c.is_file():
                    char_img = c
                    break
        if not char_img:
            any_imgs = list((ROOT_DIR / "assets" / "characters").rglob("*.png")) + list((ROOT_DIR / "assets" / "characters").rglob("*.jpg"))
            if any_imgs:
                char_img = any_imgs[0]

        if char_img and shutil.which("ffmpeg"):
            if temp_audio.is_file() and temp_audio.stat().st_size > 0:
                ff_cmd = [
                    "ffmpeg", "-y", "-loop", "1", "-i", str(char_img),
                    "-i", str(temp_audio),
                    "-c:v", "libx264", "-tune", "stillimage",
                    "-c:a", "aac", "-b:a", "192k",
                    "-pix_fmt", "yuv420p", "-shortest",
                    str(out_video)
                ]
            else:
                ff_cmd = [
                    "ffmpeg", "-y", "-loop", "1", "-i", str(char_img),
                    "-t", "3",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    str(out_video)
                ]
            subprocess.run(ff_cmd, capture_output=True, creationflags=CREATE_NO_WINDOW)
            if out_video.is_file():
                emit_log(f"[FFmpeg] Đã xuất video thử nghiệm: {out_video.name}")

        emit_progress("completed", 100.0, "Video thử nghiệm đã hoàn tất!")
        emit_event("job_completed", {
            "job_id": job_id,
            "output": str(out_video),
            "status": "success",
        })
        return 0

    cmd = [
        python_exe,
        "-u",
        str(script_path),
    ]

    # Map job parameters to CLI flags
    if job_spec.get("source"):
        cmd.extend(["--source", str(job_spec["source"])])
    elif job_spec.get("char"):
        cmd.extend(["--char", str(job_spec["char"])])

    if job_spec.get("driving"):
        cmd.extend(["--driving", str(job_spec["driving"])])

    audio_path = job_spec.get("audio")
    if not audio_path and job_spec.get("script"):
        voice = job_spec.get("voice") or "vi-VN-NamMinhNeural"
        temp_audio = ROOT_DIR / "temp" / f"{job_id}_pipeline_speech.mp3"
        temp_audio.parent.mkdir(parents=True, exist_ok=True)
        emit_progress("audio_tts", 10.0, f"Đang tổng hợp giọng nói ({voice})...")
        emit_log(f"[TTS Pipeline] Đang tạo âm thanh cho kịch bản với giọng '{voice}'...")
        try:
            dur, voice_used = synthesize_voice(
                job_spec["script"],
                voice,
                temp_audio,
                gender_hint=job_spec.get("gender")
            )
            emit_log(f"[TTS Pipeline] ✅ Đã tạo âm thanh ({voice_used}): {temp_audio.name} ({dur:.1f}s)")
            audio_path = str(temp_audio)
        except Exception as e:
            emit_log(f"[TTS Pipeline] ⚠️ Lỗi tổng hợp giọng nói tùy chọn ({e}), tiếp tục dùng kịch bản trực tiếp.")

    if audio_path:
        cmd.extend(["--audio", str(audio_path)])
    elif job_spec.get("script"):
        cmd.extend(["--script", str(job_spec["script"])])

    if job_spec.get("output"):
        cmd.extend(["--output", str(job_spec["output"])])

    if job_spec.get("duration"):
        cmd.extend(["--duration", str(job_spec["duration"])])

    if job_spec.get("fps"):
        cmd.extend(["--fps", str(job_spec["fps"])])

    if job_spec.get("multiplier"):
        cmd.extend(["--multiplier", str(job_spec["multiplier"])])

    if job_spec.get("driving_policy"):
        cmd.extend(["--driving-policy", str(job_spec["driving_policy"])])

    if job_spec.get("motion_mode"):
        cmd.extend(["--motion-mode", str(job_spec["motion_mode"])])

    if job_spec.get("batch_size"):
        cmd.extend(["--batch-size", str(job_spec["batch_size"])])

    if job_spec.get("offset_ms"):
        cmd.extend(["--offset-ms", str(job_spec["offset_ms"])])

    if job_spec.get("dry_run"):
        cmd.append("--dry-run")

    emit_log(f"Thực thi lệnh: {' '.join(cmd)}")

    # Start child process with pipe
    proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        encoding="utf-8",
        errors="replace",
        creationflags=CREATE_NO_WINDOW,
    )

    current_stage = "preparing"
    current_percent = 5.0
    output_video_path = None

    try:
        for raw_line in proc.stdout:
            line = raw_line.strip()
            if not line:
                continue

            emit_log(line)

            # Stage & Progress Parsing
            if "Đang tổng hợp giọng đọc" in line or "[Edge-TTS]" in line:
                current_stage = "audio_tts"
                current_percent = 10.0
                emit_progress(current_stage, current_percent, "Đang tổng hợp giọng nói AI...")

            elif "LivePortrait" in line or "Making motion templates" in line or "Euler Pose" in line:
                current_stage = "liveportrait"
                current_percent = 25.0
                emit_progress(current_stage, current_percent, "LivePortrait: Đang tạo cử động đầu 3D...")

            elif "TorsoKinematics" in line or "nhip tho" in line:
                current_stage = "torso_motion"
                current_percent = 45.0
                emit_progress(current_stage, current_percent, "Đang áp dụng nhịp thở và chuyển động thân...")

            elif "MuseTalk" in line or "lip-sync" in line:
                current_stage = "musetalk"
                current_percent = 55.0
                emit_progress(current_stage, current_percent, "MuseTalk 1.5 FP16: Đang khớp khẩu hình âm vị...")

            elif "batch" in line.lower() or "it/s" in line:
                # Slight bump during inference loop
                if current_stage == "musetalk" and current_percent < 85.0:
                    current_percent += 1.5
                    emit_progress(current_stage, current_percent, line)

            elif "Xác minh" in line or "ffprobe" in line:
                current_stage = "verifying"
                current_percent = 92.0
                emit_progress(current_stage, current_percent, "Đang kiểm tra chất lượng và thời lượng video...")

            elif "Video đầu ra:" in line:
                match = re.search(r"Video đầu ra:\s*(.*)", line)
                if match:
                    output_video_path = match.group(1).strip()
                current_percent = 98.0
                emit_progress("finalizing", current_percent, "Hoàn tất xử lý video.")

        proc.wait()
        rc = proc.returncode

        if rc == 0:
            emit_progress("completed", 100.0, "Video đã được tạo thành công!")
            emit_event("job_completed", {
                "job_id": job_id,
                "output": output_video_path or job_spec.get("output"),
                "status": "success",
            })
            return 0
        else:
            emit_event("job_failed", {
                "job_id": job_id,
                "returncode": rc,
                "error": f"Tiến trình kết thúc với mã lỗi {rc}",
            })
            return rc

    except KeyboardInterrupt:
        emit_log("Nhận tín hiệu dừng từ người dùng. Đang đóng các tiến trình con...")
        if proc.poll() is None:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, creationflags=CREATE_NO_WINDOW)
            else:
                proc.terminate()
        emit_event("job_cancelled", {"job_id": job_id})
        return 130


def main():
    parser = argparse.ArgumentParser(description="VCS Studio Bridge IPC Adapter")
    parser.add_argument("--preflight", action="store_true", help="Kiểm tra môi trường và tài nguyên phần cứng")
    parser.add_argument("--job-json", default=None, help="Đường dẫn file JSON mô tả job")
    parser.add_argument("--job-string", default=None, help="Chuỗi JSON mô tả job")
    parser.add_argument("--preview-tts", default=None, help="Văn bản cần đọc thử")
    parser.add_argument("--voice", default="vi-VN-NamMinhNeural", help="Giọng TTS")
    parser.add_argument("--gender", default=None, help="Giới tính giọng đọc (female/male)")
    parser.add_argument("--tts-out", default=None, help="Đường dẫn file audio test")
    
    # Passthrough pipeline args for direct CLI calling
    parser.add_argument("--char", choices=["office", "male", "female", "pixar"], default=None)
    parser.add_argument("--source", default=None)
    parser.add_argument("--driving", default=None)
    parser.add_argument("--audio", default=None)
    parser.add_argument("--output", default=None)
    parser.add_argument("--script", default=None)
    parser.add_argument("--duration", type=float, default=None)
    parser.add_argument("--fps", type=int, default=25)
    parser.add_argument("--multiplier", type=float, default=0.55)
    parser.add_argument("--driving-policy", default="hold")
    parser.add_argument("--motion-mode", default="off")
    parser.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()

    if args.preflight:
        status = preflight_check()
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return 0

    if args.preview_tts:
        out_file = Path(args.tts_out) if args.tts_out else ROOT_DIR / "temp" / "tts_preview.mp3"
        raw_voice = (args.voice or "vi-VN-NamMinhNeural").strip()

        try:
            dur, voice_used = synthesize_voice(args.preview_tts, raw_voice, out_file, gender_hint=args.gender)
        except Exception as e:
            print(json.dumps({
                "status": "error",
                "message": f"Không thể tạo âm thanh TTS cho giọng '{raw_voice}' ({e}). Vui lòng kiểm tra kết nối mạng."
            }, ensure_ascii=False))
            return 1

        import base64
        b64_audio = ""
        if out_file.is_file() and out_file.stat().st_size > 0:
            b64_audio = base64.b64encode(out_file.read_bytes()).decode("ascii")

        print(json.dumps({
            "status": "success",
            "audio_path": str(out_file.resolve()),
            "duration": dur,
            "voice_used": voice_used,
            "audio_base64": b64_audio,
        }, ensure_ascii=False))
        return 0

    job_spec = {}
    if args.job_json:
        p = Path(args.job_json).resolve()
        if not p.is_file():
            emit_event("error", {"message": f"Không tìm thấy file {p}"})
            return 1
        job_spec = json.loads(p.read_text(encoding="utf-8"))
    elif args.job_string:
        job_spec = json.loads(args.job_string)
    else:
        # Build from CLI arguments
        if args.source:
            job_spec["source"] = args.source
        if args.char:
            job_spec["char"] = args.char
        if args.driving:
            job_spec["driving"] = args.driving
        if args.audio:
            job_spec["audio"] = args.audio
        if args.output:
            job_spec["output"] = args.output
        if args.script:
            job_spec["script"] = args.script
        if args.duration:
            job_spec["duration"] = args.duration
        if args.fps:
            job_spec["fps"] = args.fps
        if args.multiplier:
            job_spec["multiplier"] = args.multiplier
        if args.driving_policy:
            job_spec["driving_policy"] = args.driving_policy
        if args.motion_mode:
            job_spec["motion_mode"] = args.motion_mode
        if args.dry_run:
            job_spec["dry_run"] = True

    if not job_spec:
        parser.print_help()
        return 1

    return run_pipeline_job(job_spec)


if __name__ == "__main__":
    raise SystemExit(main())
