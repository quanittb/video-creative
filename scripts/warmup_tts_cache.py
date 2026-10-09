"""Pre-generate TTS audio samples for instant preview in Video Creative Studio."""

import asyncio
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time

ROOT_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
LOCALAPPDATA = pathlib.Path(os.environ.get("LOCALAPPDATA", r"C:\Users\quant\AppData\Local"))
CACHE_DIR = ROOT_DIR / "data" / "tts_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

if sys.platform == "win32":
    try:
        if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

SAMPLE_VI = "Xin chào, đây là giọng đọc thử cho phần thuyết minh."
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def get_cache_key(canonical_voice: str, text: str) -> str:
    raw = f"{canonical_voice.strip()}::{text.strip()}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def warmup_vieneu():
    print("[*] Bắt đầu tạo cache cho 37 giọng VieNeu...")
    py_exe = LOCALAPPDATA / "Prostudio" / "components" / "tts-vieneu" / "python" / "python.exe"
    worker = ROOT_DIR / "runners" / "vieneu_tts_worker.py"
    custom_json = ROOT_DIR / "data" / "vieneu" / "custom-voices.json"

    if not (py_exe.exists() and worker.exists() and custom_json.exists()):
        print("[-] VieNeu không khả dụng, bỏ qua.")
        return

    presets = list(json.loads(custom_json.read_text(encoding="utf-8")).get("presets", {}).keys())
    print(f"[*] Tìm thấy {len(presets)} giọng VieNeu cần kiểm tra...")

    to_generate = []
    for voice_name in presets:
        c_id = f"vieneu:{voice_name}"
        ck = get_cache_key(c_id, SAMPLE_VI)
        target = CACHE_DIR / f"{ck}.mp3"
        if not (target.exists() and target.stat().st_size > 1000):
            to_generate.append(voice_name)

    if not to_generate:
        print("[+] Toàn bộ giọng VieNeu đã có sẵn trong cache!")
        return

    print(f"[*] Cần sinh cache cho {len(to_generate)} giọng VieNeu...")

    env = os.environ.copy()
    env["PYTHONPATH"] = str(LOCALAPPDATA / "Prostudio" / "components" / "tts-vieneu" / "site-packages")
    env["HF_HUB_CACHE"] = str(LOCALAPPDATA / "Prostudio" / "components" / "tts-vieneu" / "models" / "hub")
    env["HF_HUB_OFFLINE"] = "1"
    env["TRANSFORMERS_OFFLINE"] = "1"
    env["EDITKUB_TTS_ENGINE_ROOT"] = str(ROOT_DIR)
    env["PROSTUDIO_TTS_VOICES_DIR"] = str(ROOT_DIR / "data" / "vieneu")
    env["PYTHONIOENCODING"] = "utf-8"

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
    ready = p.stdout.readline()

    for idx, name in enumerate(to_generate, 1):
        t0 = time.time()
        c_id = f"vieneu:{name}"
        ck = get_cache_key(c_id, SAMPLE_VI)
        target = CACHE_DIR / f"{ck}.mp3"

        req = {
            "id": f"req-{idx}",
            "command": "synthesize",
            "text": SAMPLE_VI,
            "voice": name,
            "style": "tu_nhien",
        }
        p.stdin.write(json.dumps(req, ensure_ascii=False) + "\n")
        p.stdin.flush()
        res_line = p.stdout.readline()

        if res_line:
            data = json.loads(res_line)
            if data.get("success") and data.get("audioPath"):
                src_wav = pathlib.Path(data["audioPath"])
                cmd = ["ffmpeg", "-y", "-i", str(src_wav), "-b:a", "192k", str(target)]
                subprocess.run(cmd, capture_output=True, creationflags=CREATE_NO_WINDOW)
                elapsed = round(time.time() - t0, 2)
                print(f"  [{idx}/{len(to_generate)}] VieNeu: {name.encode('ascii', 'backslashreplace').decode()} -> {elapsed}s")
            else:
                print(f"  [-] Lỗi: {data.get('error')}")

    p.stdin.close()
    p.terminate()
    print("[+] Hoàn tất nạp cache VieNeu!")


def warmup_capcut():
    from runners.studio_bridge import synthesize_capcut

    active_capcut = [
        "BV421_vivn_streaming",
        "BV074_streaming",
        "BV562_streaming",
        "vi_female_huong",
        "BV560_streaming",
        "BV075_streaming",
        "multi_male_felipe_uranus_bigtts",
        "multi_female_richgirl_uranus_bigtts",
        "BV074_streaming_dsp",
        "BV075_streaming_vibrato_dsp",
        "BV075_streaming_demon_dsp",
        "multi_female_yangguangnv_uranus_bigtts",
    ]

    print(f"[*] Bắt đầu kiểm tra {len(active_capcut)} giọng CapCut...")

    for idx, v_id in enumerate(active_capcut, 1):
        c_id = f"capcut:{v_id}"
        ck = get_cache_key(c_id, SAMPLE_VI)
        target = CACHE_DIR / f"{ck}.mp3"
        if target.exists() and target.stat().st_size > 1000:
            print(f"  [{idx}/{len(active_capcut)}] CapCut: {v_id} -> Đã có trong cache")
            continue

        t0 = time.time()
        try:
            dur = synthesize_capcut(
                text=SAMPLE_VI,
                voice_id=v_id,
                out_path=target,
            )
            elapsed = round(time.time() - t0, 2)
            print(f"  [{idx}/{len(active_capcut)}] CapCut: {v_id} -> {elapsed}s (dur: {dur}s)")
        except Exception as e:
            print(f"  [-] Lỗi CapCut {v_id}: {e}")

    print("[+] Hoàn tất nạp cache CapCut!")


async def warmup_edge():
    from runners.studio_bridge import synthesize_edge_tts

    edge_voices = ["vi-VN-NamMinhNeural", "vi-VN-HoaiMyNeural"]
    print(f"[*] Bắt đầu kiểm tra {len(edge_voices)} giọng Edge-TTS...")

    for idx, v_id in enumerate(edge_voices, 1):
        ck = get_cache_key(v_id, SAMPLE_VI)
        target = CACHE_DIR / f"{ck}.mp3"
        if target.exists() and target.stat().st_size > 1000:
            print(f"  [{idx}/{len(edge_voices)}] Edge: {v_id} -> Đã có trong cache")
            continue

        t0 = time.time()
        try:
            dur = await synthesize_edge_tts(SAMPLE_VI, v_id, target)
            elapsed = round(time.time() - t0, 2)
            print(f"  [{idx}/{len(edge_voices)}] Edge: {v_id} -> {elapsed}s (dur: {dur}s)")
        except Exception as e:
            print(f"  [-] Lỗi Edge {v_id}: {e}")

    print("[+] Hoàn tất nạp cache Edge-TTS!")


def main():
    warmup_vieneu()
    warmup_capcut()
    asyncio.run(warmup_edge())
    print(f"[SUCCESS] Tổng số file cache hiện tại: {len(list(CACHE_DIR.glob('*.mp3')))}")


if __name__ == "__main__":
    main()
