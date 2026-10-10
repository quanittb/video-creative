#!/usr/bin/env python3
"""Windows-friendly, standard-library controller for the isolated EchoMimic V3 Flash test."""

from __future__ import annotations

import argparse
import datetime as _datetime
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


CODE_PIN = "7e89489ca51c0d008fc1963ec6c03fc5bd0b9397"
FLASH_REPO = "BadToBest/EchoMimicV3"
FLASH_REVISION = "311e176905a8c4c24b240b530488fe636ce4d249"
BASE_REPO = "alibaba-pai/Wan2.1-Fun-V1.1-1.3B-InP"
BASE_REVISION = "fc913c34361f4ec879e2f9c78b4f11ae50a937d1"
WAV2VEC_REPO = "TencentGameMate/chinese-wav2vec2-base"
WAV2VEC_REVISION = "3991242c806928916fff4a8c0e4f76acf661b743"
FPS = 25
# Kept for compatibility with scripts that imported the original F1 default.
DEFAULT_DURATION = 3.24
DEFAULT_PROMPT = (
    "A photorealistic person matching the source image speaks calmly to the camera. Keep the same "
    "face, hair, clothes and visible surroundings as the source. Natural speech-synchronized mouth "
    "movement. Keep the head upright, centered and facing the camera; use only a tiny occasional nod, "
    "with no repeated left-right turns, side-to-side sway or rocking. Subtle breathing may move the "
    "shoulders and upper torso modestly while the body stays centered. Natural blinking, steady camera "
    "and consistent framing. Restrained gestures; no exaggerated arm or hand motion, keep hands outside the crop."
)
NEGATIVE_PROMPT = (
    "Gesture is bad. Gesture is unclear. Strange and twisted hands. Bad hands. Bad fingers. "
    "Unclear and blurry hands. Unclear gestures, broken hands, fused fingers. Face identity change, "
    "deformed face, warped collar, clothing flicker, changing hairstyle, unstable background, "
    "repeated left-right head turns, side-to-side head sway, rocking head, exaggerated neck motion. 手指融合，"
)
NEUTRAL_PROMPT = (
    "A photorealistic person matching the source image rests calmly, upright, centered and facing "
    "the camera throughout. Keep the same face, hair, clothes and surroundings. Lips stay naturally "
    "closed and relaxed; no talking, chewing or open-mouth expression. Keep the head and neck mostly "
    "still, allowing only a tiny occasional nod and natural blinking. No repeated left-right head turns, "
    "side-to-side sway or rocking. Quiet breathing may create modest shoulder and upper-torso motion "
    "while the body remains centered. Steady camera, consistent framing, restrained gestures, hands "
    "outside the crop."
)


@dataclass(frozen=True)
class Profile:
    name: str
    width: int
    height: int
    seed: int
    frames: int = 81
    fps: int = FPS
    steps: int = 8
    guidance_scale: float = 6.0
    audio_guidance_scale: float = 3.0
    shift: float = 5.0

    @property
    def max_duration_seconds(self) -> float:
        return self.frames / float(self.fps)


PROFILES: Dict[str, Profile] = {
    "F1": Profile("F1", 384, 480, 42),
    "F2": Profile("F2", 512, 640, 42),
    "F3": Profile("F3", 512, 640, 43),
    "F10": Profile("F10", 384, 480, 42, frames=129),
    "F20": Profile("F20", 384, 480, 42, frames=249),
    "A10": Profile("A10", 512, 640, 42, frames=129),
    "A10HQ": Profile("A10HQ", 640, 800, 42, frames=129),
}


@dataclass(frozen=True)
class Asset:
    repo: str
    revision: str
    filename: str
    size: int
    sha256: str
    relative_path: str


ASSETS: Tuple[Asset, ...] = (
    Asset(BASE_REPO, BASE_REVISION, "Wan2.1_VAE.pth", 507609880,
          "38071ab59bd94681c686fa51d75a1968f64e470262043be31f7a094e442fd981",
          "models/Wan2.1-Fun-V1.1-1.3B-InP/Wan2.1_VAE.pth"),
    Asset(BASE_REPO, BASE_REVISION, "google/umt5-xxl/special_tokens_map.json", 6623,
          "7b8a9f5040adb67b5805abdfd42c1f8d0f3d0e711f10726580eb3789cd0ad61d",
          "models/Wan2.1-Fun-V1.1-1.3B-InP/google/umt5-xxl/special_tokens_map.json"),
    Asset(BASE_REPO, BASE_REVISION, "google/umt5-xxl/spiece.model", 4548313,
          "e3909a67b780650b35cf529ac782ad2b6b26e6d1f849d3fbb6a872905f452458",
          "models/Wan2.1-Fun-V1.1-1.3B-InP/google/umt5-xxl/spiece.model"),
    Asset(BASE_REPO, BASE_REVISION, "google/umt5-xxl/tokenizer.json", 16837417,
          "6e197b4d3dbd71da14b4eb255f4fa91c9c1f2068b20a2de2472967ca3d22602b",
          "models/Wan2.1-Fun-V1.1-1.3B-InP/google/umt5-xxl/tokenizer.json"),
    Asset(BASE_REPO, BASE_REVISION, "google/umt5-xxl/tokenizer_config.json", 61728,
          "ed9a3a8b0faa71a70a32847e0435fe036e6e112d4df4edb7bb48a921e344dc05",
          "models/Wan2.1-Fun-V1.1-1.3B-InP/google/umt5-xxl/tokenizer_config.json"),
    Asset(BASE_REPO, BASE_REVISION, "models_clip_open-clip-xlm-roberta-large-vit-huge-14.pth", 4772359047,
          "628c9998b613391f193eb67ff68da9667d75f492911e4eb3decf23460a158c38",
          "models/Wan2.1-Fun-V1.1-1.3B-InP/models_clip_open-clip-xlm-roberta-large-vit-huge-14.pth"),
    Asset(BASE_REPO, BASE_REVISION, "models_t5_umt5-xxl-enc-bf16.pth", 11361920418,
          "7cace0da2b446bbbbc57d031ab6cf163a3d59b366da94e5afe36745b746fd81d",
          "models/Wan2.1-Fun-V1.1-1.3B-InP/models_t5_umt5-xxl-enc-bf16.pth"),
    Asset(FLASH_REPO, FLASH_REVISION, "echomimicv3-flash-pro/config.json", 577,
          "abe85b8379e2591902f53f698f7ebd711bd6ba4811c796116b3d3c559d2d59ea",
          "models/echomimicv3-flash-pro/config.json"),
    Asset(FLASH_REPO, FLASH_REVISION, "echomimicv3-flash-pro/diffusion_pytorch_model.safetensors", 3727671120,
          "5ebdbb2fc709108bf2a1728fd92eb2874804e4bc0324e92a2cd55425968c85a4",
          "models/echomimicv3-flash-pro/diffusion_pytorch_model.safetensors"),
    Asset(WAV2VEC_REPO, WAV2VEC_REVISION, "config.json", 1951,
          "dc2cd2f989104b9510ce9e43a343a6f1fe55aa60baa1fcfca0c5908e6590b8b6",
          "models/chinese-wav2vec2-base/config.json"),
    Asset(WAV2VEC_REPO, WAV2VEC_REVISION, "preprocessor_config.json", 160,
          "c1707926644954affc391ab09ccfaf470ccd80af218d11350991090711441c09",
          "models/chinese-wav2vec2-base/preprocessor_config.json"),
    Asset(WAV2VEC_REPO, WAV2VEC_REVISION, "pytorch_model.bin", 380261837,
          "be2da40c9e7ae26bfc904a3ed79ebb9e8f060bec6dba85d6a6ae86114bc38901",
          "models/chinese-wav2vec2-base/pytorch_model.bin"),
)


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_echo_root() -> Path:
    user_profile = os.environ.get("USERPROFILE") or str(Path.home())
    return Path(user_profile) / "Downloads" / "EchoMimicV3"


