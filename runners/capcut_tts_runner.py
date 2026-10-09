#!/usr/bin/env python3
"""JSON-line bridge for the K07VN/capcut-tts-api Python SDK."""

import json
import sys
import time
from typing import Any

from capcut_tts_api import CapCutClient


def list_voices(client: CapCutClient, language: str | None) -> dict[str, Any]:
    voices = client.list_voices(lang=language or None)
    return {
        "success": True,
        "voices": [
            {
                "voice_type": voice.voice_type,
                "display_name": voice.display_name,
                "resource_id": voice.resource_id,
                "lang": voice.lang,
                "lan": voice.lan,
            }
            for voice in voices
        ],
    }


def synthesize(client: CapCutClient, request: dict[str, Any]) -> dict[str, Any]:
    text = str(request.get("text") or "").strip()
    voice = str(request.get("voice") or "").strip()
    rate = str(request.get("rate") or "1.0")
    if not text or not voice:
        raise ValueError("text and voice are required")

    created = client.create_tts_task(texts=text, voice=voice, rate=rate)
    tasks = (created.get("data") or {}).get("tasks") or []
    if not tasks:
        raise RuntimeError(f"CapCut did not return a TTS task: {created}")

    task_id = tasks[0]["id"]
    token = tasks[0]["token"]
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        queried = client.query_tts_task(task_id, token)
        query_tasks = (queried.get("data") or {}).get("tasks") or []
        if query_tasks:
            task = query_tasks[0]
            status = str(task.get("status") or "").lower()
            if status in {"success", "succeed"}:
                payload = task.get("payload") or "{}"
                if isinstance(payload, str):
                    payload = json.loads(payload)
                subtitles = payload.get("audio_subtitles") or []
                if not subtitles or not subtitles[0].get("speech_url"):
                    raise RuntimeError("CapCut task completed without an audio URL")
                audio = subtitles[0]
                return {
                    "success": True,
                    "audio_url": audio["speech_url"],
                    "duration_ms": audio.get("duration"),
                }
            if status in {"failed", "fail"}:
                raise RuntimeError(f"CapCut TTS task failed: {task}")
        time.sleep(0.35)
    raise TimeoutError("CapCut TTS task timed out after 90 seconds")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8", errors="strict")
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    request = json.loads(sys.stdin.read() or "{}")
    client = CapCutClient()
    command = request.get("command")
    if command == "voices":
        result = list_voices(client, request.get("language"))
    elif command == "synthesize":
        result = synthesize(client, request)
    else:
        raise ValueError(f"Unsupported command: {command}")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False))
        raise SystemExit(1)

