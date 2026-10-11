"""Studio Bridge for Video Creative Studio.

Provides a JSON-lines IPC interface between Tauri / Frontend and the
Echo Flash + MuseTalk production pipeline, plus the existing TTS providers.
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
import wave
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
    """Report detected host tools and managed model assets without assumptions."""
    gpu = get_gpu_info()
    ffmpeg_ok = bool(shutil.which("ffmpeg"))
    ffprobe_ok = bool(shutil.which("ffprobe"))
    python_exe = detect_python_executable()
    char_dir = ROOT_DIR / "assets" / "characters"
    try:
        from scripts.pipeline_model_manager import build_status

        model_status = build_status()
        model_components = model_status.get("components", {})
    except Exception:
        model_components = {}

    characters = []
    for name, relative_path, group in (
        ("MC Nam", "nhanvatnam/ChatGPT Image Sep 8, 2026, 08_46_26 AM (1).png", "nam"),
        ("MC Nữ", "nhanvatnu/ChatGPT Image Sep 14, 2026, 11_35_53 AM (1).png", "nữ"),
    ):
        path = char_dir / relative_path
        if path.is_file():
            characters.append({"name": name, "path": str(path.resolve()), "group": group})

    status = {
        "available": True,
        "system": {
            "platform": sys.platform,
            "python": python_exe,
            "ffmpeg": ffmpeg_ok,
            "ffprobe": ffprobe_ok,
            "gpu": gpu,
        },
        "engines": {
            "echo": model_components.get("echo", {"source": {"status": "unknown"}, "assets_ready": 0, "assets_total": 0}),
            "musetalk": {
                **model_components.get("musetalk", {"source": {"status": "unknown"}, "runtime": {"status": "unknown"}, "assets_ready": 0, "assets_total": 0}),
            },
        },
        "assets": {
            "character_count": len(characters),
            "characters": characters,
            "driving_count": 0,
            "driving_templates": [],
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


def _resolve_character_image(job_spec: Dict[str, Any]) -> Path:
    character_root = (ROOT_DIR / "assets" / "characters").resolve()
    source = job_spec.get("source")
    if source:
        image = Path(str(source)).expanduser()
        if not image.is_absolute():
            image = ROOT_DIR / image
        image = image.resolve()
        if not image.is_relative_to(character_root):
            raise ValueError("Ảnh nguồn phải nằm trong assets/characters/ của ứng dụng.")
    else:
        identity = " ".join(str(job_spec.get(key, "")) for key in ("char", "gender", "name")).casefold()
        if any(token in identity for token in ("female", "woman", "nữ")):
            relative = Path("nhanvatnu") / "ChatGPT Image Sep 14, 2026, 11_35_53 AM (1).png"
        elif any(token in identity for token in ("male", "man", "nam", "office")):
            relative = Path("nhanvatnam") / "ChatGPT Image Sep 8, 2026, 08_46_26 AM (1).png"
        else:
            raise ValueError("Job chưa chọn ảnh nhân vật nam/nữ hợp lệ.")
        image = character_root / relative

    if image.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"} or not image.is_file():
        raise FileNotFoundError(f"Không tìm thấy ảnh nhân vật hợp lệ: {image}")
    return image


def _resolve_job_audio(job_spec: Dict[str, Any], job_id: str) -> Path:
    audio_value = job_spec.get("audio")
    if audio_value:
        audio_path = Path(str(audio_value)).expanduser()
        if not audio_path.is_absolute():
            audio_path = ROOT_DIR / audio_path
        audio_path = audio_path.resolve()
        if not audio_path.is_file():
            raise FileNotFoundError(f"Không tìm thấy file audio: {audio_path}")
        return audio_path

    script_text = str(job_spec.get("script") or "").strip()
    if not script_text:
        raise ValueError("Job cần có kịch bản hoặc file audio.")
    audio_path = ROOT_DIR / "temp" / f"{job_id}_pipeline_speech.mp3"
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    voice = str(job_spec.get("voice") or "vi-VN-NamMinhNeural")
    emit_progress("audio_tts", 5.0, f"Đang tạo giọng đọc ({voice})...")
    try:
        duration, voice_used = synthesize_voice(
            script_text, voice, audio_path, gender_hint=job_spec.get("gender"),
        )
    except Exception as error:
        audio_path.unlink(missing_ok=True)
        raise RuntimeError(f"Không tạo được giọng đọc; job dừng trước khi render: {error}") from error
    emit_log(f"[TTS] Đã tạo audio bằng {voice_used}: {audio_path.name} ({duration:.2f}s).")
    return audio_path


def _preflight_audio(job_spec: Dict[str, Any], job_id: str) -> Tuple[Path, bool]:
    if job_spec.get("audio"):
        return _resolve_job_audio(job_spec, job_id), False
    # The pipeline's dry-run needs a media stream to inspect. A short silent WAV
    # is only a preflight fixture; it is never used by a production render.
    audio_path = ROOT_DIR / "temp" / f"{job_id}_preflight_silence.wav"
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    sample_rate = 16000
    duration_seconds = 3.2
    with wave.open(str(audio_path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        audio.writeframes(b"\0\0" * int(sample_rate * duration_seconds))
    return audio_path, True


def _verified_output_from_log(output_root: Path, log_lines: list[str]) -> Optional[Path]:
    for line in reversed(log_lines):
        match = re.search(r"Verified 1080x1920 output:\s*(.*?)\s*\|", line)
        if match:
            candidate = Path(match.group(1).strip()).expanduser().resolve()
            if candidate.is_file() and candidate.stat().st_size > 0:
                return candidate
    reports = sorted(
        output_root.glob("job_*/vertical_ad_report.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for report_path in reports:
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
            if report.get("status") != "complete":
                continue
            for video in report.get("videos", []):
                value = (video.get("output") or {}).get("path")
                if value:
                    candidate = Path(value).expanduser().resolve()
                    if candidate.is_file() and candidate.stat().st_size > 0:
                        return candidate
        except (OSError, ValueError, TypeError):
            continue
    return None


def _resolve_output_name(value: Any) -> Optional[str]:
    """Accept a single safe MP4 filename, including legacy output/name.mp4 manifests."""
    if value is None or not str(value).strip():
        return None
    name = str(value).strip().replace("\\", "/")
    if name.startswith("output/"):
        name = name[len("output/"):]
    if "/" in name or name in {".", ".."} or any(character in name for character in '<>:"|?*'):
        raise ValueError("Tên file đầu ra chỉ được là tên MP4, không chứa đường dẫn hoặc ký tự đặc biệt.")
    if not name.lower().endswith(".mp4"):
        if Path(name).suffix:
            raise ValueError("File đầu ra phải có phần mở rộng .mp4.")
        name += ".mp4"
    return name


def run_pipeline_job(job_spec: Dict[str, Any]) -> int:
    """Run a real vertical Echo Flash + MuseTalk render or a preflight-only dry run."""
    job_id = str(job_spec.get("id") or "job_direct")
    emit_event("job_started", {"job_id": job_id, "spec": job_spec})
    emit_progress("preflight", 2.0, "Kiểm tra ảnh, audio và model trước khi chạy core...")

    pipeline_script = ROOT_DIR / "scripts" / "test_vertical_ads.py"
    if not pipeline_script.is_file():
        message = f"Không tìm thấy pipeline Echo Flash + MuseTalk: {pipeline_script}"
        emit_event("job_failed", {"job_id": job_id, "error": message})
        emit_log(message)
        return 1

    try:
        image_path = _resolve_character_image(job_spec)
        output_name = _resolve_output_name(job_spec.get("output"))
        if job_spec.get("dry_run"):
            audio_path, remove_preflight_audio = _preflight_audio(job_spec, job_id)
            action = "dry-run"
        else:
            audio_path = _resolve_job_audio(job_spec, job_id)
            remove_preflight_audio = False
            action = "run"
    except Exception as error:
        message = str(error)
        emit_log(f"[Preflight] {message}")
        emit_event("job_failed", {"job_id": job_id, "error": message})
        return 1

    profile = str(job_spec.get("profile") or "A10")
    if profile not in {"F10", "A10", "A10HQ"}:
        message = f"Profile render không hợp lệ: {profile}"
        emit_event("job_failed", {"job_id": job_id, "error": message})
        return 1
    safe_job_id = re.sub(r"[^a-zA-Z0-9_-]+", "_", job_id)[:80] or "job"
    output_root = ROOT_DIR / "output" / "studio_jobs" / safe_job_id
    output_root.mkdir(parents=True, exist_ok=True)
    cmd = [
        detect_python_executable(), "-u", str(pipeline_script), action,
        "--profile", profile,
        "--image", str(image_path),
        "--audio", str(audio_path),
        "--output-root", str(output_root),
        "--batch-size", str(max(1, min(4, int(job_spec.get("batch_size") or 2)))),
    ]
    if output_name:
        cmd.extend(["--output-name", output_name])
    duration = job_spec.get("duration")
    if duration is not None:
        try:
            duration_value = float(duration)
        except (TypeError, ValueError):
            duration_value = 0
        if duration_value > 0:
            cmd.extend(["--duration", str(duration_value)])

    emit_log(f"Pipeline ({action}): {json.dumps(cmd, ensure_ascii=False)}")
    try:
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
    except OSError as error:
        if remove_preflight_audio:
            audio_path.unlink(missing_ok=True)
        emit_event("job_failed", {"job_id": job_id, "error": f"Không khởi chạy được pipeline: {error}"})
        return 1
    log_lines: list[str] = []
    current_stage = "preflight"
    current_percent = 4.0

    try:
        if proc.stdout is not None:
            for raw_line in proc.stdout:
                line = raw_line.strip()
                if not line:
                    continue
                log_lines.append(line)
                emit_log(line)

                lowered = line.casefold()
                if "echo" in lowered and any(token in lowered for token in ("motion base", "generation", "denois", "wan")):
                    current_stage, current_percent = "motion_base", min(45.0, max(current_percent, 15.0))
                    emit_progress(current_stage, current_percent, line)
                elif "musetalk" in lowered or "avatar preprocessing" in lowered or "inference" in lowered:
                    current_stage, current_percent = "musetalk", min(80.0, max(current_percent, 50.0))
                    emit_progress(current_stage, current_percent, line)
                elif "verified 1080x1920 output" in lowered or "hd export" in lowered:
                    current_stage, current_percent = "verifying", 92.0
                    emit_progress(current_stage, current_percent, line)
                elif current_stage == "musetalk" and ("render " in lowered or "it/s" in lowered):
                    current_percent = min(84.0, current_percent + 1.0)
                    emit_progress(current_stage, current_percent, line)

        proc.wait()
        if proc.returncode != 0:
            message = next((line for line in reversed(log_lines) if "failed" in line.casefold() or "error" in line.casefold()),
                           f"Pipeline kết thúc với mã lỗi {proc.returncode}.")
            emit_event("job_failed", {"job_id": job_id, "returncode": proc.returncode, "error": message})
            return proc.returncode or 1

        if action == "dry-run":
            emit_progress("validated", 100.0, "Preflight đạt; chưa tạo video và chưa chạy inference.")
            emit_event("job_validated", {"job_id": job_id, "status": "validated", "output": None})
            return 0

        output_video = _verified_output_from_log(output_root, log_lines)
        if output_video is None:
            message = "Pipeline trả mã 0 nhưng không tìm thấy video 1080x1920 đã được xác minh; job không được đánh dấu hoàn tất."
            emit_event("job_failed", {"job_id": job_id, "error": message})
            return 1

        emit_progress("completed", 100.0, "Video 9:16 đã được pipeline xác minh.")
        emit_event("job_completed", {"job_id": job_id, "output": str(output_video), "status": "success"})
        return 0
    except KeyboardInterrupt:
        emit_log("Nhận tín hiệu dừng từ người dùng. Đang đóng tiến trình pipeline...")
        if proc.poll() is None:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, creationflags=CREATE_NO_WINDOW)
            else:
                proc.terminate()
        emit_event("job_cancelled", {"job_id": job_id})
        return 130
    finally:
        if remove_preflight_audio:
            audio_path.unlink(missing_ok=True)


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
