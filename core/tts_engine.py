"""Multilingual TTS Engine with Subtitle Synchronization."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional


class TTSEngine:
    """Handles audio synthesis and word-level timestamp generation."""

    def __init__(self, output_dir: Optional[str] = None):
        self.output_dir = Path(output_dir or Path(__file__).resolve().parent.parent / "temp" / "audio")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def _synthesize_edge_tts(self, text: str, voice: str, out_audio: Path, out_vtt: Optional[Path] = None) -> float:
        import edge_tts

        communicate = edge_tts.Communicate(text, voice)
        sub_maker = edge_tts.SubMaker()

        with open(out_audio, "wb") as f_audio:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    f_audio.write(chunk["data"])
                elif chunk["type"] == "WordBoundary" and out_vtt:
                    sub_maker.feed(chunk)

        if out_vtt:
            with open(out_vtt, "w", encoding="utf-8") as f_sub:
                f_sub.write(sub_maker.get_srt())

        # Probe duration using ffprobe
        return self.get_audio_duration(out_audio)

    @staticmethod
    def get_audio_duration(audio_path: Path) -> float:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
        ]
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
            return float(res.stdout.strip())
        except Exception:
            return 3.0  # Fallback estimate

    def generate_scene_audio(
        self,
        scene_id: int,
        text: str,
        voice: str = "es-ES-AlvaroNeural",
        provider: str = "edge-tts",
    ) -> Dict[str, Any]:
        """Synthesize audio and subtitles for a single scene."""
        audio_file = self.output_dir / f"scene_{scene_id:03d}.mp3"
        srt_file = self.output_dir / f"scene_{scene_id:03d}.srt"

        if provider == "edge-tts":
            duration = asyncio.run(self._synthesize_edge_tts(text, voice, audio_file, srt_file))
        else:
            # Fallback to edge-tts if external provider is not configured
            duration = asyncio.run(self._synthesize_edge_tts(text, voice, audio_file, srt_file))

        return {
            "scene_id": scene_id,
            "audio_path": str(audio_file),
            "srt_path": str(srt_file),
            "duration": round(duration, 3),
            "voice": voice,
            "text": text,
        }

    def process_storyboard(self, storyboard: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Batch process all scenes in a storyboard."""
        results = []
        for scene in storyboard.get("scenes", []):
            scene_id = scene["scene_id"]
            text = scene["text"]
            voice = scene.get("voice_id", "es-ES-AlvaroNeural")
            audio_info = self.generate_scene_audio(scene_id, text, voice)
            # Update scene with real duration
            scene["duration"] = audio_info["duration"]
            scene["audio_path"] = audio_info["audio_path"]
            scene["srt_path"] = audio_info["srt_path"]
            results.append(audio_info)
        return results
