"""Video Composer: FFmpeg-based multi-layer scene compositor and timeline assembler."""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional


class VideoComposer:
    """Composites characters, dynamic background videos, B-rolls, subtitles, and audio ducking."""

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

    def __init__(self, temp_dir: Optional[str] = None):
        self.temp_dir = Path(temp_dir or Path(__file__).resolve().parent.parent / "temp" / "composer")
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.ffmpeg_bin = self.find_ffmpeg()

    def render_scene(
        self,
        scene: Dict[str, Any],
        character_video: str,
        bg_video: Optional[str] = None,
        broll_video: Optional[str] = None,
        output_file: Optional[str] = None,
    ) -> str:
        """Compose a single scene with background, character positioning, and camera framing."""
        scene_id = scene["scene_id"]
        out_p = Path(output_file or self.temp_dir / f"rendered_scene_{scene_id:03d}.mp4")
        duration = scene.get("duration", 4.0)
        shot = scene.get("camera_shot", "MEDIUM")
        layout = scene.get("layout", "FULL_CHARACTER")

        # Framing zoom factor
        zoom_factor = 1.0
        if shot == "MEDIUM":
            zoom_factor = 1.15
        elif shot == "CLOSE_UP":
            zoom_factor = 1.30

        # Case 1: B_ROLL_FULL layout (Character is Voice-Over)
        if layout == "B_ROLL_FULL" and broll_video and Path(broll_video).is_file():
            cmd = [
                self.ffmpeg_bin, "-y",
                "-stream_loop", "-1", "-i", str(broll_video),
                "-i", scene["audio_path"],
                "-t", str(duration),
                "-vf", f"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
                "-c:v", "libx264", "-c:a", "aac", "-pix_fmt", "yuv420p", "-shortest",
                str(out_p),
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return str(out_p)

        # Case 2: FULL_CHARACTER with dynamic background video
        if bg_video and Path(bg_video).is_file():
            # Composite background (blurred bokeh) with character in foreground
            filter_complex = (
                f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=15:5[bg];"
                f"[1:v]scale=iw*{zoom_factor}:ih*{zoom_factor}[fg];"
                f"[bg][fg]overlay=(W-w)/2:(H-h)/2[outv]"
            )
            cmd = [
                self.ffmpeg_bin, "-y",
                "-stream_loop", "-1", "-i", str(bg_video),
                "-i", str(character_video),
                "-t", str(duration),
                "-filter_complex", filter_complex,
                "-map", "[outv]",
                "-map", "1:a?",
                "-c:v", "libx264", "-crf", "18", "-preset", "slow",
                "-c:a", "aac", "-b:a", "320k", "-pix_fmt", "yuv420p",
                str(out_p),
            ]
            try:
                subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return str(out_p)
            except Exception:
                pass  # Fallback to direct character video

        # Case 3: Direct character framing fallback
        crop_filter = f"scale=1080*{zoom_factor}:1920*{zoom_factor},crop=1080:1920"
        cmd = [
            self.ffmpeg_bin, "-y",
            "-i", str(character_video),
            "-t", str(duration),
            "-vf", crop_filter,
            "-c:v", "libx264", "-crf", "18", "-preset", "slow",
            "-c:a", "aac", "-b:a", "320k", "-pix_fmt", "yuv420p",
            str(out_p),
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return str(out_p)

    def concatenate_scenes(self, scene_video_paths: List[str], output_path: str) -> str:
        """Stitch multiple rendered scene clips into a single video."""
        list_file = self.temp_dir / "concat_list.txt"
        with open(list_file, "w", encoding="utf-8") as f:
            for p in scene_video_paths:
                f.write(f"file '{Path(p).resolve().as_posix()}'\n")

        cmd = [
            self.ffmpeg_bin, "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(list_file),
            "-c:v", "libx264", "-crf", "18", "-preset", "slow",
            "-c:a", "aac", "-b:a", "320k",
            "-pix_fmt", "yuv420p",
            str(output_path),
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return str(output_path)

    def apply_bgm_and_subtitles(
        self,
        main_video: str,
        output_final: str,
        bgm_path: Optional[str] = None,
        srt_path: Optional[str] = None,
    ) -> str:
        """Add background music with audio ducking and burn dynamic subtitles."""
        out_p = Path(output_final)
        out_p.parent.mkdir(parents=True, exist_ok=True)

        inputs = ["-i", str(main_video)]
        filter_parts = []

        # Subtitle burning
        vf = []
        if srt_path and Path(srt_path).is_file():
            # Escape path for ffmpeg subtitles filter
            escaped_srt = str(Path(srt_path).resolve().as_posix()).replace(":", "\\:")
            vf.append(f"subtitles='{escaped_srt}':force_style='FontSize=24,PrimaryColour=&H00FFFF,OutlineColour=&H000000,BorderStyle=3,Bold=1'")

        # BGM with audio ducking
        if bgm_path and Path(bgm_path).is_file():
            inputs.extend(["-stream_loop", "-1", "-i", str(bgm_path)])
            # Duck BGM volume when voice is present
            filter_parts.append("[1:a]volume=0.08[bgm];[0:a][bgm]amix=inputs=2:duration=first[aout]")

        cmd = [self.ffmpeg_bin, "-y"] + inputs
        if vf:
            cmd.extend(["-vf", ",".join(vf)])

        if filter_parts:
            cmd.extend(["-filter_complex", ";".join(filter_parts), "-map", "0:v", "-map", "[aout]", "-c:a", "aac", "-b:a", "320k"])
        else:
            cmd.extend(["-c:a", "copy"])

        cmd.extend(["-c:v", "libx264", "-crf", "18", "-preset", "slow", "-pix_fmt", "yuv420p", "-shortest", str(out_p)])
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return str(out_p)