def default_image() -> Path:
    return project_root() / "assets" / "characters" / "nhanvatnam" / "asian_male_office_1080p.png"


def default_audio() -> Path:
    return project_root() / "sample_script_1min.mp3"


def hash_file(path: Path, chunk_size: int = 4 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def get_asset_path(echo_root: Path, asset: Asset) -> Path:
    return echo_root / asset.relative_path


def missing_model_assets(echo_root: Path, verify_sha: bool = False) -> List[str]:
    missing: List[str] = []
    for asset in ASSETS:
        path = get_asset_path(echo_root, asset)
        if not path.is_file() or path.stat().st_size != asset.size:
            missing.append(str(path))
        elif verify_sha and hash_file(path) != asset.sha256:
            missing.append(str(path) + " (SHA-256 không khớp)")
    return missing


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    with temp.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
    os.replace(str(temp), str(path))


def parse_fraction(value: str) -> float:
    if "/" in value:
        numerator, denominator = value.split("/", 1)
        den = float(denominator)
        if den == 0:
            return 0.0
        return float(numerator) / den
    return float(value)


def probe_media(path: Path, ffprobe: str = "ffprobe") -> Dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError("Không tìm thấy media: {}".format(path))
    result = subprocess.run(
        [ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("ffprobe lỗi với '{}': {}".format(path, result.stderr.strip()))
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("ffprobe trả về JSON không hợp lệ cho {}".format(path)) from error


def stream_duration(stream: Mapping[str, Any], fallback: float = 0.0) -> float:
    value = stream.get("duration")
    if value is not None:
        try:
            return float(value)
        except (TypeError, ValueError):
            pass
    return fallback


def summarize_media(data: Mapping[str, Any]) -> Dict[str, Any]:
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if video is None and audio is None:
        raise ValueError("Không tìm thấy stream video hoặc audio hợp lệ.")
    format_duration = float((data.get("format") or {}).get("duration") or 0.0)
    return {
        "video": None if video is None else {
            "width": int(video.get("width", 0)),
            "height": int(video.get("height", 0)),
            "fps": parse_fraction(str(video.get("avg_frame_rate") or video.get("r_frame_rate") or "0/1")),
            "frames": int(video["nb_frames"]) if str(video.get("nb_frames", "")).isdigit() else None,
            "duration": stream_duration(video, format_duration),
            "codec": video.get("codec_name"),
        },
        "audio": None if audio is None else {
            "duration": stream_duration(audio, format_duration),
            "sample_rate": int(audio.get("sample_rate", 0) or 0),
            "channels": int(audio.get("channels", 0) or 0),
            "codec": audio.get("codec_name"),
        },
        "format_duration": format_duration,
    }


def effective_frames(duration_seconds: float, profile: Profile) -> int:
    if not math.isfinite(duration_seconds) or duration_seconds <= 0:
        raise ValueError("Thời lượng phải là số hữu hạn lớn hơn 0.")
    max_duration = profile.max_duration_seconds
    if duration_seconds > max_duration + 1e-9:
        raise ValueError(
            "Thời lượng {:.3f}s vượt giới hạn profile {} ({:.3f}s, {} frame). "
            "Hãy chọn profile dài hơn; không tự cắt ngầm.".format(
                duration_seconds, profile.name, max_duration, profile.frames
            )
        )
    requested = min(int(duration_seconds * profile.fps + 1e-9), profile.frames)
    frames = ((requested - 1) // 4) * 4 + 1 if requested > 1 else 1
    if frames < 5:
        raise ValueError("Thời lượng quá ngắn; cần ít nhất 5 frame để mô hình tạo chuyển động.")
    return frames


def profile_duration(profile: Profile, requested_duration: Optional[float]) -> float:
    """Use each profile's full temporal window when --duration is omitted."""
    return profile.max_duration_seconds if requested_duration is None else requested_duration


def print_profile_window(profile: Profile, frames: int) -> None:
    forward_seconds = audio_video_duration(frames, profile.fps)
    print(
        "Motion base Echo: {:.3f}s đi thuận ({} frame); nếu MuseTalk dùng pingpong, "
        "chu kỳ danh nghĩa là {:.3f}s.".format(forward_seconds, frames, 2.0 * forward_seconds)
    )


def audio_video_duration(frames: int, fps: int = FPS) -> float:
    return frames / float(fps)


def validate_input_media(
    image_path: Path,
    audio_path: Path,
    profile: Profile,
    requested_duration: float,
    ffprobe: str = "ffprobe",
) -> Dict[str, Any]:
    if not image_path.is_file():
        raise FileNotFoundError("Không tìm thấy ảnh đầu vào: {}".format(image_path))
    if image_path.stat().st_size <= 0:
        raise ValueError("Ảnh đầu vào đang rỗng: {}".format(image_path))
    image_info = probe_media(image_path, ffprobe)
    image_video = next((s for s in image_info.get("streams", []) if s.get("codec_type") == "video"), None)
    if image_video is None:
        raise ValueError("Ảnh đầu vào không giải mã được thành ảnh tĩnh.")
    audio_info = summarize_media(probe_media(audio_path, ffprobe))
    audio = audio_info["audio"]
    if audio is None:
        raise ValueError("File thoại không có audio stream.")
    frames = effective_frames(requested_duration, profile)
    if frames < 13:
        raise ValueError("Thời lượng test tối thiểu là 13 frame (0,52s) để chuẩn hóa loudness ổn định.")
    effective_seconds = audio_video_duration(frames, profile.fps)
    if audio["duration"] + 0.02 < effective_seconds:
        raise ValueError(
            "Audio chỉ dài {:.3f}s nhưng test cần {:.3f}s ({} frame). Hãy chọn duration ngắn hơn hoặc audio dài hơn; không tự lặp audio.".format(
                audio["duration"], effective_seconds, frames
            )
        )
    return {
        "image": {"path": str(image_path.resolve()), "width": int(image_video.get("width", 0)),
                  "height": int(image_video.get("height", 0)), "bytes": image_path.stat().st_size},
        "audio": dict(audio, path=str(audio_path.resolve()), bytes=audio_path.stat().st_size),
        "profile": asdict(profile),
        "requested_duration_seconds": requested_duration,
        "frames": frames,
        "duration_seconds": effective_seconds,
        "frames_temporal_rule": "4n+1",
    }


def resolve_python(echo_root: Path, override: Optional[str] = None) -> Path:
    value = override or os.environ.get("ECHO_FLASH_PYTHON")
    if value:
        return Path(value).expanduser().resolve()
    if os.name == "nt":
        return echo_root / "venv" / "Scripts" / "python.exe"
    return echo_root / "venv" / "bin" / "python"


def child_environment(echo_root: Path, inherited: Optional[Mapping[str, str]] = None) -> Dict[str, str]:
    env = dict(os.environ if inherited is None else inherited)
    old_pythonpath = env.get("PYTHONPATH", "")
    paths = [str(echo_root.resolve())]
    if old_pythonpath:
        paths.append(old_pythonpath)
    env["PYTHONPATH"] = os.pathsep.join(paths)
    env["PYTHONUTF8"] = "1"
    env["HF_HUB_OFFLINE"] = "1"
    env["TRANSFORMERS_OFFLINE"] = "1"
    return env


def source_checkout_status(echo_root: Path) -> Tuple[bool, str]:
    required = [echo_root / "infer_flash.py", echo_root / "config" / "config.yaml", echo_root / "src" / "pipeline_wan_fun_inpaint_audio_2512.py"]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        return False, "Thiếu source chính thức: " + ", ".join(missing)
    try:
        completed = subprocess.run(
            ["git", "-C", str(echo_root), "rev-parse", "HEAD"],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", check=False,
        )
    except FileNotFoundError:
        return False, "Không tìm thấy Git để xác minh source pin."
    commit = completed.stdout.strip()
    if completed.returncode != 0:
        return False, "Thư mục EchoMimic chưa phải Git checkout hợp lệ: {}".format(completed.stderr.strip())
    if commit != CODE_PIN:
        return False, "Sai commit source: {} (cần {}).".format(commit, CODE_PIN)
    return True, "Source chính thức đúng pin {}.".format(CODE_PIN)


def asset_url(asset: Asset) -> str:
    return "https://huggingface.co/{}/resolve/{}/{}?download=true".format(
        asset.repo, asset.revision, urllib.parse.quote(asset.filename, safe="/")
    )


def sha256_file(path: Path) -> str:
    return hash_file(path)


def download_asset(
    asset: Asset,
    destination: Path,
    overwrite: bool = False,
    opener: Any = None,
    progress: Any = print,
    progress_callback: Any = None,
) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if destination.is_file() and destination.stat().st_size == asset.size and sha256_file(destination) == asset.sha256:
            progress("Đã có file đúng SHA: {}".format(destination))
            return "reused"
        if not overwrite:
            raise ValueError("File đã tồn tại nhưng size/SHA không đúng; giữ nguyên file: {} (dùng --overwrite để tải bản xác minh mới).".format(destination))
    partial = destination.with_name(destination.name + ".part")
    current_size = partial.stat().st_size if partial.exists() else 0
    if current_size > asset.size:
        partial.unlink()
        current_size = 0
    elif current_size == asset.size:
        if sha256_file(partial) == asset.sha256:
            os.replace(str(partial), str(destination))
            progress("Đã xác minh và lưu {}".format(destination))
            if progress_callback is not None:
                progress_callback(asset.size, asset.size)
            return "downloaded"
        partial.unlink()
        current_size = 0
    request = urllib.request.Request(asset_url(asset), headers={"User-Agent": "EchoMimicV3-test-runner/1.0"})
    if current_size:
        request.add_header("Range", "bytes={}-".format(current_size))
    open_url = opener or urllib.request.urlopen
    try:
        response = open_url(request, timeout=60)
    except Exception as error:
        raise RuntimeError("Không tải được {}: {}. File .part hiện tại được giữ để tiếp tục.".format(asset.filename, error)) from error
    status = getattr(response, "status", response.getcode() if hasattr(response, "getcode") else 200)
    response_headers = getattr(response, "headers", {})
    if current_size and status == 206:
        content_range = response_headers.get("Content-Range", "")
        if not content_range.startswith("bytes {}-".format(current_size)):
            response.close()
            raise RuntimeError("Server trả Content-Range không khớp; giữ file .part để kiểm tra.")
        mode = "ab"
    else:
        current_size = 0
        mode = "wb"
    received = current_size
    last_report = 0
    try:
        with response, partial.open(mode) as stream:
            while True:
                chunk = response.read(8 * 1024 * 1024)
                if not chunk:
                    break
                received += len(chunk)
                if received > asset.size:
                    raise RuntimeError("Tải vượt quá kích thước dự kiến của {}.".format(asset.filename))
                stream.write(chunk)
                if progress_callback is not None:
                    progress_callback(received, asset.size)
                if received - last_report >= 128 * 1024 * 1024:
                    progress("  {}: {:.1f}%".format(asset.filename, received / asset.size * 100))
                    last_report = received
            stream.flush()
            os.fsync(stream.fileno())
    except Exception as error:
        raise RuntimeError("Download gián đoạn ở byte {}/{}; giữ {} để tiếp tục. {}".format(received, asset.size, partial, error)) from error
    if partial.stat().st_size != asset.size:
        raise RuntimeError("File tải chưa đủ byte ({}/{}); giữ {} để lần sau tiếp tục.".format(partial.stat().st_size, asset.size, partial))
    digest = sha256_file(partial)
    if digest != asset.sha256:
        partial.unlink(missing_ok=True)
        raise RuntimeError("SHA-256 không khớp cho {}; file .part sai đã được loại bỏ, file đích cũ vẫn nguyên.".format(asset.filename))
    os.replace(str(partial), str(destination))
    progress("Đã xác minh và lưu {}".format(destination))
    return "downloaded"


def build_job_fingerprint(
    image_path: Path,
    audio_path: Path,
    profile: Profile,
    frames: int,
    prompt: str,
    model_files: Sequence[Path],
    source_files: Sequence[Path] = (),
    mouth_mode: str = "speech",
) -> Tuple[str, Dict[str, Any]]:
    fingerprint_data = {
        "code_pin": CODE_PIN,
        "flash_revision": FLASH_REVISION,
        "base_revision": BASE_REVISION,
        "wav2vec_revision": WAV2VEC_REVISION,
        "image_sha256": hash_file(image_path),
        "audio_sha256": hash_file(audio_path),
        "profile": asdict(profile),
        "frames": frames,
        "prompt": prompt,
        "mouth_mode": mouth_mode,
        "negative_prompt": NEGATIVE_PROMPT,
        "num_inference_steps": profile.steps,
        "sampler": "Flow_Unipc",
        "memory_policy": "sequential_cpu_offload",
        "tea_cache": False,
        "riflex": False,
        "python_version": sys.version,
        "controller_sha256": hash_file(Path(__file__).resolve()),
        "backend_sha256": hash_file(Path(__file__).with_name("echo_flash_backend.py").resolve()),
        "source_sha256": {
            str(path.resolve()): hash_file(path)
            for path in sorted(source_files, key=lambda item: str(item))
        },
        "model_files": [
            {"path": str(p.resolve()), "bytes": p.stat().st_size, "mtime_ns": p.stat().st_mtime_ns}
            for p in sorted(model_files, key=lambda item: str(item))
        ],
    }
    encoded = json.dumps(fingerprint_data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest(), fingerprint_data


def validate_output_file(
    path: Path,
    expected: Mapping[str, Any],
    require_audio: bool,
    ffprobe: str = "ffprobe",
) -> Dict[str, Any]:
    if not path.is_file() or path.stat().st_size <= 0:
        raise ValueError("Output rỗng hoặc không tồn tại: {}".format(path))
    media = summarize_media(probe_media(path, ffprobe))
    video = media["video"]
    if video is None:
        raise ValueError("Output không có video stream: {}".format(path))
    for key in ("width", "height", "frames"):
        expected_value = expected.get(key)
        actual_value = video.get(key)
        if expected_value is not None and actual_value != expected_value:
            raise ValueError("Output {} sai {}: nhận {}, cần {}.".format(path, key, actual_value, expected_value))
    if abs(video["fps"] - float(expected.get("fps", FPS))) > 0.01:
        raise ValueError("Output sai FPS: nhận {}, cần {}.".format(video["fps"], expected.get("fps", FPS)))
    target_duration = float(expected.get("duration", 0.0))
    if target_duration and abs(video["duration"] - target_duration) > 0.08:
        raise ValueError("Thời lượng video lệch: nhận {:.3f}s, cần {:.3f}s.".format(video["duration"], target_duration))
    audio = media["audio"]
    if require_audio and audio is None:
        raise ValueError("Preview không có audio stream: {}".format(path))
    if not require_audio and audio is not None:
        raise ValueError("Motion base phải im lặng nhưng output có audio: {}".format(path))
    if audio is not None and target_duration and abs(audio["duration"] - target_duration) > 0.12:
        raise ValueError("Thời lượng audio lệch video: {:.3f}s so với {:.3f}s.".format(audio["duration"], target_duration))
    return {"path": str(path.resolve()), "bytes": path.stat().st_size, "sha256": hash_file(path), "media": media}


def cache_manifest_valid(directory: Path, fingerprint: str, expected: Mapping[str, Any], ffprobe: str = "ffprobe") -> bool:
    manifest = directory / "run_manifest.json"
    if not manifest.is_file():
        return False
    try:
        value = read_json(manifest)
        if value.get("fingerprint") != fingerprint or value.get("status") != "complete":
            return False
        base = directory / "motion_base.mp4"
        preview = directory / "voice_preview.mp4"
        base_record = validate_output_file(base, expected, require_audio=False, ffprobe=ffprobe)
        preview_record = validate_output_file(preview, expected, require_audio=True, ffprobe=ffprobe)
        return value.get("outputs", {}).get("motion_base", {}).get("sha256") == base_record["sha256"] and value.get("outputs", {}).get("voice_preview", {}).get("sha256") == preview_record["sha256"]
    except (OSError, ValueError, RuntimeError, KeyError, TypeError):
        return False


def tee_backend_process(command: Sequence[str], cwd: Path, env: Mapping[str, str], log_path: Path) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8", errors="replace", newline="\n") as log:
        log.write("\n=== {} ===\n$ {}\n".format(_datetime.datetime.now().isoformat(timespec="seconds"), subprocess.list2cmdline(list(command))))
        log.flush()
        process = subprocess.Popen(
            list(command), cwd=str(cwd), env=dict(env), stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=0,
        )
        assert process.stdout is not None
        try:
            for raw_line in iter(process.stdout.readline, b""):
                line = raw_line.decode("utf-8", errors="replace")
                sys.stdout.write(line)
                sys.stdout.flush()
                log.write(line)
                log.flush()
            return process.wait()
        except KeyboardInterrupt:
            message = "\n[interrupted] Ctrl+C received; terminating Echo worker and preserving work directory/log.\n"
            sys.stdout.write(message)
            sys.stdout.flush()
            log.write(message)
            log.flush()
            if process.poll() is None:
                try:
                    process.terminate()
                except OSError:
                    pass
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    try:
                        process.kill()
                    except OSError:
                        pass
                    process.wait()
            raise
        finally:
            process.stdout.close()


def ffmpeg_prepare_inputs(
    image_path: Path,
    audio_path: Path,
    work_dir: Path,
    profile: Profile,
    duration: float,
    ffmpeg: str = "ffmpeg",
    mouth_mode: str = "speech",
) -> Tuple[Path, Path]:
    work_dir.mkdir(parents=True, exist_ok=True)
    padded = work_dir / "source_padded.png"
    wav = work_dir / "speech_16k_mono.wav"
    vf = "scale={}:{}:force_original_aspect_ratio=decrease,pad={}:{}:(ow-iw)/2:(oh-ih)/2:color=black".format(
        profile.width, profile.height, profile.width, profile.height
    )
    if mouth_mode not in ("speech", "neutral"):
        raise ValueError("mouth_mode chỉ nhận speech hoặc neutral.")
    audio_command = (
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono", "-t", "{:.6f}".format(duration), "-c:a", "pcm_s16le", str(wav)]
        if mouth_mode == "neutral" else
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(audio_path), "-t", "{:.6f}".format(duration), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav)]
    )
    commands = (
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(image_path), "-frames:v", "1", "-vf", vf, str(padded)],
        audio_command,
    )
    for command in commands:
        result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", check=False)
        if result.returncode != 0:
            raise RuntimeError("FFmpeg input preparation failed: {}".format(result.stderr.strip()))
    if not padded.is_file() or not wav.is_file() or padded.stat().st_size <= 0 or wav.stat().st_size <= 0:
        raise RuntimeError("FFmpeg did not create valid padded image/audio staging files.")
    return padded, wav


def _resolve_tool(value: str) -> Optional[str]:
    candidate = shutil.which(value)
    if candidate:
        return candidate
    path = Path(value).expanduser()
    return str(path.resolve()) if path.is_file() else None


def resolve_tools(ffmpeg_override: str = "ffmpeg", ffprobe_override: str = "ffprobe") -> Tuple[str, str]:
    ffmpeg = _resolve_tool(ffmpeg_override)
    ffprobe = _resolve_tool(ffprobe_override)
    if not ffmpeg or not ffprobe:
        raise RuntimeError("Cần cài FFmpeg và thêm ffmpeg.exe, ffprobe.exe vào PATH.")
    return ffmpeg, ffprobe


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Test EchoMimic V3 Flash native Windows, isolated khỏi WanGP/MuseTalk.")
    parser.add_argument("action", choices=("check", "fetch-models", "dry-run", "run", "benchmark"))
    parser.add_argument("--echo-dir", type=Path, default=None, help="Thư mục source + venv EchoMimicV3.")
    parser.add_argument("--echo-python", default=None, help="Python của venv EchoMimicV3.")
    parser.add_argument("--image", type=Path, default=default_image())
    parser.add_argument("--audio", type=Path, default=default_audio())
    parser.add_argument("--image-b", type=Path, default=None, help="Ảnh thứ hai tùy chọn cho benchmark cùng process.")
    parser.add_argument("--profile", choices=tuple(PROFILES), default="F1")
    parser.add_argument("--duration", type=float, default=None, help="Thời lượng tối đa giây; mặc định dùng hết cửa sổ của profile, frame count làm tròn xuống dạng 4n+1.")
    parser.add_argument("--mouth-mode", choices=("speech", "neutral"), default="speech",
                        help="speech dùng audio thật để sinh chuyển động; neutral dùng conditioning im lặng, đầu gần tĩnh và không phù hợp làm motion base có chuyển động.")
    parser.add_argument("--prompt", default=None)
    parser.add_argument("--output-dir", type=Path, default=project_root() / "output" / "echo_flash")
    parser.add_argument("--overwrite", action="store_true", help="Giữ bản output cũ thành backup rồi tạo lại.")
    parser.add_argument("--verify-sha", action="store_true", help="Băm đầy đủ các model file trong bước check.")
    parser.add_argument("--runtime-only", action="store_true", help="Check source, dependencies, CUDA và FFmpeg trước khi tải model.")
    parser.add_argument("--no-output-cache", action="store_true", help="Ép chạy lại, không dùng output cùng fingerprint.")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--ffprobe", default="ffprobe")
    return parser


def check_environment(echo_root: Path, python_path: Path, verify_sha: bool, runtime_only: bool = False, ffmpeg_arg: str = "ffmpeg", ffprobe_arg: str = "ffprobe") -> int:
    ok = True
    checkout_ok, checkout_message = source_checkout_status(echo_root)
    print(checkout_message)
    ok = ok and checkout_ok
    if not python_path.is_file():
        print("Thiếu Python venv: {}".format(python_path))
        ok = False
    else:
        print("GPU Python: {}".format(python_path))
    ffmpeg, ffprobe = _resolve_tool(ffmpeg_arg), _resolve_tool(ffprobe_arg)
    print("ffmpeg: {}".format(ffmpeg or "missing"))
    print("ffprobe: {}".format(ffprobe or "missing"))
    if not ffmpeg or not ffprobe:
        ok = False
    runtime_code = 1
    if ok:
        child_env = child_environment(echo_root)
        command = [str(python_path), "-u", str(Path(__file__).with_name("echo_flash_backend.py")), "probe", "--echo-root", str(echo_root)]
        runtime_code = tee_backend_process(command, echo_root, child_env, project_root() / "output" / "echo_flash" / "logs" / "check.log")
    if runtime_code != 0:
        ok = False
    missing = missing_model_assets(echo_root, verify_sha=verify_sha)
    if missing:
        print("Thiếu/sai model assets ({}):".format(len(missing)))
        for item in missing:
            print("  - {}".format(item))
        print("Tải bằng: test_echo_flash_rtx3060.bat fetch-models")
        if not runtime_only:
            ok = False
    else:
        print("12 model files: đã có đủ size{}.".format(" và SHA-256" if verify_sha else ""))
    if runtime_only and runtime_code == 0:
        print("Runtime-only check đạt; model files có thể được tải sau bằng fetch-models.")
        return 0
    if not ok:
        print("Check chưa đạt; xem các mục trên. Lệnh check không tải model.")
        return 1
    return 0


def fetch_models(echo_root: Path, overwrite: bool) -> int:
    good, message = source_checkout_status(echo_root)
    if not good:
        print(message)
        return 1
    failed = False
    for number, asset in enumerate(ASSETS, 1):
        destination = get_asset_path(echo_root, asset)
        print("[{}/{}] {}".format(number, len(ASSETS), destination))
        try:
            download_asset(asset, destination, overwrite=overwrite)
        except Exception as error:
            print("Lỗi tải {}: {}".format(asset.filename, error))
            failed = True
            break
    if failed:
        return 1
    write_json_atomic(echo_root / "models" / "echo_flash_assets_manifest.json", {
        "flash_revision": FLASH_REVISION,
        "base_revision": BASE_REVISION,
        "wav2vec_revision": WAV2VEC_REVISION,
        "assets": [{"path": asset.relative_path, "bytes": asset.size, "sha256": asset.sha256} for asset in ASSETS],
    })
    print("Đã tải/xác minh xong {} files. Tổng tải xấp xỉ 20.77 GB.".format(len(ASSETS)))
    return 0


def dry_run(args: argparse.Namespace, echo_root: Path) -> int:
    try:
        ffmpeg, ffprobe = resolve_tools(args.ffmpeg, args.ffprobe)
        profile = PROFILES[args.profile]
        requested_duration = profile_duration(profile, args.duration)
        summary = validate_input_media(args.image, args.audio, profile, requested_duration, ffprobe=ffprobe)
    except Exception as error:
        print("Dry-run lỗi: {}".format(error))
        return 1
    ok, source_message = source_checkout_status(echo_root)
    missing = missing_model_assets(echo_root)
    print("Nguồn ảnh: {} ({}x{})".format(summary["image"]["path"], summary["image"]["width"], summary["image"]["height"]))
    print("Audio: {} ({:.3f}s, {} Hz, {} channel(s))".format(summary["audio"]["path"], summary["audio"]["duration"], summary["audio"]["sample_rate"], summary["audio"]["channels"]))
    print("Profile {}: {}x{}, {} frame @{}fps = {:.3f}s, {} steps, seed {}".format(args.profile, profile.width, profile.height, summary["frames"], profile.fps, summary["duration_seconds"], profile.steps, profile.seed))
    print_profile_window(profile, summary["frames"])
    print("Source checkout: {}".format(source_message))
    mode = getattr(args, "mouth_mode", "speech")
    print("Mouth mode: {} | conditioning: {}".format(mode, "im lặng, miệng nghỉ để tạo cache" if mode == "neutral" else "audio gốc, đang nói"))
    print("Motion source: model-generated from prompt/conditioning; no guide video is used.")
    if missing:
        print("Model assets còn thiếu/sai: {} file. Tiếp theo: test_echo_flash_rtx3060.bat fetch-models".format(len(missing)))
        for item in missing:
            print("  - {}".format(item))
    else:
        print("Model assets: đủ size theo manifest.")
    print("FFmpeg: {}".format(ffmpeg))
    print("Dry-run chỉ kiểm tra inputs/coverage, chưa probe CUDA và chưa chạy inference.")
    return 0 if ok else 1


def _model_files_for_fingerprint(echo_root: Path) -> List[Path]:
    return [get_asset_path(echo_root, asset) for asset in ASSETS]


def _source_files_for_fingerprint(echo_root: Path) -> List[Path]:
    candidates = [echo_root / "infer_flash.py", echo_root / "config" / "config.yaml"]
    candidates.extend((echo_root / "src").rglob("*.py"))
    existing = [path for path in candidates if path.is_file()]
    existing.append(Path(__file__).resolve())
    backend = Path(__file__).with_name("echo_flash_backend.py").resolve()
    if backend.is_file():
        existing.append(backend)
    requirements = Path(__file__).with_name("echo_flash_requirements.txt").resolve()
    if requirements.is_file():
        existing.append(requirements)
    return existing


def run_job(args: argparse.Namespace, echo_root: Path, python_path: Path, benchmark: bool = False) -> int:
    mouth_mode = getattr(args, "mouth_mode", "speech")
    prompt = args.prompt or (NEUTRAL_PROMPT if mouth_mode == "neutral" else DEFAULT_PROMPT)
    try:
        ffmpeg, ffprobe = resolve_tools(args.ffmpeg, args.ffprobe)
        checkout_ok, checkout_message = source_checkout_status(echo_root)
        if not checkout_ok:
            raise RuntimeError(checkout_message)
        missing = missing_model_assets(echo_root)
        if missing:
            raise RuntimeError("Thiếu hoặc sai size model file; chạy fetch-models trước: {}".format("; ".join(missing)))
        profile = PROFILES[args.profile]
        image_b = args.image_b if benchmark else None
        requested_duration = profile_duration(profile, args.duration)
        input_a = validate_input_media(args.image, args.audio, profile, requested_duration, ffprobe=ffprobe)
        benchmark_image = image_b if image_b else args.image if benchmark else None
        input_b = validate_input_media(benchmark_image, args.audio, profile, requested_duration, ffprobe=ffprobe) if benchmark_image else None
        frames = input_a["frames"]
        print("Profile {}: {}x{}, {} frame @{}fps = {:.3f}s, {} steps, seed {}".format(
            args.profile, profile.width, profile.height, frames, profile.fps,
            audio_video_duration(frames, profile.fps), profile.steps, profile.seed,
        ))
        print_profile_window(profile, frames)
        model_files = _model_files_for_fingerprint(echo_root)
        source_files = _source_files_for_fingerprint(echo_root)
        fingerprint, fingerprint_data = build_job_fingerprint(args.image, args.audio, profile, frames, prompt, model_files, source_files, mouth_mode=mouth_mode)
        if input_b:
            fingerprint_b, _ = build_job_fingerprint(benchmark_image, args.audio, profile, frames, prompt, model_files, source_files, mouth_mode=mouth_mode)
        else:
            fingerprint_b = None
    except Exception as error:
        print("Không thể bắt đầu: {}".format(error))
        return 1

    output_root = args.output_dir.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    if benchmark or args.no_output_cache:
        # Benchmark must not return a cached file instead of executing two fresh generations.
        run_token = _datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]
        prefix = "benchmark" if benchmark else "run"
        final_dir = output_root / ("{}_{}_{}".format(prefix, args.profile.lower(), run_token))
    else:
        final_dir = output_root / ("{}_{}".format(args.profile.lower(), fingerprint[:12]))
        if final_dir.exists() and not args.no_output_cache and not args.overwrite:
            expected = {"width": profile.width, "height": profile.height, "frames": frames, "fps": profile.fps, "duration": frames / profile.fps}
            if cache_manifest_valid(final_dir, fingerprint, expected, ffprobe):
                print("Output cache hit; video đã được xác minh, không render lại.")
                print("Motion base: {}".format(final_dir / "motion_base.mp4"))
                print("Voice preview: {}".format(final_dir / "voice_preview.mp4"))
                return 0
            raise RuntimeError("Output folder đã tồn tại nhưng cache không hoàn chỉnh/khớp. Không ghi đè; đổi output-dir hoặc dùng --overwrite để backup bản cũ.")
        if final_dir.exists() and args.overwrite:
            backup = final_dir.with_name(final_dir.name + ".backup-" + _datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))
            os.replace(str(final_dir), str(backup))
            print("Output cũ được giữ tại: {}".format(backup))
    if final_dir.exists():
        raise RuntimeError("Thư mục output đã tồn tại: {}".format(final_dir))
    work_dir = output_root / (".work-" + uuid.uuid4().hex)
    work_dir.mkdir(parents=True, exist_ok=False)
    logs_dir = output_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / ("{}_{}.log".format("benchmark" if benchmark else args.profile.lower(), fingerprint[:12]))
    try:
        expected = {"width": profile.width, "height": profile.height, "frames": frames, "fps": profile.fps, "duration": frames / profile.fps}
        cases = [(args.image.resolve(), fingerprint)]
        if benchmark:
            cases.append((benchmark_image.resolve(), fingerprint_b))
        backend_inputs: List[Dict[str, str]] = []
        for index, (image, fp) in enumerate(cases, 1):
            stage = work_dir / ("input_{}".format(index))
            padded_image, trimmed_audio = ffmpeg_prepare_inputs(image, args.audio.resolve(), stage, profile, expected["duration"], ffmpeg=ffmpeg, mouth_mode=mouth_mode)
            backend_inputs.append({"image": str(padded_image), "audio": str(trimmed_audio), "fingerprint": str(fp)})
        plan_path = work_dir / "worker_plan.json"
        write_json_atomic(plan_path, {
            "echo_root": str(echo_root.resolve()),
            "model_root": str((echo_root / "models").resolve()),
            "profile": asdict(profile),
            "frames": frames,
            "prompt": prompt,
            "mouth_mode": mouth_mode,
            "negative_prompt": NEGATIVE_PROMPT,
            "inputs": backend_inputs,
            "outputs_dir": str((work_dir / "backend_outputs").resolve()),
            "benchmark": benchmark,
            "cache_mode": "bypass" if benchmark or args.no_output_cache else "fingerprint",
            "ffmpeg": ffmpeg,
        })
        gpu_python = resolve_python(echo_root, args.echo_python)
        if not gpu_python.is_file():
            raise RuntimeError("Không thấy GPU Python venv: {}. Xem docs/ECHOMIMIC_V3_FLASH_WINDOWS.md.".format(gpu_python))
        backend_path = Path(__file__).with_name("echo_flash_backend.py").resolve()
        command = [str(gpu_python), "-u", str(backend_path), "run", "--plan", str(plan_path)]
        print("Bắt đầu inference. Log live: {}".format(log_path))
        start = time.perf_counter()
        env = child_environment(echo_root)
        return_code = tee_backend_process(command, echo_root, env, log_path)
        process_seconds = time.perf_counter() - start
        if return_code != 0:
            raise RuntimeError("Backend kết thúc với mã {}. Giữ nguyên log và thư mục work: {}".format(return_code, work_dir))
        backend_output_dir = work_dir / "backend_outputs"
        results = read_json(backend_output_dir / "backend_result.json")
        if results.get("status") != "complete" or len(results.get("items", [])) != len(cases):
            raise RuntimeError("Backend không báo đủ số tác vụ hoàn tất; không xuất MP4 giả.")
        for item in results["items"]:
            base_path = Path(item["motion_base"])
            preview_path = Path(item["voice_preview"])
            validate_output_file(base_path, expected, require_audio=False, ffprobe=ffprobe)
            validate_output_file(preview_path, expected, require_audio=True, ffprobe=ffprobe)
        if benchmark:
            # Keep distinct artifacts so the second image cannot be mistaken for a warm output-cache hit.
            output_items = []
            benchmark_publish = work_dir / "benchmark_publish"
            for index, item in enumerate(results["items"], 1):
                target = benchmark_publish / "character_{}".format(index)
                target.mkdir(parents=True, exist_ok=False)
                base_target = target / "motion_base.mp4"
                voice_target = target / "voice_preview.mp4"
                shutil.copyfile(item["motion_base"], base_target)
                shutil.copyfile(item["voice_preview"], voice_target)
                base_record = validate_output_file(base_target, expected, False, ffprobe)
                voice_record = validate_output_file(voice_target, expected, True, ffprobe)
                base_record["path"] = str((final_dir / target.name / base_target.name).resolve())
                voice_record["path"] = str((final_dir / target.name / voice_target.name).resolve())
                output_items.append({"motion_base": base_record,
                                     "voice_preview": voice_record,
                                     "timing": item.get("timing", {})})
            comparison = "two distinct images" if image_b else "same image rendered twice in one fresh process"
            write_json_atomic(benchmark_publish / "benchmark_report.json", {
                "status": "complete", "profile": asdict(profile), "frames": frames,
                "process_seconds": process_seconds, "note": "Hai output được render mới trong cùng process; đây không phải cam kết tốc độ RTX 3060.",
                "comparison": comparison,
                "items": output_items,
            })
            os.replace(str(benchmark_publish), str(final_dir))
            shutil.rmtree(work_dir, ignore_errors=True)
            print("Benchmark xong. Outputs: {}".format(final_dir))
            return 0
        first = results["items"][0]
        publish_dir = work_dir / "publish"
        publish_dir.mkdir()
        base_target = publish_dir / "motion_base.mp4"
        voice_target = publish_dir / "voice_preview.mp4"
        shutil.copyfile(first["motion_base"], base_target)
        shutil.copyfile(first["voice_preview"], voice_target)
        output_base = validate_output_file(base_target, expected, False, ffprobe)
        output_voice = validate_output_file(voice_target, expected, True, ffprobe)
        output_base["path"] = str((final_dir / "motion_base.mp4").resolve())
        output_voice["path"] = str((final_dir / "voice_preview.mp4").resolve())
        report = {
            "status": "complete", "fingerprint": fingerprint, "fingerprint_inputs": fingerprint_data,
            "source_image": str(args.image.resolve()), "source_audio": str(args.audio.resolve()),
            "profile": asdict(profile), "frames": frames, "duration_seconds": expected["duration"],
            "process_seconds": process_seconds, "backend_timing": first.get("timing", {}),
            "memory_mode": "sequential_cpu_offload (weights/components are not all resident on CUDA)",
            "motion_source": "neutral_prompt_and_silent_conditioning" if mouth_mode == "neutral" else "prompt_and_audio_generated",
            "mouth_mode": mouth_mode,
            "outputs": {"motion_base": output_base, "voice_preview": output_voice},
        }
        write_json_atomic(publish_dir / "run_manifest.json", report)
        # Publish only verified results atomically; retain no duplicated staged inputs on success.
        os.replace(str(publish_dir), str(final_dir))
        shutil.rmtree(work_dir, ignore_errors=True)
        print("Motion base: {}".format(final_dir / "motion_base.mp4"))
        print("Voice preview: {}".format(final_dir / "voice_preview.mp4"))
        if mouth_mode == "neutral":
            print("Neutral preview dùng tiếng im lặng; khẩu hình theo kịch bản sẽ do MuseTalk tạo sau. Kiểm tra miệng nghỉ và cử chỉ trước khi duyệt cache.")
        print("Run manifest: {}".format(final_dir / "run_manifest.json"))
        print("Thời gian tiến trình: {:.1f}s (không phải benchmark tốc độ cam kết).".format(process_seconds))
        return 0
    except Exception as error:
        print("Lỗi pipeline: {}".format(error))
        print("Giữ lại staging/log để chẩn đoán: {}".format(work_dir))
        return 1


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = make_parser()
    args = parser.parse_args(argv)
    echo_root = (args.echo_dir or default_echo_root()).expanduser().resolve()
    python_path = resolve_python(echo_root, args.echo_python)
    if args.action == "check":
        return check_environment(echo_root, python_path, args.verify_sha, args.runtime_only, args.ffmpeg, args.ffprobe)
    if args.action == "fetch-models":
        return fetch_models(echo_root, args.overwrite)
    if args.action == "dry-run":
        return dry_run(args, echo_root)
    if args.action == "benchmark":
        return run_job(args, echo_root, python_path, benchmark=True)
    return run_job(args, echo_root, python_path, benchmark=False)


if __name__ == "__main__":
    raise SystemExit(main())
