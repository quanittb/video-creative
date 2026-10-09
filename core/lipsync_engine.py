"""Lipsync Engine: Multi-tier driver for MuseTalk, LivePortrait, and LatentSync."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional


class LipsyncEngine:
    """Orchestrates lip-sync generation between character images/videos and speech audio."""

    def __init__(self, mode: str = "auto", runner_path: Optional[str] = None):
        self.mode = mode
        self.runner_path = runner_path or self._find_prostudio_runner()

    @staticmethod
    def _find_prostudio_runner() -> Optional[str]:
        candidates = [
            Path("D:/rustProject/prostudio-ai/server/lipsync_runner.py"),
            Path("/workspace/prostudio-ai/server/lipsync_runner.py"),
            Path(__file__).resolve().parent.parent / "runners" / "lipsync_runner.py",
        ]
        for c in candidates:
            if c.is_file():
                return str(c)
        return None

    @staticmethod
    def _find_liveportrait_dir() -> Optional[Path]:
        candidates = [
            Path(__file__).resolve().parent.parent / "LivePortrait",
            Path("C:/LivePortrait"),
            Path("D:/LivePortrait"),
            Path("/workspace/LivePortrait"),
            Path.home() / "Downloads" / "LivePortrait",
            Path.home() / "Desktop" / "LivePortrait",
            Path("C:/Users/Admin/Downloads/LivePortrait"),
            Path("C:/Users/Admin/Desktop/LivePortrait"),
        ]
        for c in candidates:
            if (c / "inference.py").is_file():
                return c
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

    @staticmethod
    def find_ffmpeg() -> str:
        in_path = shutil.which("ffmpeg")
        if in_path:
            return in_path
        try:
            import imageio_ffmpeg
            return imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            pass
        candidates = [
            Path("C:/Program Files/ffmpeg/bin/ffmpeg.exe"),
            Path("C:/ffmpeg/bin/ffmpeg.exe"),
        ]
        for c in candidates:
            if c.is_file():
                return str(c)
        return "ffmpeg"

    def _get_audio_duration(self, audio_p: str) -> float:
        try:
            import soundfile as sf
            info = sf.info(str(audio_p))
            return float(info.duration)
        except Exception:
            pass
        return 3.0

    def sync(
        self,
        character_visual: str,
        audio_path: str,
        output_video: str,
        engine: str = "musetalk",
        enhance: bool = False,
    ) -> Dict[str, Any]:
        """Generate lip-synced video clip from image/video and audio (Stage 1 LivePortrait + Stage 2 MuseTalk)."""
        out_p = Path(output_video)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        ffmpeg_bin = self.find_ffmpeg()

        vis_p = Path(character_visual)
        is_image = vis_p.suffix.lower() in [".png", ".jpg", ".jpeg", ".webp"]
        orig_image = str(vis_p) if is_image else None

        # ---------------------------------------------------------
        # CHẶNG 1: LivePortrait - Cử động đầu 3D tự nhiên & Pasteback 1080p
        # ---------------------------------------------------------
        lp_runner = Path(__file__).resolve().parent.parent / "runners" / "liveportrait_runner.py"
        lp_dir = self._find_liveportrait_dir()
        driving_template = Path(__file__).resolve().parent.parent / "assets" / "driving_templates" / "natural_driving_template.mp4"

        stage1_video: Optional[Path] = None

        if lp_dir and lp_runner.is_file() and driving_template.is_file() and orig_image:
            print(f"[LipsyncEngine] [Chặng 1/2] Tìm thấy LivePortrait tại {lp_dir}. Đang tạo cử động đầu 3D & Pasteback 1080p...")
            stage1_target = out_p.parent / f"_stage1_{out_p.name}" if (self.runner_path and Path(self.runner_path).is_file()) else out_p
            if stage1_target.is_file():
                stage1_target.unlink(missing_ok=True)
            cmd_lp = [
                sys.executable,
                str(lp_runner),
                "--source", str(orig_image),
                "--driving", str(driving_template),
                "--audio", str(audio_path),
                "--output", str(stage1_target),
                "--lp_dir", str(lp_dir),
            ]
            try:
                subprocess.run(cmd_lp, check=True)
                if stage1_target.is_file() and stage1_target.stat().st_size > 1000:
                    stage1_video = stage1_target
                    print(f"[LipsyncEngine] [Chặng 1/2] Hoàn tất cử động đầu 3D tự nhiên!")
            except Exception as e:
                print(f"[LipsyncEngine] [Chặng 1/2] LivePortrait gặp lỗi: {e}")

        # If Stage 1 generated video directly to out_p and no runner exists, we're done
        if stage1_video and stage1_video == out_p:
            return {"success": True, "output": str(out_p), "engine": "liveportrait"}

        # Determine video input for Stage 2 (Audio Lip Sync)
        if stage1_video and stage1_video.is_file():
            input_for_stage2 = str(stage1_video)
        elif is_image:
            dur = self._get_audio_duration(audio_path)
            temp_loop_vid = out_p.parent / f"_loop_{out_p.stem}.mp4"
            cmd_loop = [
                ffmpeg_bin, "-y", "-loop", "1",
                "-i", str(vis_p),
                "-t", str(dur),
                "-r", "25",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                str(temp_loop_vid),
            ]
            subprocess.run(cmd_loop, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            input_for_stage2 = str(temp_loop_vid)
        else:
            input_for_stage2 = character_visual

        # ---------------------------------------------------------
        # CHẶNG 2: Audio-Driven Lip Sync (MuseTalk FP16)
        # Khớp khẩu hình chính xác theo từng âm tiết của audio giọng đọc tiếng Việt
        # ---------------------------------------------------------
        if self.runner_path and Path(self.runner_path).is_file():
            venv_candidates = [
                Path(__file__).resolve().parent.parent / "musetalk-venv" / "Scripts" / "python.exe",
                Path("D:/rustProject/video-creative-studio/musetalk-venv/Scripts/python.exe"),
                Path("D:/rustProject/prostudio-ai/musetalk-venv/Scripts/python.exe"),
                Path.home() / "Downloads" / "video-creative-studio" / "musetalk-venv" / "Scripts" / "python.exe",
                Path.home() / "Downloads" / "musetalk-venv" / "Scripts" / "python.exe",
                Path("C:/Users/Admin/Downloads/video-creative-studio/musetalk-venv/Scripts/python.exe"),
                Path("C:/Users/Admin/Downloads/musetalk-venv/Scripts/python.exe"),
            ]
            py_bin = next((str(p) for p in venv_candidates if p.is_file()), sys.executable)

            print(f"[LipsyncEngine] [Chặng 2/2] Đang khớp khẩu hình MuseTalk FP16 theo giọng nói...")
            cmd = [
                py_bin,
                self.runner_path,
                "--action", "sync",
                "--video", str(input_for_stage2),
                "--audio", str(audio_path),
                "--output", str(out_p),
                "--engine", engine,
            ]
            if enhance:
                cmd.append("--enhance")

            try:
                subprocess.run(cmd, check=True)
                if out_p.is_file() and out_p.stat().st_size > 1000:
                    engine_label = "liveportrait+lipsync" if stage1_video else engine
                    return {"success": True, "output": str(out_p), "engine": engine_label}
            except Exception as e:
                print(f"[LipsyncEngine] [Chặng 2/2] Lipsync runner gặp lỗi ({e}).")

        # If Stage 2 failed or was not available, but Stage 1 succeeded, use Stage 1 result!
        if stage1_video and stage1_video.is_file():
            print("[LipsyncEngine] Giữ video Chặng 1 (LivePortrait 1080p tự nhiên) làm sản phẩm chính.")
            if stage1_video != out_p:
                shutil.copy2(stage1_video, out_p)
            return {"success": True, "output": str(out_p), "engine": "liveportrait"}

        # Fallback cuối cùng nếu cả 2 chặng AI đều không chạy được
        cmd_fallback = [
            ffmpeg_bin,
            "-y",
            "-loop", "1",
            "-i", str(character_visual),
            "-i", str(audio_path),
            "-c:v", "libx264",
            "-tune", "stillimage",
            "-c:a", "aac",
            "-b:a", "192k",
            "-pix_fmt", "yuv420p",
            "-shortest",
            str(out_p),
        ]
        subprocess.run(cmd_fallback, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"success": True, "output": str(out_p), "mode": "fallback_stillimage"}
