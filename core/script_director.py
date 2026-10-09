"""Script Director: Intelligent scene splitter and multi-camera director for video generation."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


class ScriptDirector:
    """Orchestrates script decomposition into high-retention multi-scene storyboards."""

    def __init__(self, api_key: Optional[str] = None, settings_path: Optional[str] = None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.settings = self._load_settings(settings_path)

    @staticmethod
    def _load_settings(path: Optional[str]) -> Dict[str, Any]:
        default_path = Path(__file__).resolve().parent.parent / "config" / "settings.json"
        target = Path(path) if path else default_path
        if target.exists():
            with open(target, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def decompose_script(
        self,
        script_text: str,
        lang: str = "es",
        voice_gender: str = "male",
        character_angles: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Convert a continuous script into an optimized storyboard JSON.

        If Gemini API key is available, uses LLM for director logic.
        Otherwise, falls back to a deterministic sentence-based director algorithm.
        """
        angles = character_angles or ["angle_front", "angle_45_left", "angle_closeup"]
        voices = self.settings.get("tts_voices", {}).get(lang, {})
        voice_id = voices.get(f"voice_{voice_gender}", "es-ES-AlvaroNeural")

        if self.api_key:
            try:
                return self._decompose_with_llm(script_text, lang, voice_id, angles)
            except Exception as e:
                print(f"[ScriptDirector] LLM call failed ({e}), falling back to deterministic splitter.")

        return self._decompose_deterministic(script_text, lang, voice_id, angles)

    def _decompose_with_llm(
        self,
        script_text: str,
        lang: str,
        voice_id: str,
        angles: List[str],
    ) -> Dict[str, Any]:
        import google.generativeai as genai

        genai.configure(api_key=self.api_key)
        model = genai.GenerativeModel("gemini-2.0-flash")

        system_instruction = f"""
You are an expert Social Media Video Director (TikTok/Reels/Shorts).
Your job is to break a raw script in language '{lang}' into high-retention scenes (each 3 to 6 seconds).
Available character angles: {angles}.
Available scene types: "HOOK", "EXPLAIN", "B_ROLL_CUTAWAY", "PUNCHLINE", "CALL_TO_ACTION".
Available layouts: "FULL_CHARACTER", "SPLIT_SCREEN", "B_ROLL_FULL", "PIP".
Available camera shots: "WIDE", "MEDIUM", "CLOSE_UP".

Rules:
1. First scene MUST be HOOK with 'angle_front' and 'WIDE' or 'CLOSE_UP' shot.
2. Change character angles or layout every 3-5 seconds to maintain high viewer retention.
3. Every 2-3 scenes, add a 'B_ROLL_CUTAWAY' or 'SPLIT_SCREEN' with relevant b_roll_keyword in English for stock search.
4. Output STRICT JSON format only, matching this schema:
{{
  "project_title": "Video Project",
  "language": "{lang}",
  "total_scenes": <int>,
  "scenes": [
    {{
      "scene_id": 1,
      "type": "HOOK",
      "text": "sentence text in {lang}",
      "character_angle": "{angles[0]}",
      "camera_shot": "WIDE",
      "layout": "FULL_CHARACTER",
      "b_roll_keyword": "dramatic attention hook",
      "background_video": "modern_dark_studio.mp4",
      "voice_id": "{voice_id}",
      "sfx": "whoosh_impact.mp3"
    }}
  ]
}}
"""
        response = model.generate_content(
            f"{system_instruction}\n\nRAW SCRIPT TO DIRECT:\n{script_text}"
        )
        cleaned = re.sub(r"^```json\s*", "", response.text.strip())
        cleaned = re.sub(r"\s*```$", "", cleaned)
        return json.loads(cleaned)

    def _decompose_deterministic(
        self,
        script_text: str,
        lang: str,
        voice_id: str,
        angles: List[str],
    ) -> Dict[str, Any]:
        """Deterministic splitter that segments sentences and alternates angles/layouts."""
        # Split text by sentence endings
        raw_sentences = [
            s.strip()
            for s in re.split(r"(?<=[.!?¡¿])\s+", script_text.strip())
            if s.strip()
        ]
        if not raw_sentences:
            raw_sentences = [script_text.strip()]

        scenes: List[Dict[str, Any]] = []
        angle_count = len(angles)

        for i, sentence in enumerate(raw_sentences):
            scene_id = i + 1
            if i == 0:
                scene_type = "HOOK"
                angle = angles[0]
                shot = "CLOSE_UP"
                layout = "FULL_CHARACTER"
                sfx = "whoosh_impact.mp3"
                b_roll_kw = "attention dramatic"
            elif i == len(raw_sentences) - 1:
                scene_type = "CALL_TO_ACTION"
                angle = angles[0]
                shot = "MEDIUM"
                layout = "FULL_CHARACTER"
                sfx = "ding_bell.mp3"
                b_roll_kw = "subscribe follow action"
            elif i % 3 == 0:
                scene_type = "B_ROLL_CUTAWAY"
                angle = angles[i % angle_count]
                shot = "MEDIUM"
                layout = "B_ROLL_FULL"
                sfx = "whoosh_soft.mp3"
                b_roll_kw = "business technology workflow"
            elif i % 2 == 1:
                scene_type = "EXPLAIN"
                angle = angles[i % angle_count]
                shot = "MEDIUM"
                layout = "FULL_CHARACTER"
                sfx = "pop_click.mp3"
                b_roll_kw = "conversation talking"
            else:
                scene_type = "PUNCHLINE"
                angle = angles[-1] if len(angles) > 1 else angles[0]
                shot = "CLOSE_UP"
                layout = "SPLIT_SCREEN"
                sfx = "whoosh_fast.mp3"
                b_roll_kw = "data analysis chart"

            scenes.append({
                "scene_id": scene_id,
                "type": scene_type,
                "text": sentence,
                "character_angle": angle,
                "camera_shot": shot,
                "layout": layout,
                "b_roll_keyword": b_roll_kw,
                "background_video": "modern_studio_loop.mp4",
                "voice_id": voice_id,
                "sfx": sfx,
            })

        return {
            "project_title": "Auto Generated Video Project",
            "language": lang,
            "total_scenes": len(scenes),
            "scenes": scenes,
        }
