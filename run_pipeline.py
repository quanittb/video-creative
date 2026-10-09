#!/usr/bin/env python3
"""Main Pipeline Orchestrator: From Script + Character Angles to Production Video."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List

# Ensure UTF-8 output
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("PYTHONUTF8", "1")
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Add workspace root to sys.path
ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR))

from core.script_director import ScriptDirector
from core.tts_engine import TTSEngine
from core.lipsync_engine import LipsyncEngine
from core.video_composer import VideoComposer


def find_character_assets(char_dir: Path) -> Dict[str, str]:
    """Index available character angle images."""
    assets = {}
    valid_exts = {".png", ".jpg", ".jpeg", ".webp"}
    if char_dir.exists():
        for f in char_dir.iterdir():
            if f.suffix.lower() in valid_exts:
                # Key by filename stem, e.g. 'angle_front', 'angle_45'
                assets[f.stem] = str(f)
    return assets


def run_pipeline(
    script_path: str,
    lang: str = "es",
    voice_gender: str = "male",
    char_dir_path: str = "assets/characters",
    bg_dir_path: str = "assets/backgrounds",
    output_path: str = "output/final_video.mp4",
) -> str:
    start_time = time.time()
    print("=" * 60)
    print("🎬 VIDEO CREATIVE STUDIO - PIPELINE EXECUTION")
    print(f"Target Language: {lang.upper()} | Voice: {voice_gender}")
    print("=" * 60)

    # 1. Read input script
    script_p = Path(script_path)
    if not script_p.is_file():
        raise FileNotFoundError(f"Script file not found: {script_path}")
    with open(script_p, "r", encoding="utf-8") as f:
        raw_script = f.read().strip()
    print(f"\n[Step 1/5] Loaded Script ({len(raw_script)} characters)")

    # 2. Discover character angle assets
    char_p = ROOT_DIR / char_dir_path
    char_map = find_character_assets(char_p)
    if not char_map:
        # Fallback to sample frames if available
        sample_frames = list(ROOT_DIR.glob("sample_frame_*.jpg"))
        if sample_frames:
            char_map = {f.stem: str(f) for f in sample_frames}
        else:
            print("[Warning] No character images found. Will use solid fallback visual.")
            char_map = {"default": str(ROOT_DIR / "assets" / "characters" / "default.png")}
    print(f"[Step 2/5] Indexed {len(char_map)} character angles: {list(char_map.keys())}")

    # 3. Decompose script into storyboard JSON
    print("\n[Step 3/5] AI Director decomposing script into multi-camera scenes...")
    director = ScriptDirector()
    storyboard = director.decompose_script(
        raw_script,
        lang=lang,
        voice_gender=voice_gender,
        character_angles=list(char_map.keys()),
    )
    print(f"   Generated {len(storyboard['scenes'])} scenes with dynamic pacing:")
    for sc in storyboard["scenes"]:
        print(f"   - Scene {sc['scene_id']:02d} [{sc['type']} - {sc['camera_shot']}]: {sc['text'][:45]}... (Pose: {sc['character_angle']})")

    # Save storyboard JSON for audit / inspection
    storyboard_file = ROOT_DIR / "temp" / "storyboard.json"
    storyboard_file.parent.mkdir(parents=True, exist_ok=True)
    with open(storyboard_file, "w", encoding="utf-8") as f:
        json.dump(storyboard, f, ensure_ascii=False, indent=2)

    # 4. Generate audio and subtitles via TTS Engine
    print("\n[Step 4/5] Multilingual TTS synthesis & word-level subtitle generation...")
    tts = TTSEngine()
    tts.process_storyboard(storyboard)
    total_audio_sec = sum(sc["duration"] for sc in storyboard["scenes"])
    print(f"   Audio complete: Total speech time = {total_audio_sec:.1f}s")

    # 5. Lip-Sync & Video Compositing
    print("\n[Step 5/5] Compositing scenes (Multi-angle switching + Lip-sync + Video Background)...")
    lipsync = LipsyncEngine()
    composer = VideoComposer()
    rendered_scene_paths: List[str] = []

    # Check for background video
    bg_p = ROOT_DIR / bg_dir_path
    bg_videos = list(bg_p.glob("*.mp4")) if bg_p.exists() else []
    default_bg = str(bg_videos[0]) if bg_videos else None

    for sc in storyboard["scenes"]:
        sc_id = sc["scene_id"]
        pose_key = sc.get("character_angle", list(char_map.keys())[0])
        char_visual = char_map.get(pose_key, list(char_map.values())[0])

        # Generate lip-synced character clip
        char_clip = ROOT_DIR / "temp" / f"charsync_scene_{sc_id:03d}.mp4"
        lipsync.sync(
            character_visual=char_visual,
            audio_path=sc["audio_path"],
            output_video=str(char_clip),
        )

        # Composite scene with background, camera punch-in, and layout
        scene_clip = composer.render_scene(
            scene=sc,
            character_video=str(char_clip),
            bg_video=default_bg,
        )
        rendered_scene_paths.append(scene_clip)

    # 6. Concatenate all scenes into final video
    final_out = ROOT_DIR / output_path
    final_out.parent.mkdir(parents=True, exist_ok=True)
    stitched_video = ROOT_DIR / "temp" / "stitched_temp.mp4"
    composer.concatenate_scenes(rendered_scene_paths, str(stitched_video))

    # Apply BGM & merge subtitles
    bgm_candidates = list((ROOT_DIR / "assets" / "audio").glob("*.mp3"))
    bgm_file = str(bgm_candidates[0]) if bgm_candidates else None
    
    # Combine individual scene srt files into a single master srt if needed
    composer.apply_bgm_and_subtitles(
        main_video=str(stitched_video),
        output_final=str(final_out),
        bgm_path=bgm_file,
    )

    elapsed = time.time() - start_time
    print("\n" + "=" * 60)
    print(f"🎉 RENDER SUCCESSFUL! Output saved to: {final_out}")
    print(f"⏱️ Total processing time: {elapsed:.2f}s for {total_audio_sec:.1f}s of video")
    print("=" * 60)
    return str(final_out)


def main():
    parser = argparse.ArgumentParser(description="Video Creative Studio Automated Pipeline")
    parser.add_argument("--script", default="test_samples/script_spanish_sample.txt", help="Path to input script")
    parser.add_argument("--lang", default="es", choices=["es", "en", "vi", "fr", "de"], help="Target language")
    parser.add_argument("--gender", default="male", choices=["male", "female"], help="Voice gender")
    parser.add_argument("--characters", default="assets/characters", help="Directory of character images")
    parser.add_argument("--backgrounds", default="assets/backgrounds", help="Directory of background videos")
    parser.add_argument("--output", default="output/final_video.mp4", help="Output video file path")

    args = parser.parse_args()
    run_pipeline(
        script_path=args.script,
        lang=args.lang,
        voice_gender=args.gender,
        char_dir_path=args.characters,
        bg_dir_path=args.backgrounds,
        output_path=args.output,
    )


if __name__ == "__main__":
    main()
