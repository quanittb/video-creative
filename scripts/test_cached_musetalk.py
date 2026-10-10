#!/usr/bin/env python3
"""Prepare/reuse a MuseTalk v1.5 avatar cache and render a short test clip."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Mapping, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CACHE_SCHEMA = 1
NORMALIZATION_SPEC = {
    "audio_sample_rate": 16000,
    "audio_channels": 1,
    "audio_codec": "pcm_s16le",
    "audio_trim_policy": "trim_to_requested_duration_or_input_end",
    "video_policy": "preserve_source_frames_and_resolution; require_source_fps_matches_target",
}


class PipelineError(RuntimeError):
    """A preflight, cache-integrity, or render failure safe to show to the user."""


@dataclass(frozen=True)
class MuseTalkPaths:
    root: Path
    python: Path
    inference_script: Path
    unet_model: Path
    unet_config: Path
    whisper_dir: Path
    vae_dir: Path
    dwpose_dir: Path
    face_parsing_dir: Path


@dataclass(frozen=True)
class MediaInfo:
    duration: float
    width: int
    height: int
    fps: float
    has_video: bool
    has_audio: bool
    sample_rate: int = 0
    channels: int = 0
    audio_codec: str = ""
    video_duration: float = 0.0
    audio_duration: float = 0.0


def _resolve_project_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def _import_runner_path_finder() -> Callable[[], tuple[Path | None, Path | None]]:
    """Load the existing path discovery helper without importing GPU libraries."""
    runner_path = PROJECT_ROOT / "runners" / "lipsync_runner.py"
    if not runner_path.is_file():
        raise PipelineError(f"Không tìm thấy helper dò MuseTalk: {runner_path}")
    spec = importlib.util.spec_from_file_location("vcs_lipsync_runner_path_helper", str(runner_path))
    if spec is None or spec.loader is None:
        raise PipelineError(f"Không nạp được helper dò MuseTalk: {runner_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.find_musetalk_paths


def discover_musetalk_paths(
    musetalk_dir: str | Path | None = None,
    musetalk_python: str | Path | None = None,
) -> MuseTalkPaths:
    discovered_dir, discovered_python = _import_runner_path_finder()()
    root = _resolve_project_path(musetalk_dir) if musetalk_dir else discovered_dir
    python = _resolve_project_path(musetalk_python) if musetalk_python else discovered_python
    if root is None:
        raise PipelineError(
            "Chưa tìm thấy mã nguồn MuseTalk. Truyền --musetalk-dir và --musetalk-python "
            "hoặc cài MuseTalk theo setup_musetalk.bat."
        )
    if python is None:
        raise PipelineError(
            "Chưa tìm thấy Python của MuseTalk. Truyền --musetalk-python tới python.exe trong "
            "môi trường đã cài MuseTalk."
        )

    root = Path(root).resolve()
    python = Path(python).resolve()
    model_root = root / "models"
    config_candidates = (
        model_root / "musetalkV15" / "musetalk.json",
        model_root / "musetalkV15" / "config.json",
        model_root / "musetalk" / "config.json",
        model_root / "musetalk" / "musetalk.json",
    )
    config = next((candidate for candidate in config_candidates if candidate.is_file()), None)
    if config is None:
        config = config_candidates[0]

    return MuseTalkPaths(
        root=root,
        python=python,
        inference_script=root / "scripts" / "realtime_inference.py",
        unet_model=model_root / "musetalkV15" / "unet.pth",
        unet_config=config,
        whisper_dir=model_root / "whisper",
        vae_dir=model_root / "sd-vae",
        dwpose_dir=model_root / "dwpose",
        face_parsing_dir=model_root / "face-parse-bisent",
    )


def validate_musetalk_install(paths: MuseTalkPaths) -> None:
    missing: list[str] = []
    required_files = (
        (paths.python, "Python MuseTalk"),
        (paths.inference_script, "scripts/realtime_inference.py"),
        (paths.unet_model, "models/musetalkV15/unet.pth"),
        (paths.unet_config, "cấu hình UNet v1.5"),
        (paths.whisper_dir / "config.json", "models/whisper/config.json"),
        (paths.whisper_dir / "preprocessor_config.json", "models/whisper/preprocessor_config.json"),
        (paths.vae_dir / "config.json", "models/sd-vae/config.json"),
        (paths.dwpose_dir / "dw-ll_ucoco_384.pth", "models/dwpose/dw-ll_ucoco_384.pth"),
        (paths.face_parsing_dir / "79999_iter.pth", "models/face-parse-bisent/79999_iter.pth"),
        (paths.face_parsing_dir / "resnet18-5c106cde.pth", "models/face-parse-bisent/resnet18-5c106cde.pth"),
    )
    for path, label in required_files:
        if not path.is_file() or path.stat().st_size == 0:
            missing.append(f"{label}: {path}")
    whisper_weights = (paths.whisper_dir / "pytorch_model.bin", paths.whisper_dir / "model.safetensors")
    if not any(path.is_file() and path.stat().st_size > 0 for path in whisper_weights):
        missing.append(f"trọng số Whisper trong {paths.whisper_dir} (pytorch_model.bin hoặc model.safetensors)")
    vae_weights = (
        paths.vae_dir / "diffusion_pytorch_model.bin",
        paths.vae_dir / "diffusion_pytorch_model.safetensors",
    )
    if not any(path.is_file() and path.stat().st_size > 0 for path in vae_weights):
        missing.append(f"trọng số VAE trong {paths.vae_dir} (diffusion_pytorch_model.bin hoặc .safetensors)")
    if missing:
        raise PipelineError("MuseTalk v1.5 còn thiếu file cần thiết:\n  - " + "\n  - ".join(missing))


def find_ffmpeg_pair(ffmpeg_override: str | None = None, ffprobe_override: str | None = None) -> tuple[str, str]:
    ffmpeg = ffmpeg_override or shutil.which("ffmpeg")
    ffprobe = ffprobe_override or shutil.which("ffprobe")
    if ffmpeg is None and ffprobe_override:
        ffmpeg = shutil.which("ffmpeg")
    if ffprobe is None and ffmpeg:
        sibling = Path(ffmpeg).resolve().with_name("ffprobe.exe" if os.name == "nt" else "ffprobe")
        if sibling.is_file():
            ffprobe = str(sibling)
    if not ffmpeg or not ffprobe:
        raise PipelineError("Cần cài ffmpeg và ffprobe, đồng thời thêm cả hai vào PATH.")
    return str(ffmpeg), str(ffprobe)


def _parse_rate(value: str | None) -> float:
    if not value:
        return 0.0
    if "/" in value:
        numerator, denominator = value.split("/", 1)
        try:
            denominator_value = float(denominator)
            return float(numerator) / denominator_value if denominator_value else 0.0
        except ValueError:
            return 0.0
    try:
        return float(value)
    except ValueError:
        return 0.0


def probe_media(path: Path, ffprobe: str) -> MediaInfo:
    if not path.is_file():
        raise PipelineError(f"Không tìm thấy media: {path}")
    command = [
        ffprobe,
        "-v", "error",
        "-show_entries", "format=duration:stream=codec_type,width,height,avg_frame_rate,r_frame_rate,duration,sample_rate,channels,codec_name",
        "-of", "json",
        str(path),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    except OSError as exc:
        raise PipelineError(f"Không chạy được ffprobe ({ffprobe}): {exc}") from exc
    if result.returncode != 0:
        raise PipelineError(f"ffprobe không đọc được {path}: {result.stderr.strip()}")
    try:
        payload = json.loads(result.stdout)
        streams = payload.get("streams", [])
        video = next((item for item in streams if item.get("codec_type") == "video"), None)
        audio = next((item for item in streams if item.get("codec_type") == "audio"), None)
        fmt_duration = float(payload.get("format", {}).get("duration") or 0.0)
        if video:
            video_duration = float(video.get("duration") or 0.0)
            fps = _parse_rate(video.get("avg_frame_rate")) or _parse_rate(video.get("r_frame_rate"))
            width = int(video.get("width") or 0)
            height = int(video.get("height") or 0)
        else:
            video_duration, fps, width, height = 0.0, 0.0, 0, 0
        if audio:
            audio_duration = float(audio.get("duration") or 0.0)
            sample_rate = int(audio.get("sample_rate") or 0)
            channels = int(audio.get("channels") or 0)
            audio_codec = str(audio.get("codec_name") or "")
        else:
            audio_duration = 0.0
            sample_rate, channels, audio_codec = 0, 0, ""
        # Keep per-stream lengths so a short audio stream cannot hide a long video
        # (or vice versa) behind the container's aggregate duration.
        duration = video_duration or audio_duration or fmt_duration
        return MediaInfo(
            duration=duration,
            width=width,
            height=height,
            fps=fps,
            has_video=video is not None,
            has_audio=audio is not None,
            sample_rate=sample_rate,
            channels=channels,
            audio_codec=audio_codec,
            video_duration=video_duration,
            audio_duration=audio_duration,
        )
    except (KeyError, TypeError, ValueError, StopIteration) as exc:
        raise PipelineError(f"Thông tin ffprobe không hợp lệ cho {path}: {exc}") from exc


def validate_duration_coverage(audio_seconds: float, base_seconds: float, fps: int) -> None:
    if not math.isfinite(audio_seconds) or not math.isfinite(base_seconds) or audio_seconds <= 0 or base_seconds <= 0:
        raise PipelineError("Audio và video nền phải có thời lượng lớn hơn 0.")
    # A single-frame tolerance covers container timestamp rounding without permitting a loop.
    if audio_seconds > base_seconds + (0.5 / fps):
        raise PipelineError(
            f"Audio sau khi cắt dài {audio_seconds:.3f}s nhưng video nền chỉ phủ "
            f"{base_seconds:.3f}s. Cắt ngắn --duration hoặc cung cấp video nền dài hơn; "
            "script từ chối để MuseTalk không lặp ngầm video nền."
        )


def validate_pingpong_support(inference_script: Path) -> None:
    try:
        source = inference_script.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise PipelineError(f"Không đọc được realtime inference source để xác minh ping-pong: {inference_script}: {exc}") from exc
    normalized = " ".join(source.split())
    required_patterns = (
        "self.frame_list_cycle = frame_list + frame_list[::-1]",
        "self.coord_list_cycle = coord_list + coord_list[::-1]",
        "self.input_latent_list_cycle = input_latent_list + input_latent_list[::-1]",
        "self.frame_list_cycle[self.idx % (len(self.frame_list_cycle))]",
        "self.coord_list_cycle[self.idx % (len(self.coord_list_cycle))]",
        "datagen(whisper_chunks, self.input_latent_list_cycle, self.batch_size)",
    )
    missing = [pattern for pattern in required_patterns if pattern not in normalized]
    if missing:
        raise PipelineError(
            "--motion-policy pingpong chỉ được bật khi realtime_inference.py có cấu trúc forward+reverse "
            "và modulo đã kiểm tra; source hiện tại khác phiên bản hỗ trợ. Dùng policy mặc định error "
            f"hoặc kiểm tra source: {inference_script} (thiếu: {', '.join(missing)})."
        )


def validate_bbox_shift_support(inference_script: Path, bbox_shift: int) -> None:
    if bbox_shift == 0:
        return
    try:
        source = inference_script.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise PipelineError(f"Không đọc được realtime inference source để xác minh bbox_shift: {inference_script}: {exc}") from exc
    if re.search(r"if\s+args\.version\s*==\s*['\"]v15['\"]\s*:\s*bbox_shift\s*=\s*0\b", source):
        raise PipelineError(
            "MuseTalk v1.5 trong máy này ép bbox_shift về 0 trong realtime_inference.py; "
            "giá trị khác 0 sẽ bị upstream bỏ qua và không thể dùng để hiệu chỉnh. "
            "Hãy chạy với --bbox-shift 0 và so sánh parsing mode jaw/raw."
        )


def validate_motion_coverage(
    audio_seconds: float,
    base_seconds: float,
    fps: int,
    motion_policy: str,
) -> None:
    if motion_policy not in {"error", "pingpong"}:
        raise PipelineError("--motion-policy chỉ nhận error hoặc pingpong.")
    if motion_policy == "error":
        validate_duration_coverage(audio_seconds, base_seconds, fps)
        return
    if not math.isfinite(audio_seconds) or not math.isfinite(base_seconds) or audio_seconds <= 0 or base_seconds <= 0:
        raise PipelineError("Audio và video nền phải có thời lượng lớn hơn 0.")


def build_motion_metadata(audio_seconds: float, base_seconds: float, motion_policy: str) -> dict[str, object]:
    cycle_seconds = 2.0 * base_seconds
    cycle_count = (
        int(math.ceil(audio_seconds / cycle_seconds))
        if motion_policy == "pingpong" and audio_seconds > 0 and cycle_seconds > 0
        else (1 if audio_seconds > 0 and cycle_seconds > 0 else 0)
    )
    return {
        "motion_policy": motion_policy,
        "source_video_duration_seconds": round(base_seconds, 6),
        "nominal_full_motion_cycle_seconds": round(cycle_seconds, 6),
        "nominal_motion_cycles": cycle_count,
        "nominal_motion_repeats": max(0, cycle_count - 1),
    }


def validate_base_media(info: MediaInfo, fps: int) -> None:
    if not info.has_video or info.width <= 0 or info.height <= 0:
        raise PipelineError("Video nền không có luồng hình hợp lệ.")
    video_duration = info.video_duration or info.duration
    if not math.isfinite(video_duration) or video_duration <= 0:
        raise PipelineError("Không đọc được thời lượng video nền.")
    if info.fps <= 0 or abs(info.fps - fps) > 0.10:
        raise PipelineError(
            f"FPS video nền là {info.fps:.3f}, khác mục tiêu {fps} FPS. "
            "Hãy xuất motion-base thành CFR đúng FPS trước khi chạy để tránh lệch thời gian."
        )


def normalize_audio(
    source: Path,
    destination: Path,
    requested_duration: float,
    ffmpeg: str,
    ffprobe: str,
) -> tuple[float, MediaInfo]:
    source_info = probe_media(source, ffprobe)
    source_duration = source_info.audio_duration or source_info.duration
    if not source_info.has_audio or not math.isfinite(source_duration) or source_duration <= 0:
        raise PipelineError(f"File không có audio hợp lệ: {source}")
    if not math.isfinite(float(requested_duration)):
        raise PipelineError("--duration phải là số hữu hạn lớn hơn 0.")
    effective_duration = min(float(requested_duration), source_duration)
    if effective_duration <= 0:
        raise PipelineError("--duration phải lớn hơn 0.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    command = [
        ffmpeg, "-y", "-v", "error", "-i", str(source), "-vn",
        "-t", f"{effective_duration:.6f}", "-ac", "1", "-ar", "16000",
        "-c:a", "pcm_s16le", str(destination),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    except OSError as exc:
        raise PipelineError(f"Không chạy được ffmpeg để chuẩn hóa audio: {exc}") from exc
    if result.returncode != 0 or not destination.is_file() or destination.stat().st_size == 0:
        raise PipelineError(f"Chuẩn hóa audio thất bại: {result.stderr.strip()}")
    normalized_info = probe_media(destination, ffprobe)
    if not normalized_info.has_audio:
        raise PipelineError("ffmpeg tạo file chuẩn hóa nhưng không có luồng audio.")
    if normalized_info.sample_rate != NORMALIZATION_SPEC["audio_sample_rate"] or normalized_info.channels != 1 or normalized_info.audio_codec != "pcm_s16le":
        raise PipelineError(
            "Audio sau chuẩn hóa không đạt pcm_s16le, 16kHz, mono "
            f"(codec={normalized_info.audio_codec}, rate={normalized_info.sample_rate}, channels={normalized_info.channels})."
        )
    normalized_duration = normalized_info.audio_duration or normalized_info.duration
    if abs(normalized_duration - effective_duration) > 0.12:
        raise PipelineError(
            f"Độ dài audio sau chuẩn hóa {normalized_duration:.3f}s lệch khỏi "
            f"mục tiêu {effective_duration:.3f}s quá 0.12s."
        )
    return normalized_duration, normalized_info


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_signature(path: Path, root: Path | None = None) -> dict[str, object]:
    stat = path.stat()
    signature: dict[str, object] = {
        "path": str(path.relative_to(root).as_posix()) if root else path.name,
        "size": stat.st_size,
        "mtime_ns": getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000)),
    }
    # Hash small source/config files exactly; checkpoint files are represented by stable stat data.
    if stat.st_size <= 2 * 1024 * 1024:
        signature["sha256"] = sha256_file(path)
    return signature


def _directory_signature(path: Path) -> list[dict[str, object]]:
    if not path.is_dir():
        return []
    entries = []
    transient_directories = {"__pycache__", ".git", ".pytest_cache", ".mypy_cache"}
    for child in sorted(path.rglob("*")):
        relative_parts = child.relative_to(path).parts
        is_transient = any(part in transient_directories or part.startswith(".") for part in relative_parts)
        if child.is_file() and child.suffix.lower() not in {".pyc", ".pyo"} and not is_transient:
            entries.append(_file_signature(child, path))
    return entries


def build_fingerprint_inputs(
    base_video: Path,
    base_info: MediaInfo,
    fps: int,
    paths: MuseTalkPaths,
    parsing_mode: str = "jaw",
    extra_margin: int = 10,
    left_cheek_width: int = 90,
    right_cheek_width: int = 90,
    bbox_shift: int = 0,
) -> dict[str, object]:
    models_root = paths.root / "models"
    tracked_dirs = {
        "whisper": paths.whisper_dir,
        "vae": paths.vae_dir,
        "dwpose": paths.dwpose_dir,
        "face_parsing": paths.face_parsing_dir,
        "upstream_scripts": paths.root / "scripts",
        "upstream_musetalk_code": paths.root / "musetalk",
    }
    upstream_signature = _file_signature(paths.inference_script)
    python_signature = _file_signature(paths.python)
    unet_signature = _file_signature(paths.unet_model)
    config_signature = _file_signature(paths.unet_config)
    return {
        "schema": CACHE_SCHEMA,
        "base_video": {
            "sha256": sha256_file(base_video),
            "size": base_video.stat().st_size,
            "duration_seconds": round(base_info.duration, 6),
            "width": base_info.width,
            "height": base_info.height,
            "source_fps": round(base_info.fps, 6),
            "target_fps": fps,
        },
        "musetalk": {
            "version": "v15",
            "upstream_script": upstream_signature,
            "python_runtime": python_signature,
            "unet": unet_signature,
            "unet_config": config_signature,
            "model_directories": {
                key: _directory_signature(path) for key, path in tracked_dirs.items()
            },
            "model_layout": {
                "models_root_name": models_root.name,
                "vae_type": "sd-vae",
                "version": "v15",
            },
            "parameters": {
                "bbox_shift": bbox_shift,
                "parsing_mode": parsing_mode,
                "extra_margin": extra_margin,
                "left_cheek_width": left_cheek_width,
                "right_cheek_width": right_cheek_width,
                "weight_dtype": "upstream_fp16_always",
            },
        },
        "normalization": dict(NORMALIZATION_SPEC),
    }


def fingerprint_key(inputs: Mapping[str, object]) -> str:
    canonical = json.dumps(inputs, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def cache_target(cache_dir: Path, key: str) -> Path:
    return cache_dir / key[:32]


def is_safe_upstream_path(path: str | Path) -> bool:
    value = str(path)
    if not value or not value.isascii():
        return False
    unsafe_shell_chars = set(" \t\r\n\"'&|<>^()%!")
    return not any(character in unsafe_shell_chars for character in value)


def validate_safe_cache_root(cache_dir: Path) -> None:
    if not is_safe_upstream_path(cache_dir.resolve()):
        raise PipelineError(
            f"Đường dẫn cache chứa khoảng trắng, ký tự shell hoặc Unicode: {cache_dir.resolve()}\n"
            "MuseTalk upstream ghép một số lệnh ffmpeg bằng shell không có dấu nháy. "
            "Hãy dùng cache root ASCII không có khoảng trắng, ví dụ --cache-dir C:\\vcs_cache."
        )


def validate_safe_musetalk_root(musetalk_root: Path) -> None:
    if not is_safe_upstream_path(musetalk_root.resolve()):
        raise PipelineError(
            f"Thư mục MuseTalk chứa khoảng trắng, ký tự shell hoặc Unicode: {musetalk_root.resolve()}\n"
            "Realtime inference ghép lệnh ffmpeg bằng shell và ghi ./results tương đối theo thư mục này. "
            "Đặt MuseTalk vào đường dẫn ASCII không có khoảng trắng, ví dụ C:\\MuseTalk."
        )


def validate_output_target(output: Path, input_paths: Sequence[Path], protected_roots: Sequence[Path]) -> Path:
    output = output.resolve()
    for source in input_paths:
        source = source.resolve()
        try:
            same_file = output.exists() and source.exists() and os.path.samefile(output, source)
        except OSError:
            same_file = False
        if output == source or same_file:
            raise PipelineError(f"Output không được trùng hoặc là hardlink của file đầu vào: {output}")
    for protected_root in protected_roots:
        protected_root = protected_root.resolve()
        if output == protected_root or output.is_relative_to(protected_root):
            raise PipelineError(f"Output không được ghi bên trong cache/avatar input tree: {protected_root}")
    return output


def avatar_dir_for(work_root: Path, avatar_id: str) -> Path:
    return work_root / "results" / "v15" / "avatars" / avatar_id


def validate_avatar_cache_files(work_root: Path, avatar_id: str, bbox_shift: int = 0) -> None:
    avatar_dir = avatar_dir_for(work_root, avatar_id)
    required = (
        avatar_dir / "avator_info.json",
        avatar_dir / "coords.pkl",
        avatar_dir / "latents.pt",
        avatar_dir / "mask_coords.pkl",
        avatar_dir / "full_imgs",
        avatar_dir / "mask",
    )
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise PipelineError("Cache avatar chưa đầy đủ; thiếu:\n  - " + "\n  - ".join(missing))
    for filename in ("coords.pkl", "latents.pt", "mask_coords.pkl"):
        path = avatar_dir / filename
        if not path.is_file() or path.stat().st_size == 0:
            raise PipelineError(f"Cache avatar chưa đầy đủ hoặc file rỗng: {path}")
    full_images = [path for path in (avatar_dir / "full_imgs").glob("*.png") if path.stat().st_size > 0]
    masks = [path for path in (avatar_dir / "mask").glob("*.png") if path.stat().st_size > 0]
    if not full_images or not masks or len(full_images) != len(masks):
        raise PipelineError(
            f"Cache avatar chưa đầy đủ: full_imgs={len(full_images)}, mask={len(masks)} tại {avatar_dir}"
        )
    try:
        info = json.loads((avatar_dir / "avator_info.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PipelineError(f"Không đọc được avator_info.json trong cache {avatar_dir}: {exc}") from exc
    if info.get("avatar_id") != avatar_id or info.get("version") != "v15" or info.get("bbox_shift") != bbox_shift:
        raise PipelineError(f"Cache avatar sai phiên bản hoặc bbox_shift: {avatar_dir}")


def read_cache_manifest(
    cache_path: Path,
    key: str,
    inputs: Mapping[str, object],
    avatar_id: str,
    musetalk_root: Path,
) -> dict[str, object] | None:
    avatar_path = avatar_dir_for(musetalk_root, avatar_id)
    if not cache_path.exists():
        if avatar_path.exists():
            raise PipelineError(
                f"Đã có thư mục avatar upstream nhưng thiếu controller manifest: {avatar_path}. "
                "Có thể lần chạy trước bị ngắt giữa chừng; tôi giữ nguyên thư mục và không ghi đè."
            )
        return None
    if not cache_path.is_dir():
        raise PipelineError(f"Cache path đã tồn tại nhưng không phải thư mục; giữ nguyên để kiểm tra: {cache_path}")
    manifest_path = cache_path / "cache_manifest.json"
    if not manifest_path.is_file():
        raise PipelineError(
            f"Phát hiện cache dở hoặc thiếu manifest tại {cache_path}. Tôi giữ nguyên cache này, "
            "không tự xóa; đổi --cache-dir hoặc tự kiểm tra thư mục trước khi chạy lại."
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PipelineError(f"Manifest cache lỗi tại {manifest_path}; giữ nguyên dữ liệu: {exc}") from exc
    if manifest.get("schema") != CACHE_SCHEMA or manifest.get("fingerprint") != key or manifest.get("inputs") != inputs:
        raise PipelineError(
            f"Manifest cache không khớp với fingerprint hiện tại tại {cache_path}; giữ nguyên cache cũ."
        )
    try:
        validate_avatar_cache_files(musetalk_root, avatar_id, int(inputs.get("musetalk", {}).get("parameters", {}).get("bbox_shift", 0)))
    except PipelineError as exc:
        raise PipelineError(f"Cache partial/corrupt tại {cache_path}; không xóa cache cũ. {exc}") from exc
    base_copy = cache_path / "input" / "base_video.mp4"
    base_inputs = inputs.get("base_video", {})
    expected_base_hash = base_inputs.get("sha256") if isinstance(base_inputs, Mapping) else None
    if not base_copy.is_file() or not expected_base_hash or sha256_file(base_copy) != expected_base_hash:
        raise PipelineError(
            f"Bản sao video nền trong cache thiếu hoặc sai SHA-256: {base_copy}; giữ nguyên cache cũ."
        )
    return manifest


def _write_json_atomic(path: Path, payload: Mapping[str, object]) -> None:
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temp, path)


def _log_status(log_path: Path, message: str) -> None:
    print(message)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8", errors="replace") as log:
        log.write(message + "\n")


def _write_cache_manifest(
    stage: Path,
    key: str,
    inputs: Mapping[str, object],
    avatar_id: str,
    musetalk_root: Path,
) -> None:
    validate_avatar_cache_files(musetalk_root, avatar_id, int(inputs.get("musetalk", {}).get("parameters", {}).get("bbox_shift", 0)))
    manifest = {
        "schema": CACHE_SCHEMA,
        "fingerprint": key,
        "inputs": inputs,
        "avatar_id": avatar_id,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "cache_assets": {
            "avatar_asset_path": str(avatar_dir_for(musetalk_root, avatar_id)),
            "full_image_count": len(list((avatar_dir_for(musetalk_root, avatar_id) / "full_imgs").glob("*.png"))),
            "mask_count": len(list((avatar_dir_for(musetalk_root, avatar_id) / "mask").glob("*.png"))),
        },
    }
    _write_json_atomic(stage / "cache_manifest.json", manifest)


def _yaml_string(value: str | Path) -> str:
    return json.dumps(Path(value).as_posix() if isinstance(value, Path) else value, ensure_ascii=True)


def write_inference_config(
    path: Path,
    avatar_id: str,
    video_path: Path,
    preparation: bool,
    audio_path: Path | None,
    output_name: str | None,
    bbox_shift: int = 0,
) -> None:
    if output_name and not output_name.isascii():
        raise PipelineError("Tên file tạm upstream chỉ dùng ký tự ASCII.")
    audio_yaml = f"  audio_clips:\n    {output_name}: " + _yaml_string(audio_path) + "\n" if audio_path and output_name else "  audio_clips: {}\n"
    text = (
        f"{avatar_id}:\n"
        f"  preparation: {'true' if preparation else 'false'}\n"
        f"  bbox_shift: {bbox_shift}\n"
        f"  video_path: {_yaml_string(video_path)}\n"
        f"{audio_yaml}"
    )
    path.write_text(text, encoding="utf-8")


def build_backend_command(
    paths: MuseTalkPaths,
    config_path: Path,
    output_name: str | None,
    batch_size: int,
    fps: int,
    parsing_mode: str,
    extra_margin: int,
    left_cheek_width: int,
    right_cheek_width: int,
    audio_padding_left: int,
    audio_padding_right: int,
    bbox_shift: int = 0,
) -> list[str]:
    command = [
        str(paths.python), "-u", str(paths.inference_script),
        "--inference_config", str(config_path),
        # Avatar currently anchors assets at cwd/results/v15/avatars; process cwd is paths.root.
        # This argument is aligned for upstream versions that honor it.
        "--result_dir", str(paths.root / "results"),
        "--unet_model_path", str(paths.unet_model),
        "--unet_config", str(paths.unet_config),
        "--whisper_dir", str(paths.whisper_dir),
        "--version", "v15",
        "--vae_type", "sd-vae",
        "--batch_size", str(batch_size),
        "--fps", str(fps),
        "--bbox_shift", str(bbox_shift),
        "--parsing_mode", parsing_mode,
        "--extra_margin", str(extra_margin),
        "--left_cheek_width", str(left_cheek_width),
        "--right_cheek_width", str(right_cheek_width),
        "--audio_padding_length_left", str(audio_padding_left),
        "--audio_padding_length_right", str(audio_padding_right),
    ]
    if output_name:
        command.extend(["--output_vid_name", output_name])
    # Never add --skip_save_images: upstream would then report success without an MP4.
    # Realtime inference already converts the model components to FP16 unconditionally.
    return command


def build_backend_environment(
    ffmpeg: str,
    base_environment: Mapping[str, str] | None = None,
    *,
    musetalk_root: Path | None = None,
) -> dict[str, str]:
    environment = dict(base_environment or os.environ)
    ffmpeg_parent = str(Path(ffmpeg).resolve().parent)
    current_path = environment.get("PATH", "")
    environment["PATH"] = ffmpeg_parent + (os.pathsep + current_path if current_path else "")
    if musetalk_root is not None:
        root = str(musetalk_root.resolve())
        current_pythonpath = environment.get("PYTHONPATH", "")
        environment["PYTHONPATH"] = root + (os.pathsep + current_pythonpath if current_pythonpath else "")
    environment.setdefault("PYTHONIOENCODING", "utf-8")
    environment.setdefault("PYTHONUTF8", "1")
    return environment


def run_backend_process(
    command: Sequence[str],
    cwd: Path,
    environment: Mapping[str, str],
    log_path: Path,
) -> tuple[int, float]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    with log_path.open("a", encoding="utf-8", errors="replace") as log:
        log.write(f"\n[{datetime.now().astimezone().isoformat(timespec='seconds')}] CMD: {list(command)!r}\n")
        log.write(f"[{datetime.now().astimezone().isoformat(timespec='seconds')}] CWD: {cwd}\n")
        log.flush()
        try:
            proc = subprocess.Popen(
                list(command),
                cwd=str(cwd),
                env=dict(environment),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                shell=False,
            )
        except OSError as exc:
            log.write(f"[launcher error] {exc}\n")
            raise PipelineError(f"Không khởi chạy được MuseTalk backend: {exc}; log: {log_path}") from exc
        assert proc.stdout is not None
        try:
            try:
                for line in iter(proc.stdout.readline, ""):
                    sys.stdout.write(line)
                    sys.stdout.flush()
                    log.write(line)
                    log.flush()
                return_code = proc.wait()
            except KeyboardInterrupt:
                log.write("\n[interrupted by user; terminating MuseTalk backend]\n")
                log.flush()
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                raise
        finally:
            proc.stdout.close()
        elapsed = time.monotonic() - started
        log.write(f"\n[backend exit={return_code}; elapsed={elapsed:.2f}s]\n")
        log.flush()
    return return_code, elapsed


def verify_rendered_output(
    path: Path,
    expected_video: MediaInfo,
    expected_fps: int,
    expected_duration: float,
    ffprobe: str,
) -> MediaInfo:
    if not path.is_file() or path.stat().st_size <= 1000:
        raise PipelineError(f"MuseTalk không tạo video đầu ra hợp lệ tại {path}; file thiếu hoặc rỗng.")
    info = probe_media(path, ffprobe)
    if not info.has_video or not info.has_audio:
        raise PipelineError(f"Video đầu ra phải có cả hình và tiếng; ffprobe báo {path}: {info}")
    if info.video_duration <= 0 or info.audio_duration <= 0:
        raise PipelineError(f"ffprobe không trả thời lượng riêng cho cả hai luồng của video đầu ra: {path}")
    if (info.width, info.height) != (expected_video.width, expected_video.height):
        raise PipelineError(
            f"Sai độ phân giải đầu ra: {info.width}x{info.height}; mong đợi "
            f"{expected_video.width}x{expected_video.height}."
        )
    if abs(info.fps - expected_fps) > 0.10:
        raise PipelineError(f"Sai FPS đầu ra: {info.fps:.3f}; mong đợi {expected_fps} FPS.")
    tolerance = max(0.15, 1.5 / expected_fps)
    video_duration = info.video_duration
    audio_duration = info.audio_duration
    if abs(video_duration - expected_duration) > tolerance:
        raise PipelineError(
            f"Sai thời lượng luồng video đầu ra: {video_duration:.3f}s; mong đợi khoảng {expected_duration:.3f}s "
            f"(dung sai {tolerance:.3f}s)."
        )
    if abs(audio_duration - expected_duration) > tolerance:
        raise PipelineError(
            f"Sai thời lượng luồng audio đầu ra: {audio_duration:.3f}s; mong đợi khoảng {expected_duration:.3f}s "
            f"(dung sai {tolerance:.3f}s)."
        )
    return info


def atomic_copy_output(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".musetalk_verified_", suffix=".mp4", dir=str(destination.parent))
    os.close(fd)
    temp = Path(temp_name)
    try:
        shutil.copyfile(source, temp)
        if not temp.is_file() or temp.stat().st_size <= 1000:
            raise PipelineError("Bản sao video tạm không hợp lệ; output cũ được giữ nguyên.")
        os.replace(temp, destination)
    except Exception:
        try:
            temp.unlink()
        except OSError:
            pass
        raise


def _make_stage(cache_dir: Path, key: str) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    stage = cache_dir / (".stage_" + key[:12] + "_" + uuid.uuid4().hex[:10])
    stage.mkdir()
    (stage / "input").mkdir()
    (stage / "jobs").mkdir()
    return stage


def _write_run_manifest(
    job_dir: Path,
    audio_source: Path,
    audio_duration: float,
    audio_info: MediaInfo,
    output: Path | None,
    cache_state: str,
    normalization_seconds: float,
    backend_seconds: float,
    motion_metadata: Mapping[str, object] | None = None,
) -> None:
    payload = {
        "audio_source": str(audio_source),
        "normalized_audio_duration_seconds": round(audio_duration, 6),
        "cache_state": cache_state,
        "audio_normalization_seconds": round(normalization_seconds, 3),
        "backend_process_seconds": round(backend_seconds, 3),
        "model_weights_reloaded_for_this_process": True,
        "normalized_audio": {
            "sample_rate": audio_info.sample_rate,
            "channels": audio_info.channels,
            "codec": audio_info.audio_codec,
        },
        "output": str(output) if output else None,
        "recorded_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        **dict(motion_metadata or {}),
    }
    _write_json_atomic(job_dir / "render_manifest.json", payload)


def _cache_lock(cache_dir: Path, key: str):
    class Lock:
        def __init__(self) -> None:
            self.path = cache_dir / ("." + key[:32] + ".lock")
            self.fd: int | None = None

        def __enter__(self):
            cache_dir.mkdir(parents=True, exist_ok=True)
            try:
                self.fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(self.fd, f"pid={os.getpid()} started={time.time()}\n".encode("ascii"))
            except FileExistsError as exc:
                raise PipelineError(f"Đang có tiến trình khác dùng cache này hoặc còn lock cũ: {self.path}") from exc
            return self

        def __exit__(self, exc_type, exc, traceback) -> None:
            if self.fd is not None:
                os.close(self.fd)
            try:
                self.path.unlink()
            except OSError:
                pass
    return Lock()


def _promote_stage(stage: Path, target: Path) -> None:
    if target.exists():
        raise PipelineError(f"Cache đích xuất hiện trong lúc chạy; giữ nguyên cả hai thư mục: {target}")
    os.replace(stage, target)


def run_pipeline(
    action: str,
    base_video: Path,
    audio: Path,
    duration: float,
    output: Path,
    cache_dir: Path,
    fps: int = 25,
    batch_size: int = 2,
    musetalk_dir: str | Path | None = None,
    musetalk_python: str | Path | None = None,
    ffmpeg_override: str | None = None,
    ffprobe_override: str | None = None,
    log_path: Path | None = None,
    parsing_mode: str = "jaw",
    extra_margin: int = 10,
    left_cheek_width: int = 90,
    right_cheek_width: int = 90,
    audio_padding_left: int = 2,
    audio_padding_right: int = 2,
    backend_runner: Callable[[Sequence[str], Path, Mapping[str, str], Path], tuple[int, float]] | None = None,
    motion_policy: str = "error",
    bbox_shift: int = 0,
) -> dict[str, object]:
    if action not in ("dry-run", "prepare", "run"):
        raise PipelineError(f"Action không hợp lệ: {action}")
    if motion_policy not in {"error", "pingpong"}:
        raise PipelineError("--motion-policy chỉ nhận error hoặc pingpong.")
    if fps < 1 or batch_size < 1 or not math.isfinite(duration) or duration <= 0:
        raise PipelineError("fps, batch-size và duration phải lớn hơn 0.")
    if not isinstance(bbox_shift, int) or not -20 <= bbox_shift <= 20:
        raise PipelineError("bbox-shift phải là số nguyên trong [-20, 20]; kiểm tra range do upstream báo trước khi chọn.")
    if audio_padding_left < 0 or audio_padding_right < 0 or audio_padding_left + audio_padding_right != 4:
        raise PipelineError("MuseTalk v1.5 cần tổng audio padding trái + phải = 4, mỗi giá trị không âm (mặc định 2 + 2).")
    base_video = base_video.resolve()
    audio = audio.resolve()
    cache_dir = cache_dir.resolve()
    validate_safe_cache_root(cache_dir)
    if action in ("dry-run", "run") and not audio.is_file():
        raise PipelineError(f"Không tìm thấy audio: {audio}")
    if not base_video.is_file():
        raise PipelineError(f"Không tìm thấy video motion-base: {base_video}")

    paths = discover_musetalk_paths(musetalk_dir, musetalk_python)
    validate_safe_musetalk_root(paths.root)
    validate_musetalk_install(paths)
    validate_bbox_shift_support(paths.inference_script, bbox_shift)
    if motion_policy == "pingpong":
        validate_pingpong_support(paths.inference_script)
    protected_roots = (
        cache_dir,
        paths.root / "results" / "v15" / "avatars",
    )
    output = validate_output_target(output, (base_video, audio), protected_roots)
    ffmpeg, ffprobe = find_ffmpeg_pair(ffmpeg_override, ffprobe_override)
    base_info = probe_media(base_video, ffprobe)
    validate_base_media(base_info, fps)
    source_video_duration = base_info.video_duration or base_info.duration

    audio_source_info: MediaInfo | None = None
    effective_audio_duration = 0.0
    if action in ("dry-run", "run"):
        audio_source_info = probe_media(audio, ffprobe)
        if not audio_source_info.has_audio:
            raise PipelineError(f"Audio không có luồng tiếng: {audio}")
        source_audio_duration = audio_source_info.audio_duration or audio_source_info.duration
        if not math.isfinite(source_audio_duration) or source_audio_duration <= 0:
            raise PipelineError(f"Không đọc được thời lượng luồng audio: {audio}")
        effective_audio_duration = min(duration, source_audio_duration)
        validate_motion_coverage(effective_audio_duration, source_video_duration, fps, motion_policy)

    inputs = build_fingerprint_inputs(
        base_video, base_info, fps, paths, parsing_mode, extra_margin,
        left_cheek_width, right_cheek_width, bbox_shift,
    )
    key = fingerprint_key(inputs)
    target = cache_target(cache_dir, key)
    # Upstream stores under cwd/results/v15/avatars/<YAML-key>; cwd is MuseTalk itself.
    avatar_id = "avatar_" + key[:16]
    lip_settings = {"bbox_shift": bbox_shift, "parsing_mode": parsing_mode,
                    "audio_padding_left": audio_padding_left, "audio_padding_right": audio_padding_right,
                    "extra_margin": extra_margin}
    print(f"Base video: {base_video} ({base_info.width}x{base_info.height}, {base_info.fps:.3f} FPS, {base_info.duration:.3f}s)")
    print(f"MuseTalk: {paths.root} | Python: {paths.python}")
    print(f"Avatar cache key: {key[:16]} | action={action}")
    if action in ("dry-run", "run"):
        print(f"Audio effective: {effective_audio_duration:.3f}s (requested cap {duration:.3f}s), 16kHz mono PCM after normalization")
        motion_metadata = build_motion_metadata(effective_audio_duration, source_video_duration, motion_policy)
        motion_metadata["lip_sync_settings"] = lip_settings
        if motion_policy == "pingpong":
            print(
                "Coverage check: PASS (ping-pong explicitly enabled; nominal full motion cycle "
                f"{motion_metadata['nominal_full_motion_cycle_seconds']:.3f}s, "
                f"about {motion_metadata['nominal_motion_cycles']} cycle(s), "
                f"{motion_metadata['nominal_motion_repeats']} repeat(s); last cycle may be partial)."
            )
        else:
            print(f"Coverage check: PASS ({effective_audio_duration:.3f}s <= {source_video_duration:.3f}s)")
    else:
        motion_metadata = build_motion_metadata(0.0, source_video_duration, motion_policy)
        motion_metadata["lip_sync_settings"] = lip_settings
    print(f"Motion policy: {motion_policy} | source motion {source_video_duration:.3f}s")
    print("Dtype: upstream realtime_inference.py casts VAE/UNet/PE to FP16; no CLI float16 flag is sent.")

    if action == "dry-run":
        manifest = read_cache_manifest(target, key, inputs, avatar_id, paths.root)
        print("Dry-run hoàn tất; không nạp Torch/CUDA và không chạy backend.")
        print("Avatar cache: hợp lệ, sẽ tái sử dụng." if manifest else "Avatar cache: chưa có; lệnh prepare/run sẽ tạo cache.")
        return {
            "cache_hit": manifest is not None,
            "cache_path": target,
            "audio_duration": effective_audio_duration,
            **motion_metadata,
        }

    if backend_runner is None:
        backend_runner = run_backend_process
    effective_log = log_path or (PROJECT_ROOT / "output" / "cached_musetalk" / "logs" / f"{action}_{datetime.now():%Y%m%d_%H%M%S}.log")
    environment = build_backend_environment(ffmpeg, musetalk_root=paths.root)
    with _cache_lock(cache_dir, key):
        cached = read_cache_manifest(target, key, inputs, avatar_id, paths.root)
        cache_hit = cached is not None
        if action == "prepare" and cache_hit:
            print(f"Avatar cache đã sẵn sàng, giữ nguyên và tái sử dụng: {target}")
            return {"cache_hit": True, "cache_path": target, "prepared_seconds": 0.0}
        if action == "run" and cache_hit:
            job_id = "run_" + uuid.uuid4().hex[:12]
            job_dir = target / "jobs" / job_id
            job_dir.mkdir(parents=True, exist_ok=False)
            normalized_audio = job_dir / "audio_16k_mono.wav"
            normalization_started = time.monotonic()
            actual_audio_duration, normalized_info = normalize_audio(audio, normalized_audio, duration, ffmpeg, ffprobe)
            normalization_seconds = time.monotonic() - normalization_started
            validate_motion_coverage(actual_audio_duration, source_video_duration, fps, motion_policy)
            actual_motion_metadata = build_motion_metadata(actual_audio_duration, source_video_duration, motion_policy)
            actual_motion_metadata["lip_sync_settings"] = lip_settings
            output_name = "render_" + uuid.uuid4().hex[:12]
            config_path = job_dir / "realtime.yaml"
            safe_base_copy = target / "input" / "base_video.mp4"
            expected_base_hash = inputs["base_video"]["sha256"]
            if not safe_base_copy.is_file() or sha256_file(safe_base_copy) != expected_base_hash:
                raise PipelineError(f"Cache manifest hợp lệ nhưng bản video nền nội bộ thiếu hoặc sai SHA-256: {safe_base_copy}")
            write_inference_config(config_path, avatar_id, safe_base_copy, False, normalized_audio, output_name, bbox_shift)
            command = build_backend_command(
                paths, config_path, output_name, batch_size, fps, parsing_mode,
                extra_margin, left_cheek_width, right_cheek_width, audio_padding_left, audio_padding_right,
                bbox_shift,
            )
            _log_status(effective_log, f"Avatar cache: REUSE ({target})")
            _log_status(effective_log, f"Audio normalization: {normalization_seconds:.2f}s; upstream model weights will load again.")
            rc, elapsed = backend_runner(command, paths.root, environment, effective_log)
            _write_run_manifest(
                job_dir, audio, actual_audio_duration, normalized_info, output, "REUSE",
                normalization_seconds, elapsed, actual_motion_metadata,
            )
            if rc != 0:
                raise PipelineError(f"MuseTalk thoát với mã {rc}; log: {effective_log}; cache vẫn được giữ.")
            generated = avatar_dir_for(paths.root, avatar_id) / "vid_output" / (output_name + ".mp4")
            output_info = verify_rendered_output(generated, base_info, fps, actual_audio_duration, ffprobe)
            atomic_copy_output(generated, output)
            print(f"Render thành công: {output} ({output_info.width}x{output_info.height}, {output_info.duration:.3f}s)")
            _log_status(effective_log, f"Backend process: {elapsed:.2f}s; avatar preprocessing cache: REUSE; model weights reloaded.")
            return {
                "cache_hit": True,
                "cache_path": target,
                "output": output,
                "backend_seconds": elapsed,
                "audio_duration": actual_audio_duration,
                **actual_motion_metadata,
            }

        # Cold prepare, or cold run. Staging keeps an existing cache untouched on failure.
        stage = _make_stage(cache_dir, key)
        safe_base_copy = stage / "input" / "base_video.mp4"
        shutil.copy2(base_video, safe_base_copy)
        if not is_safe_upstream_path(stage) or not is_safe_upstream_path(safe_base_copy):
            raise PipelineError(f"Tên đường dẫn staging không an toàn cho upstream shell: {stage}")
        job_id = "prepare_" + uuid.uuid4().hex[:12]
        job_dir = stage / "jobs" / job_id
        job_dir.mkdir()
        normalized_audio: Path | None = None
        actual_audio_duration = 0.0
        normalized_info: MediaInfo | None = None
        output_name: str | None = None
        if action == "run":
            normalized_audio = job_dir / "audio_16k_mono.wav"
            normalization_started = time.monotonic()
            actual_audio_duration, normalized_info = normalize_audio(audio, normalized_audio, duration, ffmpeg, ffprobe)
            normalization_seconds = time.monotonic() - normalization_started
            validate_motion_coverage(actual_audio_duration, source_video_duration, fps, motion_policy)
            actual_motion_metadata = build_motion_metadata(actual_audio_duration, source_video_duration, motion_policy)
            actual_motion_metadata["lip_sync_settings"] = lip_settings
            output_name = "render_" + uuid.uuid4().hex[:12]
        config_path = job_dir / "realtime.yaml"
        write_inference_config(config_path, avatar_id, safe_base_copy, True, normalized_audio, output_name, bbox_shift)
        command = build_backend_command(
            paths, config_path, output_name, batch_size, fps, parsing_mode,
            extra_margin, left_cheek_width, right_cheek_width, audio_padding_left, audio_padding_right,
            bbox_shift,
        )
        print("Bước chuẩn bị avatar chạy bằng MuseTalk; thời gian đầu tiên sẽ dài hơn các lần tái sử dụng.")
        _log_status(effective_log, f"Avatar cache: CREATE ({stage} -> {target})")
        if action == "run":
            _log_status(effective_log, f"Audio normalization: {normalization_seconds:.2f}s.")
        started = time.monotonic()
        rc, backend_elapsed = backend_runner(command, paths.root, environment, effective_log)
        prepared_assets_valid = False
        prepared_assets_error: str | None = None
        try:
            validate_avatar_cache_files(paths.root, avatar_id, bbox_shift)
            prepared_assets_valid = True
        except PipelineError as exc:
            prepared_assets_error = str(exc)
        if prepared_assets_valid:
            _write_cache_manifest(stage, key, inputs, avatar_id, paths.root)
            _promote_stage(stage, target)
            print(f"Avatar cache đã được lưu: {target}")
        if rc != 0:
            raise PipelineError(
                f"MuseTalk thoát với mã {rc}; log: {effective_log}. "
                + ("Avatar cache đã được lưu nếu preprocessing hoàn tất." if prepared_assets_valid else f"Staging được giữ để kiểm tra: {stage}")
            )
        if not prepared_assets_valid:
            raise PipelineError(
                "Backend báo thành công nhưng cache avatar không vượt kiểm tra; "
                f"chi tiết: {prepared_assets_error or 'không rõ nguyên nhân'}; staging được giữ: {stage}"
            )
        if action == "prepare":
            elapsed = time.monotonic() - started
            _log_status(effective_log, f"Prepare backend/cache creation: {elapsed:.2f}s; no MP4 rendered; model process is not warm-cached.")
            return {"cache_hit": False, "cache_path": target, "prepared_seconds": elapsed}
        assert output_name is not None and normalized_info is not None
        generated = avatar_dir_for(paths.root, avatar_id) / "vid_output" / (output_name + ".mp4")
        _write_run_manifest(
            target / "jobs" / job_id, audio, actual_audio_duration, normalized_info, output,
            "CREATE", normalization_seconds, backend_elapsed, actual_motion_metadata,
        )
        output_info = verify_rendered_output(generated, base_info, fps, actual_audio_duration, ffprobe)
        atomic_copy_output(generated, output)
        elapsed = time.monotonic() - started
        print(f"Render thành công: {output} ({output_info.width}x{output_info.height}, {output_info.duration:.3f}s)")
        _log_status(effective_log, f"Backend process: {backend_elapsed:.2f}s; cache: CREATE; model weights loaded in this process.")
        return {
            "cache_hit": False,
            "cache_path": target,
            "output": output,
            "backend_seconds": backend_elapsed,
            "elapsed_seconds": elapsed,
            "audio_duration": actual_audio_duration,
            **actual_motion_metadata,
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Test MuseTalk v1.5 trên motion-base; tạo/tái sử dụng preprocessing avatar cache.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("action", choices=("dry-run", "prepare", "run"), help="dry-run kiểm tra, prepare tạo cache, run render MP4")
    parser.add_argument("--base-video", required=True, help="Motion-base đã được duyệt; video phải đủ dài cho đoạn audio")
    parser.add_argument("--audio", default=str(PROJECT_ROOT / "sample_script_1min.mp3"), help="Audio test; run sẽ trim tới --duration")
    parser.add_argument("--duration", type=float, default=3.2, help="Số giây tối đa lấy từ đầu audio")
    parser.add_argument("--motion-policy", choices=("error", "pingpong"), default="error", help="Cho phép lặp ping-pong upstream cho audio dài hơn base")
    parser.add_argument("--output", default=str(PROJECT_ROOT / "output" / "cached_musetalk" / "musetalk_test.mp4"), help="File MP4 đầu ra (được thay thế nguyên tử sau khi kiểm tra)")
    parser.add_argument("--cache-dir", default=str(PROJECT_ROOT / "output" / "cached_musetalk" / "cache"), help="Cache root ASCII không có khoảng trắng; Windows nên dùng C:\\vcs_cache")
    parser.add_argument("--fps", type=int, default=25)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--bbox-shift", type=int, default=0, help="Chỉnh face crop theo pixel native; mỗi giá trị có avatar cache riêng, mặc định giữ 0.")
    parser.add_argument("--musetalk-dir", help="Override thư mục MuseTalk")
    parser.add_argument("--musetalk-python", help="Override python.exe trong môi trường MuseTalk")
    parser.add_argument("--ffmpeg", help="Override đường dẫn ffmpeg")
    parser.add_argument("--ffprobe", help="Override đường dẫn ffprobe")
    parser.add_argument("--log", help="File log backend; mặc định output/cached_musetalk/logs/<action>_<timestamp>.log")
    parser.add_argument("--parsing-mode", default="jaw", choices=("jaw", "raw"))
    parser.add_argument("--extra-margin", type=int, default=10)
    parser.add_argument("--left-cheek-width", type=int, default=90)
    parser.add_argument("--right-cheek-width", type=int, default=90)
    parser.add_argument("--audio-padding-left", type=int, default=2)
    parser.add_argument("--audio-padding-right", type=int, default=2)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = run_pipeline(
            action=args.action,
            base_video=_resolve_project_path(args.base_video),
            audio=_resolve_project_path(args.audio),
            duration=args.duration,
            output=_resolve_project_path(args.output),
            cache_dir=_resolve_project_path(args.cache_dir),
            fps=args.fps,
            batch_size=args.batch_size,
            musetalk_dir=args.musetalk_dir,
            musetalk_python=args.musetalk_python,
            ffmpeg_override=args.ffmpeg,
            ffprobe_override=args.ffprobe,
            log_path=_resolve_project_path(args.log) if args.log else None,
            parsing_mode=args.parsing_mode,
            extra_margin=args.extra_margin,
            left_cheek_width=args.left_cheek_width,
            right_cheek_width=args.right_cheek_width,
            audio_padding_left=args.audio_padding_left,
            audio_padding_right=args.audio_padding_right,
            motion_policy=args.motion_policy,
            bbox_shift=args.bbox_shift,
        )
        print(json.dumps({"status": "ok", **{key: str(value) if isinstance(value, Path) else value for key, value in result.items()}}, ensure_ascii=False))
        return 0
    except PipelineError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nĐã nhận Ctrl+C; cache staging được giữ để kiểm tra, output cũ không bị thay thế.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
