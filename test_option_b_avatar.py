"""Run a LivePortrait + MuseTalk avatar pipeline with explicit, testable settings.

An existing speech file can be supplied with ``--audio``; otherwise Edge-TTS is used.
Motion comes from one driving video, with optional calibrated torso coupling.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

if sys.platform == "win32":
    try:
        if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent


def sanitize_null_bytes():
    """Scans and strips accidental null bytes from all .py files in the project."""
    cleaned_count = 0
    for p in ROOT_DIR.rglob("*.py"):
        try:
            raw = p.read_bytes()
            if b"\x00" in raw:
                clean = raw.replace(b"\x00", b"")
                p.write_bytes(clean)
                cleaned_count += 1
        except Exception:
            pass
    if cleaned_count > 0:
        print(f"  🔧 [Auto-Fix] Đã tự động làm sạch null-bytes trong {cleaned_count} file mã nguồn.")


def ensure_environment_compatibility():
    """Ensure numpy is pinned to 1.26.4 to prevent binary ABI incompatibility with mmcv/cv2/xtcocotools."""
    try:
        import numpy as np
        if np.__version__.startswith("2."):
            print(f"  🔧 [Auto-Fix] Phát hiện NumPy {np.__version__} (không tương thích DWPose). Đang tự động hạ xuống 1.26.4...")
            subprocess.run([sys.executable, "-m", "pip", "install", "numpy==1.26.4", "--user", "--quiet"])
            print("  ✅ Đã đồng bộ NumPy 1.26.4 thành công!")
    except Exception:
        pass


def find_character_image(char_type: str = "office") -> Path:
    if char_type == "office":
        office_candidates = [
            ROOT_DIR / "assets" / "characters" / "nhanvatnam" / "asian_male_office_1080p.png",
            Path.home() / "Dropbox" / "PC" / "Downloads" / "asian_male_office_1080p.png",
            Path("C:/Users/Admin/Dropbox/PC/Downloads/asian_male_office_1080p.png"),
            Path("C:/Users/quant/Dropbox/PC/Downloads/asian_male_office_1080p.png"),
        ]
        for oc in office_candidates:
            if oc.is_file():
                return oc
        folder = ROOT_DIR / "assets" / "characters" / "nhanvatnam"
    elif char_type == "female":
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


def find_liveportrait_dir() -> Path | None:
    candidates = [
        ROOT_DIR / "LivePortrait",
        Path("C:/LivePortrait"),
        Path("D:/LivePortrait"),
        Path.home() / "Downloads" / "LivePortrait",
        Path.home() / "Desktop" / "LivePortrait",
        Path("C:/Users/Admin/Downloads/LivePortrait"),
        Path("C:/Users/Admin/Desktop/LivePortrait"),
    ]
    for c in candidates:
        if (c / "inference.py").is_file():
            return c
    # Deep search in Downloads and Desktop
    for search_root in [
        Path.home() / "Downloads",
        Path.home() / "Desktop",
        Path("C:/Users/Admin/Downloads"),
        Path("C:/Users/Admin/Desktop"),
    ]:
        if search_root.is_dir():
            for sub in search_root.glob("*LivePortrait*"):
                if (sub / "inference.py").is_file():
                    return sub
                for nested in sub.glob("**/inference.py"):
                    return nested.parent
    return None


def find_driving_template() -> Path | None:
    dest_dir = ROOT_DIR / "assets" / "driving_templates"
    candidates = [
        dest_dir / "reference_head_driving.mp4",
        dest_dir / "natural_driving_template.mp4",
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
            return c
    return None


def find_musetalk_python() -> str:
    candidates = [
        ROOT_DIR / "musetalk-venv" / "Scripts" / "python.exe",
        Path("D:/rustProject/video-creative-studio/musetalk-venv/Scripts/python.exe"),
        Path("D:/rustProject/prostudio-ai/musetalk-venv/Scripts/python.exe"),
        Path.home() / "Downloads" / "video-creative-studio" / "musetalk-venv" / "Scripts" / "python.exe",
        Path.home() / "Downloads" / "musetalk-venv" / "Scripts" / "python.exe",
        Path("C:/Users/Admin/Downloads/video-creative-studio/video-creative-studio/musetalk-venv/Scripts/python.exe"),
        Path("C:/Users/Admin/Downloads/video-creative-studio/musetalk-venv/Scripts/python.exe"),
        Path("C:/Users/Admin/Downloads/musetalk-venv/Scripts/python.exe"),
    ]
    for c in candidates:
        if c.is_file():
            return str(c)
    return sys.executable


async def synthesize_speech(text: str, voice: str, out_audio: Path) -> float:
    import edge_tts
    comm = edge_tts.Communicate(text, voice)
    with open(out_audio, "wb") as f:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(out_audio)
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Không đọc được thời lượng audio: {res.stderr.strip()}")
    duration = float(res.stdout.strip())
    if duration <= 0:
        raise RuntimeError("Audio không có thời lượng hợp lệ.")
    return duration


def get_media_duration(media_path: Path) -> float:
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(media_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Không đọc được thời lượng {media_path}: {result.stderr.strip()}")
    duration = float(result.stdout.strip())
    if duration <= 0:
        raise RuntimeError(f"Media không có thời lượng hợp lệ: {media_path}")
    return duration


def trim_audio_to_duration(audio_path: Path, temp_dir: Path, duration: float) -> Path:
    actual_duration = get_media_duration(audio_path)
    if duration > actual_duration + 0.05:
        raise ValueError(f"--duration={duration:g}s dài hơn audio ({actual_duration:.2f}s).")
    if duration >= actual_duration - 0.05:
        return audio_path
    trimmed_audio = temp_dir / "trimmed_speech.wav"
    result = subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(audio_path), "-t", f"{duration:.6f}",
            "-c:a", "pcm_s16le", str(trimmed_audio),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not trimmed_audio.is_file():
        raise RuntimeError(f"Không cắt được audio: {result.stderr.strip()}")
    return trimmed_audio


def main():
    parser = argparse.ArgumentParser(description="LivePortrait + MuseTalk test pipeline (RTX 3060 12GB)")
    parser.add_argument("--char", choices=["office", "male", "female", "pixar"], default="office", help="Loại nhân vật mặc định")
    parser.add_argument("--source", default=None, help="Ảnh nguồn; nếu bỏ trống dùng ảnh theo --char")
    parser.add_argument("--driving", default=None, help="Driving video; mặc định ưu tiên reference_head_driving.mp4")
    parser.add_argument("--audio", default=None, help="Audio có sẵn; bỏ qua Edge-TTS")
    parser.add_argument("--output", default=None, help="Đường dẫn video đầu ra")
    parser.add_argument("--script", default="Xin chào các bạn, tôi là trợ lý ảo được tạo hoàn toàn tự động bằng công nghệ AI cao cấp.", help="Kịch bản nếu chưa có --audio")
    parser.add_argument("--script-file", default=None, help="File text nếu chưa có --audio")
    parser.add_argument("--liveportrait-dir", default=None, help="Thư mục LivePortrait")
    parser.add_argument("--musetalk-dir", default=None, help="Thư mục MuseTalk")
    parser.add_argument("--musetalk-python", default=None, help="Python của môi trường MuseTalk")
    parser.add_argument("--unet-model-path", default=None, help="MuseTalk v1.5 UNet weights")
    parser.add_argument("--unet-config", default=None, help="MuseTalk UNet config")
    parser.add_argument("--duration", type=float, default=None, help="Cắt cùng audio/video theo số giây")
    parser.add_argument("--fps", type=int, default=25, help="FPS thống nhất cho LivePortrait và MuseTalk")
    parser.add_argument("--source-max-dim", type=int, default=1280, help="LivePortrait source_max_dim")
    parser.add_argument("--multiplier", type=float, default=0.55, help="Hệ số motion LivePortrait")
    parser.add_argument("--driving-policy", choices=["hold", "loop"], default="hold", help="Khi audio dài hơn driving: giữ frame cuối hoặc loop")
    parser.add_argument("--flag-eye-retargeting", action="store_true", default=False, help="Thử eye retargeting đang được LivePortrait đánh dấu WIP")
    parser.add_argument("--legacy-vendor-patches", action="store_true", default=False, help="Bật các custom smoothing/blink patch cũ một cách tường minh")
    parser.add_argument("--motion-mode", choices=["off", "coupled"], default="off", help="Coupling thân nhỏ trước MuseTalk; mặc định tắt")
    parser.add_argument("--body-mask", default=None, help="Mask xám cùng kích thước video; vùng trắng là áo/vai được phép dịch")
    parser.add_argument("--body-render-mode", choices=["interior", "silhouette"], default="interior", help="Render nội vùng tương thích cũ hoặc dịch biên silhouette thân")
    parser.add_argument("--face-roi", nargs=4, type=int, metavar=("X", "Y", "W", "H"), default=None, help="ROI khuôn mặt theo frame Stage 1")
    parser.add_argument("--max-displacement-px", type=float, default=2.5, help="Giới hạn dịch vai tại chiều cao 1280px")
    parser.add_argument("--coupling-strength", type=float, default=0.25, help="Độ phản hồi vai theo chuyển động đầu đo được")
    parser.add_argument("--head-motion-lag-seconds", type=float, default=0.14, help="Độ trễ làm mượt phản hồi vai")
    parser.add_argument("--batch-size", type=int, default=2, help="Batch MuseTalk; giảm 1 nếu OOM")
    parser.add_argument("--offset-ms", type=int, default=0, help="Hiệu chỉnh feature audio theo ms; không dịch audio cuối")
    parser.add_argument("--dry-run", action="store_true", help="In cấu hình và khả năng tìm thấy stage, không chạy GPU hay ghi output")
    args = parser.parse_args()

    if args.duration is not None and args.duration <= 0:
        parser.error("--duration phải lớn hơn 0")
    if args.fps <= 0 or args.source_max_dim <= 0 or args.batch_size <= 0:
        parser.error("--fps, --source-max-dim và --batch-size phải lớn hơn 0")
    if args.max_displacement_px <= 0 or args.coupling_strength <= 0 or args.head_motion_lag_seconds <= 0:
        parser.error("--max-displacement-px, --coupling-strength và --head-motion-lag-seconds phải lớn hơn 0")
    if args.motion_mode == "coupled" and (not args.body_mask or not args.face_roi):
        if args.char == "office" and not args.source:
            office_mask = "office_torso_silhouette_mask.png" if args.body_render_mode == "silhouette" else "office_torso_motion_mask.png"
            args.body_mask = args.body_mask or str(ROOT_DIR / "assets" / "driving_templates" / office_mask)
            args.face_roi = args.face_roi or [360, 490, 320, 460]
        if not args.body_mask or not args.face_roi:
            parser.error("motion-mode coupled cần --body-mask và --face-roi theo frame output")

    script_text = args.script
    if args.script_file:
        script_file = Path(args.script_file).expanduser().resolve()
        if not script_file.is_file():
            parser.error(f"Không tìm thấy --script-file: {script_file}")
        script_text = script_file.read_text(encoding="utf-8").strip()

    char_img = Path(args.source).expanduser().resolve() if args.source else find_character_image(args.char).resolve()
    driving = Path(args.driving).expanduser().resolve() if args.driving else find_driving_template()
    lp_dir = Path(args.liveportrait_dir).expanduser().resolve() if args.liveportrait_dir else find_liveportrait_dir()
    lipsync_runner = ROOT_DIR / "runners" / "lipsync_runner.py"
    muse_py = args.musetalk_python or find_musetalk_python()
    default_m_dir, _default_muse_py = (None, None)
    if not args.musetalk_dir:
        try:
            from runners.lipsync_runner import find_musetalk_paths
            default_m_dir, _default_muse_py = find_musetalk_paths()
        except Exception:
            pass
    musetalk_dir = Path(args.musetalk_dir).expanduser().resolve() if args.musetalk_dir else default_m_dir
    final_video = Path(args.output).expanduser().resolve() if args.output else ROOT_DIR / "output" / "avatar_option_b_result.mp4"
    audio_plan = Path(args.audio).expanduser().resolve() if args.audio else None

    if args.dry_run:
        payload = {
            "source": str(char_img),
            "source_exists": char_img.is_file(),
            "driving": str(driving) if driving else None,
            "driving_exists": bool(driving and driving.is_file()),
            "audio": str(audio_plan) if audio_plan else "Edge-TTS from script",
            "audio_exists": bool(audio_plan and audio_plan.is_file()) if audio_plan else None,
            "liveportrait_dir": str(lp_dir) if lp_dir else None,
            "liveportrait_code_available": bool(lp_dir and (lp_dir / "inference.py").is_file()),
            "liveportrait_weights_available": bool(lp_dir and all(
                (lp_dir / relative_path).is_file()
                for relative_path in (
                    "pretrained_weights/liveportrait/base_models/appearance_feature_extractor.pth",
                    "pretrained_weights/liveportrait/base_models/motion_extractor.pth",
                    "pretrained_weights/liveportrait/base_models/spade_generator.pth",
                    "pretrained_weights/liveportrait/base_models/warping_module.pth",
                )
            )),
            "musetalk_dir": str(musetalk_dir) if musetalk_dir else None,
            "musetalk_python": str(muse_py),
            "musetalk_runner_exists": lipsync_runner.is_file(),
            "output": str(final_video),
            "duration_seconds": args.duration,
            "fps": args.fps,
            "source_max_dim": args.source_max_dim,
            "driving_multiplier": args.multiplier,
            "driving_policy": args.driving_policy,
            "eye_retargeting": args.flag_eye_retargeting,
            "legacy_vendor_patches": args.legacy_vendor_patches,
            "motion_mode": args.motion_mode,
            "body_mask": args.body_mask,
            "body_render_mode": args.body_render_mode,
            "face_roi": args.face_roi,
            "max_displacement_px": args.max_displacement_px,
            "coupling_strength": args.coupling_strength,
            "head_motion_lag_seconds": args.head_motion_lag_seconds,
            "musetalk_batch_size": args.batch_size,
            "audio_feature_offset_ms": args.offset_ms,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    for input_name, input_path in (("ảnh nguồn", char_img), ("audio", audio_plan), ("driving video", driving)):
        if input_path is not None and not input_path.is_file():
            print(f"❌ Không tìm thấy {input_name}: {input_path}")
            return 1
    if not lp_dir or not (lp_dir / "inference.py").is_file():
        print("❌ Không tìm thấy LivePortrait inference.py; dừng để tránh xuất video tĩnh.")
        return 1
    if not driving:
        print("❌ Không tìm thấy driving template. Chỉ định bằng --driving.")
        return 1
    if not lipsync_runner.is_file():
        print(f"❌ Không tìm thấy MuseTalk runner: {lipsync_runner}")
        return 1

    temp_root = ROOT_DIR / "temp"
    temp_root.mkdir(parents=True, exist_ok=True)
    import tempfile
    temp_dir = Path(tempfile.mkdtemp(prefix="option_b_", dir=str(temp_root)))
    audio_path = audio_plan if audio_plan else temp_dir / "vietnamese_speech.mp3"
    if not audio_plan:
        voice = "vi-VN-NamMinhNeural" if args.char in ["office", "male"] else "vi-VN-HoaiMyNeural"
        print(f"[TTS] Tổng hợp giọng {voice} từ script...")
        try:
            dur = asyncio.run(synthesize_speech(script_text, voice, audio_path))
        except Exception as exc:
            print(f"❌ Edge-TTS thất bại: {exc}")
            print(f"Log và file tạm được giữ tại: {temp_dir}")
            return 1
    else:
        try:
            dur = get_media_duration(audio_path)
        except Exception as exc:
            print(f"❌ {exc}")
            print(f"Log và file tạm được giữ tại: {temp_dir}")
            return 1

    try:
        if args.duration is not None:
            audio_path = trim_audio_to_duration(audio_path, temp_dir, args.duration)
            dur = get_media_duration(audio_path)
    except Exception as exc:
        print(f"❌ Không chuẩn bị được audio: {exc}")
        print(f"Log và file tạm được giữ tại: {temp_dir}")
        return 1

    print("=" * 75)
    print("VIDEO CREATIVE STUDIO - LIVEPORTRAIT + MUSETALK TEST PIPELINE")
    print(f"Nguồn: {char_img}\nDriving: {driving}\nAudio: {audio_path} ({dur:.2f}s)")
    print(f"Cấu hình: fps={args.fps}, max_dim={args.source_max_dim}, multiplier={args.multiplier}, MuseTalk batch={args.batch_size}")
    if args.motion_mode == "coupled":
        print(f"Vai: mode={args.body_render_mode}, max={args.max_displacement_px:g}px, coupling={args.coupling_strength:g}, lag={args.head_motion_lag_seconds:g}s")
    print("=" * 75)

    stage1_video = temp_dir / "stage1_liveportrait.mp4"
    input_for_stage2 = str(stage1_video)
    start_t = time.time()
    from runners.liveportrait_runner import run_liveportrait
    ok_stage1 = run_liveportrait(
        source_img=str(char_img),
        driving_video=str(driving),
        audio_path=str(audio_path),
        output_path=str(stage1_video),
        liveportrait_dir=str(lp_dir),
        driving_multiplier=args.multiplier,
        flag_eye_retargeting=args.flag_eye_retargeting,
        source_max_dim=args.source_max_dim,
        fps=args.fps,
        driving_policy=args.driving_policy,
        legacy_vendor_patch=args.legacy_vendor_patches,
    )
    if not ok_stage1 or not stage1_video.is_file() or stage1_video.stat().st_size <= 1000:
        print("❌ LivePortrait stage thất bại; MuseTalk chưa chạy.")
        print(f"Log và file tạm được giữ tại: {temp_dir}")
        return 1

    if args.motion_mode == "coupled":
        from runners.apply_conversational_motion import apply_conversational_motion_to_video
        coupled_stage = temp_dir / "stage1_coupled.mp4"
        print("[Coupling] Đo chuyển động vùng mắt/trán và ghép phản ứng vai trong mask đã hiệu chuẩn...")
        if not apply_conversational_motion_to_video(
            str(stage1_video),
            str(coupled_stage),
            audio_path=str(audio_path),
            mode="coupled",
            body_mask_path=args.body_mask,
            face_roi=args.face_roi,
            max_displacement_px=args.max_displacement_px,
            head_motion_lag_seconds=args.head_motion_lag_seconds,
            coupling_strength=args.coupling_strength,
            body_render_mode=args.body_render_mode,
        ) or not coupled_stage.is_file() or coupled_stage.stat().st_size <= 1000:
            print("❌ Body coupling thất bại; MuseTalk chưa chạy.")
            print(f"Log và file tạm được giữ tại: {temp_dir}")
            return 1
        input_for_stage2 = str(coupled_stage)

    cmd_stage2 = [
        muse_py,
        str(lipsync_runner),
        "--action", "sync",
        "--video", input_for_stage2,
        "--audio", str(audio_path),
        "--output", str(final_video),
        "--engine", "musetalk",
        "--batch-size", str(args.batch_size),
        "--fps", str(args.fps),
        "--offset-ms", str(args.offset_ms),
    ]
    if args.musetalk_dir:
        cmd_stage2.extend(["--musetalk-dir", str(Path(args.musetalk_dir).expanduser().resolve())])
    if args.musetalk_python:
        cmd_stage2.extend(["--musetalk-python", str(Path(args.musetalk_python).expanduser().resolve())])
    if args.unet_model_path:
        cmd_stage2.extend(["--unet-model-path", str(Path(args.unet_model_path).expanduser().resolve())])
    if args.unet_config:
        cmd_stage2.extend(["--unet-config", str(Path(args.unet_config).expanduser().resolve())])

    print("[MuseTalk] Đang xử lý lip-sync v1.5 FP16...")
    try:
        proc = subprocess.run(cmd_stage2, text=True)
    except OSError as exc:
        print(f"❌ Không khởi chạy được MuseTalk: {exc}")
        print(f"Log và file tạm được giữ tại: {temp_dir}")
        return 1
    stage2_success = proc.returncode == 0 and final_video.is_file() and final_video.stat().st_size > 1000
    if not stage2_success:
        print(f"❌ MuseTalk stage thất bại (exit code {proc.returncode}); không dùng fallback hoặc video tĩnh.")
        print(f"Log và file tạm được giữ tại: {temp_dir}")
        return 1

    total_time = time.time() - start_t
    print(f"✅ Video đầu ra: {final_video}")
    print(f"Thời gian các stage GPU: {total_time:.1f}s")

    try:
        res = subprocess.check_output(
            [
                "ffprobe", "-v", "error", "-show_entries",
                "stream=codec_type,width,height,r_frame_rate,duration:format=duration",
                "-of", "json", str(final_video),
            ],
            text=True,
        )
        probe = json.loads(res)
        streams = probe.get("streams", [])
        video_stream = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
        audio_stream = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
        if not video_stream or not audio_stream:
            raise RuntimeError("Thiếu video stream hoặc audio stream trong kết quả.")
        video_duration = float(video_stream.get("duration") or probe["format"]["duration"])
        audio_duration = float(audio_stream.get("duration") or probe["format"]["duration"])
        expected_duration = get_media_duration(audio_path)
        frame_rate = video_stream.get("r_frame_rate", "0/1").split("/")
        fps_num, fps_den = (int(value) for value in frame_rate)
        actual_fps = fps_num / fps_den if fps_den else 0.0
        duration_tolerance = 1.0 / max(args.fps, 1) + 0.03
        print(
            f"Thông số đầu ra: {video_stream['width']}x{video_stream['height']} @ {actual_fps:g}fps; "
            f"video={video_duration:.3f}s, audio={audio_duration:.3f}s, nguồn={expected_duration:.3f}s"
        )
        if int(video_stream["width"]) <= 0 or int(video_stream["height"]) <= 0:
            raise RuntimeError("Kích thước video đầu ra không hợp lệ.")
        if actual_fps <= 0 or abs(actual_fps - args.fps) > 0.01:
            raise RuntimeError(f"FPS đầu ra {actual_fps:g} khác cấu hình yêu cầu {args.fps}.")
        if (
            abs(video_duration - audio_duration) > duration_tolerance
            or abs(video_duration - expected_duration) > duration_tolerance
            or abs(audio_duration - expected_duration) > duration_tolerance
        ):
            raise RuntimeError(
                f"Độ dài đầu ra lệch audio nguồn quá một frame cộng độ trễ AAC "
                f"({video_duration:.3f}s video, {audio_duration:.3f}s audio, {expected_duration:.3f}s nguồn)."
            )
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"❌ Xác minh ffprobe thất bại: {exc}")
        print(f"Log và file tạm được giữ tại: {temp_dir}")
        return 1

    if args.output is None and not args.dry_run:
        dropbox_dirs = [
            Path.home() / "Dropbox" / "PC" / "Downloads",
            Path("C:/Users/Admin/Dropbox/PC/Downloads"),
            Path("C:/Users/quant/Dropbox/PC/Downloads"),
        ]
        for dp in dropbox_dirs:
            if dp.is_dir():
                try:
                    target_file = dp / final_video.name
                    shutil.copy2(str(final_video), str(target_file))
                    print(f"🚀 Đã tự động đồng bộ sang Dropbox: {target_file}")
                    break
                except Exception:
                    pass
        if os.name == "nt":
            os.startfile(str(final_video))

    shutil.rmtree(temp_dir, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
