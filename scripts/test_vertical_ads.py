#!/usr/bin/env python3
"""Measure Echo/MuseTalk runs, calibrate lip crops, and export verified vertical MP4s."""

from __future__ import annotations

import argparse
import csv
import datetime as _datetime
import json
import math
import os
import subprocess
import sys
import time
import uuid
import wave
from array import array
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

SCRIPT_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_ROOT.parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import echo_flash_windows as echo
import test_cached_musetalk as musetalk


FPS = 25
EXPORT_WIDTH = 1080
EXPORT_HEIGHT = 1920
DEFAULT_DURATION = 60.0
DEFAULT_CACHE_DIR = Path(r"C:\vcs_cache")
PROFILE_NAMES = ("F10", "A10", "A10HQ")
PAUSE_RMS_THRESHOLD_DBFS = -60.0
PAUSE_MIN_DURATION_SECONDS = 0.32
PAUSE_FORCE_MIN_DURATION_SECONDS = 0.16
PAUSE_ANALYSIS_WINDOW_SECONDS = 0.02
PAUSE_MAX_INTERRUPTION_SECONDS = 0.04
PAUSE_TRANSITION_SECONDS = 0.08
AUDIO_OFFSET_STEP_MS = 40
AUDIO_OFFSET_LIMIT_MS = 160


def resolve_project_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def probe_media(path: Path, ffprobe: str) -> Dict[str, Any]:
    return echo.probe_media(path, ffprobe)


def stream_by_type(data: Mapping[str, Any], stream_type: str) -> Optional[Mapping[str, Any]]:
    return next((item for item in data.get("streams", []) if item.get("codec_type") == stream_type), None)


def media_duration(data: Mapping[str, Any], stream: Mapping[str, Any]) -> float:
    fallback = float((data.get("format") or {}).get("duration") or 0.0)
    return echo.stream_duration(stream, fallback)


def is_vertical_9_16(width: int, height: int) -> bool:
    if width <= 0 or height <= 0:
        return False
    return math.isclose(width / float(height), 9.0 / 16.0, rel_tol=1e-4, abs_tol=1e-6)


def build_vertical_video_filter(source_width: int, source_height: int) -> Tuple[str, str, str]:
    """Build an HD resize or a no-crop contain composite for an existing base video."""
    if is_vertical_9_16(source_width, source_height):
        return "-vf", "scale=1080:1920:flags=lanczos,setsar=1", "native_9_16_lanczos_upscale"
    graph = (
        "[0:v]split=2[bg][fg];"
        "[bg]scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,"
        "crop=1080:1920,gblur=sigma=36:steps=2[bg];"
        "[fg]scale=1080:1920:force_original_aspect_ratio=decrease:flags=lanczos[fg];"
        "[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[vout]"
    )
    return "-filter_complex", graph, "contain_foreground_blurred_same_video_background"


def detect_silence_intervals(
    wav_path: Path,
    threshold_dbfs: float = PAUSE_RMS_THRESHOLD_DBFS,
    min_duration_seconds: float = PAUSE_MIN_DURATION_SECONDS,
    window_seconds: float = PAUSE_ANALYSIS_WINDOW_SECONDS,
    merge_gap_seconds: float = PAUSE_MAX_INTERRUPTION_SECONDS,
) -> List[Dict[str, float]]:
    """Detect sustained pauses while protecting globally quiet speech and brief stop sounds."""
    if not math.isfinite(threshold_dbfs) or not -96.0 <= threshold_dbfs <= 0.0:
        raise ValueError("Pause threshold must be finite dBFS in [-96, 0].")
    if not math.isfinite(min_duration_seconds) or min_duration_seconds <= 0:
        raise ValueError("Minimum pause duration must be finite and positive.")
    if not math.isfinite(window_seconds) or window_seconds <= 0:
        raise ValueError("Pause analysis window must be finite and positive.")
    if not math.isfinite(merge_gap_seconds) or merge_gap_seconds < 0:
        raise ValueError("Pause hysteresis gap must be finite and non-negative.")
    try:
        with wave.open(str(wav_path), "rb") as audio:
            if audio.getcomptype() != "NONE" or audio.getnchannels() != 1 or audio.getsampwidth() != 2:
                raise ValueError("Pause detection requires uncompressed 16-bit mono PCM WAV.")
            sample_rate = audio.getframerate()
            if sample_rate != 16000:
                raise ValueError("Pause detection requires the normalized 16 kHz MuseTalk WAV.")
            sample_count = audio.getnframes()
            pcm = array("h")
            pcm.frombytes(audio.readframes(sample_count))
    except (OSError, wave.Error) as error:
        raise RuntimeError("Could not read normalized audio for pause detection: {}".format(error)) from error
    if sys.byteorder != "little":
        pcm.byteswap()
    if not pcm:
        raise ValueError("Normalized audio WAV has no samples.")

    window_samples = max(1, int(round(sample_rate * window_seconds)))
    window_dbfs: List[float] = []
    for offset in range(0, len(pcm), window_samples):
        samples = pcm[offset:offset + window_samples]
        rms = math.sqrt(sum(sample * sample for sample in samples) / float(len(samples)))
        window_dbfs.append(-120.0 if rms <= 0 else 20.0 * math.log10(rms / 32768.0))

    # If a recording contains quiet speech, a fixed threshold can mistake it for
    # silence. Anchor the gate below the lower active-level percentile; when ambient
    # noise makes silence ambiguous, prefer leaving the mouth untouched.
    active_levels = sorted(level for level in window_dbfs if level > -90.0)
    if active_levels:
        reference_level = active_levels[min(len(active_levels) - 1, int((len(active_levels) - 1) * 0.10))]
        effective_threshold_dbfs = min(threshold_dbfs, reference_level - 12.0)
    else:
        effective_threshold_dbfs = threshold_dbfs
    low_windows = [level <= effective_threshold_dbfs for level in window_dbfs]

    # Bridge only threshold-near energy dips inside a candidate pause. A distinct
    # plosive or syllable is kept as speech even when it is shorter than the gap bound.
    max_gap_windows = int(math.floor(merge_gap_seconds / window_seconds + 1e-9))
    if max_gap_windows:
        index = 0
        while index < len(low_windows):
            if low_windows[index]:
                index += 1
                continue
            gap_start = index
            while index < len(low_windows) and not low_windows[index]:
                index += 1
            if (gap_start > 0 and index < len(low_windows) and low_windows[gap_start - 1]
                    and low_windows[index] and index - gap_start <= max_gap_windows
                    and all(level <= effective_threshold_dbfs + 6.0 for level in window_dbfs[gap_start:index])):
                low_windows[gap_start:index] = [True] * (index - gap_start)

    intervals: List[Dict[str, float]] = []
    run_start: Optional[int] = None
    total_seconds = len(pcm) / float(sample_rate)
    for index, is_low in enumerate(low_windows + [False]):
        if is_low and run_start is None:
            run_start = index
        elif not is_low and run_start is not None:
            start = run_start * window_samples / float(sample_rate)
            end = min(index * window_samples / float(sample_rate), total_seconds)
            if end - start >= min_duration_seconds:
                intervals.append({"start_seconds": round(start, 6), "end_seconds": round(end, 6),
                                  "duration_seconds": round(end - start, 6)})
            run_start = None
    return intervals


def pingpong_frame_index(frame_index: int, source_frame_count: int) -> int:
    """Match MuseTalk's frame_list + frame_list[::-1] modulo mapping exactly."""
    if source_frame_count < 1:
        raise ValueError("Source frame count must be positive.")
    if frame_index < 0:
        raise ValueError("Output frame index cannot be negative.")
    position = frame_index % (2 * source_frame_count)
    return position if position < source_frame_count else 2 * source_frame_count - 1 - position


def split_pause_intervals_by_reference_audio(
    output_pause_intervals: Sequence[Mapping[str, float]],
    reference_pause_intervals: Sequence[Mapping[str, float]],
    source_frame_count: int,
    duration_seconds: float,
    fps: int = FPS,
) -> Tuple[List[Dict[str, float]], List[Dict[str, float]]]:
    """Return output-time intervals whose output and mapped source frame are both in pauses."""
    if source_frame_count < 2 or fps < 1 or not math.isfinite(duration_seconds) or duration_seconds <= 0:
        raise ValueError("Pause mapping requires valid source frames, FPS and duration.")

    def covers_frame(intervals: Sequence[Mapping[str, float]], start: float, end: float) -> bool:
        return any(float(interval["start_seconds"]) <= start + 1e-9
                   and float(interval["end_seconds"]) >= end - 1e-9 for interval in intervals)

    frame_count = int(math.ceil(duration_seconds * fps - 1e-9))
    requested: List[bool] = []
    safe: List[bool] = []
    for frame_index in range(frame_count):
        start = frame_index / float(fps)
        end = min((frame_index + 1) / float(fps), duration_seconds)
        output_is_pause = end > start and covers_frame(output_pause_intervals, start, end)
        requested.append(output_is_pause)
        if not output_is_pause:
            safe.append(False)
            continue
        source_index = pingpong_frame_index(frame_index, source_frame_count)
        source_start = source_index / float(fps)
        source_end = (source_index + 1) / float(fps)
        safe.append(covers_frame(reference_pause_intervals, source_start, source_end))

    def to_intervals(mask: Sequence[bool]) -> List[Dict[str, float]]:
        intervals: List[Dict[str, float]] = []
        run_start: Optional[int] = None
        for index, enabled in enumerate(list(mask) + [False]):
            if enabled and run_start is None:
                run_start = index
            elif not enabled and run_start is not None:
                start = run_start / float(fps)
                end = min(index / float(fps), duration_seconds)
                intervals.append({"start_seconds": round(start, 6), "end_seconds": round(end, 6),
                                  "duration_seconds": round(end - start, 6)})
                run_start = None
        return intervals

    return to_intervals(safe), to_intervals([wanted and not allowed for wanted, allowed in zip(requested, safe)])


def validate_audio_offset_ms(value: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("Audio offset phải là số nguyên mili-giây.")
    if abs(value) > AUDIO_OFFSET_LIMIT_MS or value % AUDIO_OFFSET_STEP_MS:
        raise ValueError("--audio-offset-ms chỉ nhận bội số 40 trong khoảng -160..160 ms.")
    return value


def _normalized_wav_info(path: Path) -> Dict[str, Any]:
    try:
        with wave.open(str(path), "rb") as audio:
            params = audio.getparams()
            if (audio.getcomptype() != "NONE" or params.nchannels != 1 or params.sampwidth != 2
                    or params.framerate != 16000):
                raise ValueError("Audio conditioning requires normalized 16 kHz mono PCM16 WAV.")
            return {"sample_rate": params.framerate, "sample_count": params.nframes,
                    "duration_seconds": round(params.nframes / float(params.framerate), 6)}
    except (OSError, wave.Error) as error:
        raise RuntimeError("Could not inspect normalized PCM WAV: {}".format(error)) from error


def _read_normalized_pcm(path: Path) -> Tuple[wave._wave_params, array]:
    try:
        with wave.open(str(path), "rb") as audio:
            params = audio.getparams()
            if (audio.getcomptype() != "NONE" or params.nchannels != 1 or params.sampwidth != 2
                    or params.framerate != 16000):
                raise ValueError("Audio conditioning requires normalized 16 kHz mono PCM16 WAV.")
            pcm = array("h")
            pcm.frombytes(audio.readframes(params.nframes))
    except (OSError, wave.Error) as error:
        raise RuntimeError("Could not read normalized PCM WAV: {}".format(error)) from error
    if sys.byteorder != "little":
        pcm.byteswap()
    if len(pcm) != params.nframes:
        raise ValueError("Normalized WAV frame count did not match its decoded PCM samples.")
    return params, pcm


def _write_normalized_pcm(destination: Path, params: wave._wave_params, pcm: array, purpose: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name("." + destination.name + ".tmp")
    if destination.exists() or temporary.exists():
        raise FileExistsError("Refusing to overwrite {} WAV: {}".format(purpose, destination))
    try:
        with wave.open(str(temporary), "wb") as output_wav:
            output_wav.setnchannels(params.nchannels)
            output_wav.setsampwidth(params.sampwidth)
            output_wav.setframerate(params.framerate)
            data = pcm.tobytes()
            if sys.byteorder != "little":
                emitted = array("h", pcm)
                emitted.byteswap()
                data = emitted.tobytes()
            output_wav.writeframes(data)
        os.replace(str(temporary), str(destination))
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def gate_pause_audio(
    source: Path,
    destination: Path,
    min_pause_seconds: float = PAUSE_MIN_DURATION_SECONDS,
) -> Dict[str, Any]:
    """Zero only RMS/hysteresis-confirmed pauses in the MuseTalk conditioning WAV."""
    intervals = detect_silence_intervals(source, min_duration_seconds=min_pause_seconds)
    params, pcm = _read_normalized_pcm(source)
    gated_intervals: List[Dict[str, Any]] = []
    gated_sample_count = 0
    changed_sample_count = 0
    for interval in intervals:
        start_sample = max(0, min(len(pcm), int(round(interval["start_seconds"] * params.framerate))))
        end_sample = max(start_sample, min(len(pcm), int(round(interval["end_seconds"] * params.framerate))))
        if end_sample <= start_sample:
            continue
        changed_sample_count += sum(sample != 0 for sample in pcm[start_sample:end_sample])
        pcm[start_sample:end_sample] = array("h", [0]) * (end_sample - start_sample)
        gated_sample_count += end_sample - start_sample
        gated_intervals.append({**interval, "start_sample": start_sample, "end_sample": end_sample,
                                "sample_count": end_sample - start_sample})
    _write_normalized_pcm(destination, params, pcm, "pause-gated conditioning")
    return {
        "status": "applied" if gated_intervals else "no_qualifying_pauses",
        "method": "digital-zero PCM16 gate before MuseTalk Whisper feature extraction",
        "source": str(source.resolve()),
        "source_sha256": musetalk.sha256_file(source),
        "path": str(destination.resolve()),
        "sha256": musetalk.sha256_file(destination),
        "sample_rate": params.framerate,
        "sample_count": len(pcm),
        "duration_seconds": round(len(pcm) / float(params.framerate), 6),
        "minimum_pause_seconds": min_pause_seconds,
        "interval_count": len(gated_intervals),
        "gated_sample_count": gated_sample_count,
        "gated_duration_seconds": round(gated_sample_count / float(params.framerate), 6),
        "changed_nonzero_sample_count": changed_sample_count,
        "intervals": gated_intervals,
        "output_audio_unchanged": True,
    }


def _disabled_pause_gate_record(audio_path: Path, policy: str) -> Dict[str, Any]:
    info = _normalized_wav_info(audio_path)
    digest = musetalk.sha256_file(audio_path)
    return {
        "status": "disabled", "requested_policy": policy,
        "method": "none; pause gating disabled by CLI",
        "source": str(audio_path.resolve()), "source_sha256": digest,
        "path": str(audio_path.resolve()), "sha256": digest,
        **info, "minimum_pause_seconds": None, "interval_count": 0,
        "gated_sample_count": 0, "gated_duration_seconds": 0.0,
        "changed_nonzero_sample_count": 0, "intervals": [], "output_audio_unchanged": True,
    }


def _offset_pause_intervals(
    intervals: Sequence[Mapping[str, Any]], sample_count: int, offset_ms: int,
    sample_rate: int = 16000,
) -> List[Dict[str, Any]]:
    shift = abs(offset_ms) * sample_rate // 1000
    direction = 1 if offset_ms > 0 else -1 if offset_ms < 0 else 0
    moved: List[Dict[str, Any]] = []
    for interval in intervals:
        start = max(0, min(sample_count, int(interval["start_sample"]) + direction * shift))
        end = max(0, min(sample_count, int(interval["end_sample"]) + direction * shift))
        if end <= start:
            continue
        moved.append({"start_seconds": round(start / float(sample_rate), 6),
                      "end_seconds": round(end / float(sample_rate), 6),
                      "duration_seconds": round((end - start) / float(sample_rate), 6),
                      "start_sample": start, "end_sample": end, "sample_count": end - start})
    return moved


def shift_pcm_wav(source: Path, destination: Path, offset_ms: int) -> Dict[str, Any]:
    """Shift normalized PCM for MuseTalk conditioning; positive delays mouth timing."""
    validate_audio_offset_ms(offset_ms)
    try:
        params, pcm = _read_normalized_pcm(source)
    except (OSError, wave.Error) as error:
        raise RuntimeError("Could not read normalized PCM for audio offset: {}".format(error)) from error
    sample_count = params.nframes
    if len(pcm) != sample_count:
        raise ValueError("Normalized WAV frame count did not match its decoded PCM samples.")
    shift_samples = abs(offset_ms) * params.framerate // 1000
    if shift_samples >= sample_count and sample_count:
        raise ValueError("Audio offset exceeds the normalized audio length.")
    shifted = array("h")
    if offset_ms > 0:
        shifted.extend([0] * shift_samples)
        shifted.extend(pcm[:sample_count - shift_samples])
    elif offset_ms < 0:
        shifted.extend(pcm[shift_samples:])
        shifted.extend([0] * shift_samples)
    else:
        shifted = pcm
    _write_normalized_pcm(destination, params, shifted, "audio-offset conditioning")
    return {"offset_ms": offset_ms, "conditioning_sign": "positive delays mouth; negative advances mouth",
            "sample_offset": shift_samples, "sample_rate": params.framerate,
            "duration_seconds": round(sample_count / float(params.framerate), 6),
            "original_audio_preserved_for_output": True}


def count_video_frames(path: Path, ffprobe: str) -> int:
    result = subprocess.run(
        [ffprobe, "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
         "stream=nb_read_frames", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace", check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("ffprobe could not count video frames for {}: {}".format(path, result.stderr.strip()))
    try:
        frame_count = int(result.stdout.strip())
    except ValueError as error:
        raise RuntimeError("ffprobe did not return a decoded frame count for {}.".format(path)) from error
    if frame_count < 2:
        raise ValueError("Motion base needs at least two decoded frames for ping-pong mapping.")
    return frame_count


def _pause_alpha_expression(intervals: Sequence[Mapping[str, float]], transition_seconds: float, fps: int) -> str:
    if not intervals:
        return "0"
    if not math.isfinite(transition_seconds) or transition_seconds <= 0:
        raise ValueError("Pause transition duration must be finite and positive.")
    expressions = []
    for interval in intervals:
        start = float(interval["start_seconds"])
        end = float(interval["end_seconds"])
        if not math.isfinite(start) or not math.isfinite(end) or end <= start:
            raise ValueError("Pause interval has invalid bounds.")
        start_frame = start * fps
        end_frame = end * fps
        fade = min(transition_seconds * fps, (end_frame - start_frame) / 2.0)
        expressions.append(
            "if(lt(N-1,{start}),0,if(lt(N-1,{fade_in}),((N-1)-{start})/{fade},"
            "if(lt(N-1,{fade_out}),1,if(lt(N-1,{end}),({end}-(N-1))/{fade},0))))".format(
                start=start_frame, fade_in=start_frame + fade, fade_out=end_frame - fade, end=end_frame, fade=fade,
            )
        )
    alpha = expressions[0]
    for expression in expressions[1:]:
        alpha = "max({}, {})".format(alpha, expression)
    return alpha


def build_pause_closure_filter(
    source_frame_count: int,
    duration_seconds: float,
    intervals: Sequence[Mapping[str, float]],
    fps: int = FPS,
    transition_seconds: float = PAUSE_TRANSITION_SECONDS,
) -> str:
    """Crossfade the same motion-base ping-pong frame into sustained MuseTalk pauses."""
    if source_frame_count < 2 or fps < 1 or not math.isfinite(duration_seconds) or duration_seconds <= 0:
        raise ValueError("Pause replacement requires a valid motion-base frame count, FPS and duration.")
    alpha = _pause_alpha_expression(intervals, transition_seconds, fps)
    return (
        "[0:v]fps={fps},setpts=PTS-STARTPTS[musetalk];"
        "[1:v]fps={fps},setpts=PTS-STARTPTS,split=2[motion_forward][motion_reverse_input];"
        "[motion_reverse_input]reverse,setpts=PTS-STARTPTS[motion_reverse];"
        "[motion_forward][motion_reverse]concat=n=2:v=1:a=0,"
        "loop=loop=-1:size={cycle_frames}:start=0,setpts=N/({fps}*TB),"
        "trim=duration={duration}[motion_reference];"
        "[musetalk][motion_reference]blend=all_expr='A*(1-({alpha}))+B*({alpha})':shortest=1,"
        "setpts=PTS-STARTPTS[closed]"
    ).format(fps=fps, cycle_frames=2 * source_frame_count, duration=duration_seconds, alpha=alpha)


def apply_pause_mouth_closure(
    rendered_video: Path,
    reference_motion_video: Path,
    normalized_audio: Path,
    destination: Path,
    ffmpeg: str,
    ffprobe: str,
    duration_seconds: float,
    fps: int = FPS,
    min_pause_seconds: float = PAUSE_MIN_DURATION_SECONDS,
    reference_audio: Optional[Path] = None,
) -> Dict[str, Any]:
    intervals = detect_silence_intervals(normalized_audio, min_duration_seconds=min_pause_seconds)
    source_pause_intervals = detect_silence_intervals(
        reference_audio or normalized_audio, min_duration_seconds=1.0 / fps,
    )
    frame_count = count_video_frames(reference_motion_video, ffprobe)
    safe_intervals, uncovered_intervals = split_pause_intervals_by_reference_audio(
        intervals, source_pause_intervals, frame_count, duration_seconds, fps,
    )
    record: Dict[str, Any] = {
        "status": ("no_qualifying_pauses" if not intervals else
                   "no_safe_reference_pauses" if not safe_intervals else "applied"),
        "reference_source": "existing_motion_base_video",
        "reference_video": str(reference_motion_video.resolve()),
        "reference_sha256": musetalk.sha256_file(reference_motion_video),
        "reference_audio": str((reference_audio or normalized_audio).resolve()),
        "reference_audio_sha256": musetalk.sha256_file(reference_audio or normalized_audio),
        "reference_cache_state": "not_needed; reuses existing Echo motion base",
        "pause_detection": {"method": "20 ms PCM RMS windows", "threshold_dbfs": PAUSE_RMS_THRESHOLD_DBFS,
                            "quiet_level_protection": "effective threshold is at least 12 dB below active-level 10th percentile; ambiguous background noise favors no correction",
                            "minimum_duration_seconds": min_pause_seconds,
                            "merge_interruption_seconds": PAUSE_MAX_INTERRUPTION_SECONDS,
                            "merge_condition": "bridge only gaps within 6 dB of the gate; stronger plosives/speech split the pause",
                            "transition_seconds": PAUSE_TRANSITION_SECONDS,
                            "speech_frames_preserved": True,
                            "audio_policy": "unshifted output audio stream copied unchanged with FFmpeg -c:a copy"},
        "pingpong_mapping": "frame_list + frame_list[::-1], index modulo 2N",
        "requested_intervals": intervals,
        "reference_audio_pause_intervals": source_pause_intervals,
        "intervals": safe_intervals,
        "uncovered_intervals": uncovered_intervals,
        "uncovered_duration_seconds": round(sum(item["duration_seconds"] for item in uncovered_intervals), 6),
        "mapping_policy": "restore only when the full output frame and its mapped source-frame time are both inside detected pauses",
        "fallback": "none; errors fail the job rather than claiming a corrected result",
    }
    if not intervals or not safe_intervals:
        return record

    rendered_info = probe_media(rendered_video, ffprobe)
    source_audio = stream_by_type(rendered_info, "audio")
    source_video = stream_by_type(rendered_info, "video")
    if source_audio is None or source_video is None:
        raise ValueError("MuseTalk intermediate must contain both audio and video for pause correction.")
    source_fps = echo.parse_fraction(str(source_video.get("avg_frame_rate") or "0/1"))
    if abs(source_fps - fps) > 0.01:
        raise ValueError("Pause correction requires a constant {} FPS MuseTalk intermediate.".format(fps))
    reference_info = probe_media(reference_motion_video, ffprobe)
    reference_video = stream_by_type(reference_info, "video")
    if reference_video is None:
        raise ValueError("Motion-base pause reference has no video stream.")
    reference_fps = echo.parse_fraction(str(reference_video.get("avg_frame_rate") or reference_video.get("r_frame_rate") or "0/1"))
    if (int(reference_video.get("width", 0)), int(reference_video.get("height", 0))) != (
            int(source_video.get("width", 0)), int(source_video.get("height", 0))):
        raise ValueError("Pause reference and MuseTalk output dimensions differ; refusing an unsynchronized blend.")
    if abs(reference_fps - fps) > 0.01:
        raise ValueError("Pause reference must be {} FPS for the upstream ping-pong map.".format(fps))

    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError("Refusing to overwrite pause-corrected video: {}".format(destination))
    temporary = destination.with_name("." + destination.stem + ".partial.mp4")
    if temporary.exists():
        raise FileExistsError("Pause-correction temporary already exists: {}".format(temporary))
    graph = build_pause_closure_filter(frame_count, duration_seconds, safe_intervals, fps)
    command = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(rendered_video), "-i", str(reference_motion_video),
        "-filter_complex", graph, "-map", "[closed]", "-map", "0:a:0", "-map_metadata", "0",
        "-t", "{:.6f}".format(duration_seconds), "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-pix_fmt", "yuv420p", "-fps_mode", "passthrough", "-video_track_timescale", "25000",
        "-c:a", "copy", "-movflags", "+faststart", str(temporary),
    ]
    try:
        result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, encoding="utf-8", errors="replace", check=False)
        if result.returncode != 0:
            raise RuntimeError("FFmpeg pause correction failed: {}".format(result.stderr.strip()))
        if not temporary.is_file() or temporary.stat().st_size <= 1000:
            raise RuntimeError("FFmpeg did not create a valid pause-corrected video.")
        corrected_info = probe_media(temporary, ffprobe)
        corrected_video = stream_by_type(corrected_info, "video")
        corrected_audio = stream_by_type(corrected_info, "audio")
        if corrected_video is None or corrected_audio is None:
            raise ValueError("Pause-corrected output lost a video or audio stream.")
        video_dims = (int(source_video.get("width", 0)), int(source_video.get("height", 0)))
        corrected_dims = (int(corrected_video.get("width", 0)), int(corrected_video.get("height", 0)))
        actual_fps = echo.parse_fraction(str(corrected_video.get("avg_frame_rate") or "0/1"))
        source_audio_duration = media_duration(rendered_info, source_audio)
        corrected_audio_duration = media_duration(corrected_info, corrected_audio)
        if corrected_dims != video_dims or abs(actual_fps - fps) > 0.01:
            raise ValueError("Pause-corrected video changed dimensions or FPS unexpectedly.")
        if str(corrected_audio.get("codec_name")) != str(source_audio.get("codec_name")):
            raise ValueError("Pause correction changed the MuseTalk audio codec despite stream-copy mode.")
        if abs(corrected_audio_duration - source_audio_duration) > 0.01:
            raise ValueError("Pause correction changed the MuseTalk audio duration unexpectedly.")
        os.replace(str(temporary), str(destination))
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    record["output"] = str(destination.resolve())
    record["source_frame_count"] = frame_count
    record["output_audio_codec"] = str(corrected_audio.get("codec_name"))
    record["output_audio_duration_seconds"] = round(corrected_audio_duration, 6)
    return record


def remux_unshifted_audio(
    rendered_video: Path,
    normalized_audio: Path,
    destination: Path,
    ffmpeg: str,
    ffprobe: str,
    duration_seconds: float,
) -> Dict[str, Any]:
    """Restore normalized, unshifted audio after a conditioning-only sync offset."""
    audio_info = probe_media(normalized_audio, ffprobe)
    audio_stream = stream_by_type(audio_info, "audio")
    if audio_stream is None or int(audio_stream.get("sample_rate", 0) or 0) != 16000 or int(audio_stream.get("channels", 0) or 0) != 1:
        raise ValueError("Output audio restoration requires the original normalized 16 kHz mono WAV.")
    if str(audio_stream.get("codec_name")) != "pcm_s16le":
        raise ValueError("Output audio restoration requires normalized PCM16 WAV.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name("." + destination.stem + ".partial.mp4")
    if destination.exists() or temporary.exists():
        raise FileExistsError("Refusing to overwrite audio-restored intermediate: {}".format(destination))
    command = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(rendered_video), "-i", str(normalized_audio),
        "-map", "0:v:0", "-map", "1:a:0", "-map_metadata", "0", "-t", "{:.6f}".format(duration_seconds),
        "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(temporary),
    ]
    try:
        result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, encoding="utf-8", errors="replace", check=False)
        if result.returncode != 0 or not temporary.is_file() or temporary.stat().st_size <= 1000:
            raise RuntimeError("FFmpeg could not restore unshifted output audio: {}".format(result.stderr.strip()))
        restored_info = probe_media(temporary, ffprobe)
        restored_video = stream_by_type(restored_info, "video")
        restored_audio = stream_by_type(restored_info, "audio")
        if restored_video is None or restored_audio is None:
            raise ValueError("Audio-restored intermediate lost a media stream.")
        if str(restored_audio.get("codec_name")) != "aac":
            raise ValueError("Audio-restored intermediate did not encode normalized source as AAC.")
        if abs(media_duration(restored_info, restored_audio) - duration_seconds) > 0.16:
            raise ValueError("Restored unshifted audio duration does not match the requested audio duration.")
        os.replace(str(temporary), str(destination))
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return {"status": "restored", "source": str(normalized_audio.resolve()),
            "source_sha256": musetalk.sha256_file(normalized_audio), "codec": "aac",
            "decoded_pcm_note": "AAC encodes the normalized unshifted PCM once; subsequent pause correction and HD export stream-copy this AAC track."}


def expected_audio_duration(audio: Path, duration_cap: float, ffprobe: str) -> Tuple[float, Dict[str, Any]]:
    data = probe_media(audio, ffprobe)
    stream = stream_by_type(data, "audio")
    if stream is None:
        raise ValueError("Audio đầu vào không có audio stream.")
    source_seconds = media_duration(data, stream)
    if not math.isfinite(source_seconds) or source_seconds <= 0:
        raise ValueError("Không đọc được thời lượng audio đầu vào.")
    if not math.isfinite(duration_cap) or duration_cap <= 0:
        raise ValueError("--duration phải là số hữu hạn lớn hơn 0.")
    return min(source_seconds, duration_cap), {
        "path": str(audio.resolve()),
        "source_duration_seconds": round(source_seconds, 6),
        "requested_duration_cap_seconds": round(duration_cap, 6),
        "effective_duration_seconds": round(min(source_seconds, duration_cap), 6),
        "sample_rate": int(stream.get("sample_rate", 0) or 0),
        "channels": int(stream.get("channels", 0) or 0),
        "codec": stream.get("codec_name"),
    }


def make_echo_args(args: argparse.Namespace, output_dir: Path) -> argparse.Namespace:
    values = [
        "run", "--profile", args.profile, "--image", str(resolve_project_path(args.image)),
        "--audio", str(resolve_project_path(args.audio)), "--output-dir", str(output_dir),
        "--no-output-cache", "--ffmpeg", args.ffmpeg, "--ffprobe", args.ffprobe,
        "--mouth-mode", args.mouth_mode,
    ]
    if args.echo_dir:
        values.extend(("--echo-dir", str(args.echo_dir)))
    if args.echo_python:
        values.extend(("--echo-python", args.echo_python))
    if args.prompt:
        values.extend(("--prompt", args.prompt))
    return echo.make_parser().parse_args(values)


def find_echo_manifest(output_dir: Path, profile_name: str) -> Tuple[Path, Dict[str, Any]]:
    matches: List[Tuple[Path, Dict[str, Any]]] = []
    for path in output_dir.rglob("run_manifest.json"):
        try:
            payload = echo.read_json(path)
        except (OSError, ValueError):
            continue
        if payload.get("status") == "complete" and (payload.get("profile") or {}).get("name") == profile_name:
            outputs = payload.get("outputs") or {}
            base_path = outputs.get("motion_base", {}).get("path")
            if base_path and Path(base_path).is_file():
                matches.append((path, payload))
    if len(matches) != 1:
        raise RuntimeError("Cần đúng một run_manifest Echo hoàn chỉnh trong thư mục benchmark; nhận {}.".format(len(matches)))
    return matches[0]


def find_musetalk_render_manifest(cache_path: Path, output_path: Path) -> Dict[str, Any]:
    expected_output = output_path.resolve()
    for path in sorted((cache_path / "jobs").rglob("render_manifest.json"), key=lambda item: item.stat().st_mtime_ns, reverse=True):
        try:
            payload = echo.read_json(path)
        except (OSError, ValueError):
            continue
        candidate = payload.get("output")
        if candidate and Path(candidate).resolve() == expected_output:
            return payload
    raise RuntimeError("Không tìm thấy render_manifest MuseTalk cho output {}.".format(expected_output))


def build_export_command(
    source: Path,
    destination: Path,
    source_video: Mapping[str, Any],
    source_audio: Mapping[str, Any],
    ffmpeg: str,
) -> Tuple[List[str], str]:
    width = int(source_video.get("width", 0))
    height = int(source_video.get("height", 0))
    filter_option, filter_value, framing_mode = build_vertical_video_filter(width, height)
    audio_codec = str(source_audio.get("codec_name") or "")
    audio_args = ["-c:a", "copy"] if audio_codec == "aac" else ["-c:a", "aac", "-b:a", "160k"]
    command = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-stats_period", "1", "-progress", "pipe:1", "-nostats",
        "-y", "-i", str(source), filter_option, filter_value,
    ]
    if filter_option == "-filter_complex":
        command.extend(("-map", "[vout]"))
    else:
        command.extend(("-map", "0:v:0"))
    command.extend((
        "-map", "0:a:0", "-map_metadata", "0", "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-pix_fmt", "yuv420p", "-fps_mode", "passthrough", "-video_track_timescale", "25000",
    ))
    command.extend(audio_args)
    command.extend(("-movflags", "+faststart", str(destination)))
    return command, framing_mode


def run_live_command(command: Sequence[str], log_path: Path) -> Tuple[int, float]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    with log_path.open("w", encoding="utf-8", newline="\n") as log:
        process = subprocess.Popen(
            list(command), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
        )
        assert process.stdout is not None
        try:
            for line in process.stdout:
                sys.stdout.write(line)
                sys.stdout.flush()
                log.write(line)
                log.flush()
            code = process.wait()
        except KeyboardInterrupt:
            print("\nCtrl+C: dừng FFmpeg, giữ nguyên log và file tạm để kiểm tra.", flush=True)
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            raise
        finally:
            process.stdout.close()
    return code, time.perf_counter() - started


def export_hd_video(
    source: Path,
    destination: Path,
    ffmpeg: str,
    ffprobe: str,
    expected_duration: float,
    job_log: Path,
) -> Tuple[float, Dict[str, Any]]:
    started = time.perf_counter()
    source_data = probe_media(source, ffprobe)
    source_video = stream_by_type(source_data, "video")
    source_audio = stream_by_type(source_data, "audio")
    if source_video is None or source_audio is None:
        raise ValueError("MuseTalk intermediate phải có cả video và audio trước khi xuất HD.")
    source_fps = echo.parse_fraction(str(source_video.get("avg_frame_rate") or "0/1"))
    if abs(source_fps - FPS) > 0.01:
        raise ValueError("Intermediate không phải 25 FPS; không tự đổi FPS để che lỗi đồng bộ.")
    for stream in (source_video, source_audio):
        if abs(media_duration(source_data, stream) - expected_duration) > 0.16:
            raise ValueError("Intermediate sai thời lượng trước khi export.")
        if abs(float(stream.get("start_time") or 0.0)) > 0.04:
            raise ValueError("Intermediate có timestamp bắt đầu lệch; cần kiểm tra trước khi export.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name("." + destination.stem + ".partial.mp4")
    if destination.exists() or temporary.exists():
        raise FileExistsError("Không ghi đè output/file tạm đã có: {}".format(destination))
    command, framing_mode = build_export_command(source, temporary, source_video, source_audio, ffmpeg)
    code, encoder_seconds = run_live_command(command, job_log)
    if code != 0:
        raise RuntimeError("FFmpeg HD export thoát với mã {}; file tạm được giữ tại {}.".format(code, temporary))
    if not temporary.is_file() or temporary.stat().st_size <= 1000:
        raise RuntimeError("FFmpeg không tạo MP4 HD hợp lệ: {}.".format(temporary))
    output_data = probe_media(temporary, ffprobe)
    video = stream_by_type(output_data, "video")
    audio = stream_by_type(output_data, "audio")
    if video is None or audio is None:
        raise ValueError("MP4 HD không có đủ luồng hình và tiếng.")
    video_seconds = media_duration(output_data, video)
    audio_seconds = media_duration(output_data, audio)
    actual_fps = echo.parse_fraction(str(video.get("avg_frame_rate") or video.get("r_frame_rate") or "0/1"))
    video_codec = str(video.get("codec_name") or "")
    audio_codec = str(audio.get("codec_name") or "")
    sar = str(video.get("sample_aspect_ratio") or "")
    pix_fmt = str(video.get("pix_fmt") or "")
    checks = {
        "width": int(video.get("width", 0)) == EXPORT_WIDTH,
        "height": int(video.get("height", 0)) == EXPORT_HEIGHT,
        "fps_25": abs(actual_fps - FPS) <= 0.01,
        "h264": video_codec == "h264",
        "yuv420p": pix_fmt == "yuv420p",
        "square_pixels": sar == "1:1",
        "aac_audio": audio_codec == "aac",
        "video_duration": abs(video_seconds - expected_duration) <= 0.16,
        "audio_duration": abs(audio_seconds - expected_duration) <= 0.16,
        "audio_video_aligned": abs(video_seconds - audio_seconds) <= 0.12,
        "duration_within_cap": video_seconds <= expected_duration + 0.16,
    }
    if not all(checks.values()):
        raise ValueError("ffprobe HD validation failed: {}".format(checks))
    os.replace(str(temporary), str(destination))
    record = {
        "path": str(destination.resolve()),
        "bytes": destination.stat().st_size,
        "sha256": echo.hash_file(destination),
        "width": int(video["width"]),
        "height": int(video["height"]),
        "aspect_ratio": "9:16",
        "fps": actual_fps,
        "sar": sar,
        "video_codec": video_codec,
        "pixel_format": pix_fmt,
        "audio_codec": audio_codec,
        "video_duration_seconds": round(video_seconds, 6),
        "audio_duration_seconds": round(audio_seconds, 6),
        "export_framing_mode": framing_mode,
        "quality": {"video": "libx264", "preset": "fast", "crf": 18, "audio": "AAC copy if source AAC; otherwise AAC 160 kbps"},
        "ffprobe_checks": checks,
        "encoder_process_seconds": round(encoder_seconds, 3),
    }
    elapsed = time.perf_counter() - started
    record["export_wall_seconds"] = round(elapsed, 3)
    return elapsed, record


def write_phase_csv(path: Path, phases: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    fields = ("phase", "wall_seconds", "measured", "cache_state", "cache_hit", "video_index", "note")
    with temporary.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for item in phases:
            writer.writerow(item)
    os.replace(str(temporary), str(path))


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Benchmark/đóng gói ad 9:16 từ Echo Flash + MuseTalk trên Windows.")
    parser.add_argument("action", choices=("dry-run", "run", "benchmark", "calibrate"))
    parser.add_argument("--profile", choices=PROFILE_NAMES, default="A10", help="A10: native 512x640; A10HQ: 640x800; F10: 384x480. Cuối cùng dựng 1080x1920.")
    parser.add_argument("--base-video", type=Path, default=None, help="Motion base đã duyệt; nếu có thì bỏ qua Echo generation.")
    parser.add_argument("--image", type=Path, default=echo.default_image())
    parser.add_argument("--audio", type=Path, default=echo.default_audio())
    parser.add_argument("--duration", type=float, default=None, help="Giới hạn audio, mặc định 60s; calibrate mặc định 3.24s và giới hạn 6s.")
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--output-root", type=Path, default=PROJECT_ROOT / "output" / "vertical_ads")
    parser.add_argument("--echo-dir", type=Path, default=None)
    parser.add_argument("--echo-python", default=None)
    parser.add_argument("--musetalk-dir", default=None)
    parser.add_argument("--musetalk-python", default=None)
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--ffprobe", default="ffprobe")
    parser.add_argument("--prompt", default=None)
    parser.add_argument("--mouth-mode", choices=("neutral", "speech"), default="speech",
                        help="Chỉ khi tạo nền mới: speech dùng audio thật để sinh chuyển động; neutral conditioning im lặng, đầu gần tĩnh, không khuyến nghị làm motion base chuyển động.")
    parser.add_argument("--bbox-shift", type=int, default=0)
    parser.add_argument("--parsing-mode", choices=("jaw", "raw"), default="jaw")
    parser.add_argument("--pause-mouth-closure", choices=("auto", "force", "off"), default="auto",
                        help="Gate PCM pause cho MuseTalk và correction sau render: auto mute pause >=0.32s, force >=0.16s; correction auto cần manifest speech + SHA khớp và source-time pause an toàn. off tắt cả gate lẫn correction.")
    parser.add_argument("--audio-offset-ms", type=int, default=0,
                        help="Dịch audio chỉ cho MuseTalk conditioning theo bước 40ms, giới hạn ±160ms. Dương làm miệng trễ audio; âm làm miệng đi trước. Audio output vẫn không dịch.")
    parser.add_argument("--audio-offset-sweep", action="store_true",
                        help="calibrate: tạo 3 preview jaw ở -40/0/+40ms; cần --base-video và duration ≤6s; mỗi preview nạp MuseTalk lại.")
    return parser


class TeeStream:
    def __init__(self, console: Any, log: Any) -> None:
        self.console = console
        self.log = log

    def write(self, text: str) -> int:
        self.console.write(text)
        self.log.write(text)
        self.console.flush()
        self.log.flush()
        return len(text)

    def flush(self) -> None:
        self.console.flush()
        self.log.flush()


def _append_phase(report: Dict[str, Any], name: str, seconds: float, note: str, cache_state: str = "n/a", cache_hit: Optional[bool] = None, video_index: Optional[int] = None) -> None:
    row = {
        "phase": name,
        "wall_seconds": round(seconds, 3),
        "measured": "yes" if seconds > 0 else "no",
        "cache_state": cache_state,
        "cache_hit": "" if cache_hit is None else str(cache_hit).lower(),
        "video_index": "" if video_index is None else video_index,
        "note": note,
    }
    report.setdefault("phase_timings", []).append(row)
    write_phase_csv(Path(report["phase_csv_path"]), report["phase_timings"])
    echo.write_json_atomic(Path(report["report_path"]), report)


def _find_musetalk_paths(args: argparse.Namespace) -> musetalk.MuseTalkPaths:
    paths = musetalk.discover_musetalk_paths(args.musetalk_dir, args.musetalk_python)
    musetalk.validate_safe_musetalk_root(paths.root)
    musetalk.validate_musetalk_install(paths)
    musetalk.validate_pingpong_support(paths.inference_script)
    return paths


def _preflight_without_base(args: argparse.Namespace, echo_root: Path, job_dir: Path) -> Dict[str, Any]:
    echo_profile = echo.PROFILES[args.profile]
    audio_seconds, audio_info = expected_audio_duration(resolve_project_path(args.audio), args.duration, args.ffprobe)
    paths = _find_musetalk_paths(args)
    musetalk.validate_safe_cache_root(resolve_project_path(args.cache_dir))
    musetalk.validate_motion_coverage(audio_seconds, echo_profile.max_duration_seconds, FPS, "pingpong")
    echo_args = echo.make_parser().parse_args([
        "dry-run", "--profile", args.profile, "--image", str(resolve_project_path(args.image)),
        "--audio", str(resolve_project_path(args.audio)), "--ffmpeg", args.ffmpeg, "--ffprobe", args.ffprobe,
        "--mouth-mode", args.mouth_mode,
    ] + (["--echo-dir", str(args.echo_dir)] if args.echo_dir else []) + (["--echo-python", args.echo_python] if args.echo_python else []))
    echo_status = echo.dry_run(echo_args, echo_root)
    return {
        "echo_dry_run_exit_code": echo_status,
        "musetalk_root": str(paths.root),
        "musetalk_python": str(paths.python),
        "echo_expected_forward_duration_seconds": echo_profile.max_duration_seconds,
        "nominal_pingpong_cycle_seconds": round(2 * echo_profile.max_duration_seconds, 6),
        "audio": audio_info,
        "note": "Chỉ kiểm tra file, source, model asset theo size và độ phủ thời lượng; không import Torch/CUDA hoặc chạy inference.",
    }


def _preflight_with_base(args: argparse.Namespace, base_video: Path, job_dir: Path) -> Dict[str, Any]:
    audio_seconds, audio_info = expected_audio_duration(resolve_project_path(args.audio), args.duration, args.ffprobe)
    paths = _find_musetalk_paths(args)
    base_info = musetalk.probe_media(base_video, args.ffprobe)
    musetalk.validate_base_media(base_info, FPS)
    musetalk.validate_motion_coverage(audio_seconds, base_info.video_duration or base_info.duration, FPS, "pingpong")
    dry_result = musetalk.run_pipeline(
        "dry-run", base_video=base_video, audio=resolve_project_path(args.audio), duration=args.duration,
        output=job_dir / "dry_run_unused.mp4", cache_dir=resolve_project_path(args.cache_dir), fps=FPS,
        batch_size=args.batch_size, musetalk_dir=paths.root, musetalk_python=paths.python,
        ffmpeg_override=args.ffmpeg, ffprobe_override=args.ffprobe,
        log_path=job_dir / "logs" / "musetalk_dry_run.log", motion_policy="pingpong",
        bbox_shift=args.bbox_shift, parsing_mode=args.parsing_mode,
    )
    return {"audio": audio_info, "dry_run": {key: str(value) if isinstance(value, Path) else value for key, value in dry_result.items()},
            "musetalk_root": str(paths.root), "musetalk_python": str(paths.python),
            "base_video": {"path": str(base_video), "width": base_info.width, "height": base_info.height,
                           "fps": base_info.fps, "duration_seconds": base_info.video_duration or base_info.duration},
            "nominal_pingpong_cycle_seconds": round(2 * (base_info.video_duration or base_info.duration), 6),
            "note": "Echo generation được bỏ qua vì dùng motion base đã có; MuseTalk dry-run không nạp Torch/CUDA."}


def _run_echo_generation(args: argparse.Namespace, echo_root: Path, job_dir: Path, report: Dict[str, Any]) -> Tuple[Path, Dict[str, Any], float]:
    echo_output_root = job_dir / "echo"
    echo_output_root.mkdir(parents=True, exist_ok=False)
    echo_args = make_echo_args(args, echo_output_root)
    gpu_python = echo.resolve_python(echo_root, args.echo_python)
    report["echo"] = {"status": "running", "output_root": str(echo_output_root), "gpu_python": str(gpu_python)}
    echo.write_json_atomic(Path(report["report_path"]), report)
    started = time.perf_counter()
    exit_code = echo.run_job(echo_args, echo_root, gpu_python, benchmark=False)
    elapsed = time.perf_counter() - started
    _append_phase(report, "echo_generation_wall", elapsed, "Controller wall time including Echo input preparation, model load, audio conditioning, denoise and encode.")
    if exit_code != 0:
        report["echo"].update({"status": "failed", "exit_code": exit_code, "wall_seconds": round(elapsed, 3)})
        raise RuntimeError("Echo generation failed with exit code {}. Check {}.".format(exit_code, echo_output_root))
    manifest_path, manifest = find_echo_manifest(echo_output_root, args.profile)
    profile = echo.PROFILES[args.profile]
    base_path = Path(manifest["outputs"]["motion_base"]["path"]).resolve()
    echo.validate_output_file(base_path, {
        "width": profile.width, "height": profile.height, "frames": profile.frames,
        "fps": profile.fps, "duration": profile.max_duration_seconds,
    }, require_audio=False, ffprobe=args.ffprobe)
    report["echo"] = {
        "status": "generated_fresh",
        "motion_base": str(base_path),
        "run_manifest": str(manifest_path),
        "wall_seconds": round(elapsed, 3),
        "worker_process_seconds": manifest.get("process_seconds"),
        "profile": manifest.get("profile"),
        "frames": manifest.get("frames"),
        "duration_seconds": manifest.get("duration_seconds"),
        "input_framing": manifest.get("input_framing"),
        "motion_source": manifest.get("motion_source"),
        "mouth_mode": manifest.get("mouth_mode"),
        "source_manifest_audio_sha256": (manifest.get("fingerprint_inputs") or {}).get("audio_sha256"),
        "memory_mode": manifest.get("memory_mode"),
        "backend_timing": manifest.get("backend_timing"),
        "source_and_model_pins": {
            key: (manifest.get("fingerprint_inputs") or {}).get(key)
            for key in ("code_pin", "flash_revision", "base_revision", "wav2vec_revision", "num_inference_steps", "sampler")
        },
        "controller_python": (manifest.get("fingerprint_inputs") or {}).get("python_version"),
        "gpu_python_executable": str(gpu_python),
        "note": "GPU model-load/conditioning/denoise timings and CUDA peak memory are copied from Echo run_manifest; no temperature or system-RAM telemetry is sampled.",
    }
    report["motion_base"] = str(base_path)
    echo.write_json_atomic(Path(report["report_path"]), report)
    return base_path, manifest, elapsed


def _reused_base_metadata(base_video: Path, ffprobe: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {"status": "reused_existing", "motion_base": str(base_video.resolve()), "wall_seconds": 0.0}
    manifest_path, manifest = _find_base_echo_manifest(base_video)
    if manifest_path is not None and manifest is not None:
        result["source_run_manifest"] = str(manifest_path)
        result["source_manifest_profile"] = manifest.get("profile")
        result["source_manifest_mouth_mode"] = manifest.get("mouth_mode")
        result["source_manifest_audio"] = manifest.get("source_audio")
        result["source_manifest_audio_sha256"] = (manifest.get("fingerprint_inputs") or {}).get("audio_sha256")
        result["source_and_model_pins"] = {
            key: (manifest.get("fingerprint_inputs") or {}).get(key)
            for key in ("code_pin", "flash_revision", "base_revision", "wav2vec_revision")
        }
        result["source_manifest_motion_source"] = manifest.get("motion_source")
    data = probe_media(base_video, ffprobe)
    video = stream_by_type(data, "video")
    if video is None:
        raise ValueError("Motion base không có video stream: {}".format(base_video))
    result["media"] = {"width": int(video.get("width", 0)), "height": int(video.get("height", 0)),
                       "fps": echo.parse_fraction(str(video.get("avg_frame_rate") or video.get("r_frame_rate") or "0/1")),
                       "duration_seconds": media_duration(data, video)}
    return result


def _find_base_echo_manifest(base_video: Path) -> Tuple[Optional[Path], Optional[Dict[str, Any]]]:
    expected_base = base_video.resolve()
    for parent in (base_video.parent, *base_video.parents):
        manifest_path = parent / "run_manifest.json"
        if not manifest_path.is_file():
            continue
        try:
            manifest = echo.read_json(manifest_path)
        except (OSError, ValueError):
            continue
        recorded = ((manifest.get("outputs") or {}).get("motion_base") or {}).get("path")
        if recorded:
            try:
                if Path(recorded).resolve() == expected_base:
                    return manifest_path, manifest
            except (OSError, RuntimeError):
                continue
    return None, None


def _pause_closure_decision(
    requested: str,
    mouth_mode: Optional[str],
    manifest_audio_sha256: Optional[str] = None,
    current_audio_sha256: Optional[str] = None,
) -> Tuple[bool, str]:
    if requested == "off":
        return False, "disabled_by_cli"
    if requested == "force":
        return True, "forced_by_cli; mode/audio identity gate bypassed, but source-time pause verification remains required"
    if mouth_mode == "neutral":
        return False, "skipped_because_echo_manifest_marks_neutral_motion_base"
    if mouth_mode != "speech":
        return False, "skipped_because_motion_base_mode_is_unverified"
    if not manifest_audio_sha256 or not current_audio_sha256:
        return False, "skipped_because_echo_audio_identity_is_unverified"
    if manifest_audio_sha256.lower() != current_audio_sha256.lower():
        return False, "skipped_because_current_audio_does_not_match_echo_conditioning_audio_sha256"
    return True, "echo_manifest_confirms_speech_mode_and_matching_audio_sha256"


def _run_one_musetalk(
    args: argparse.Namespace,
    base_video: Path,
    paths: musetalk.MuseTalkPaths,
    job_dir: Path,
    video_index: int,
    require_cache_hit: bool = False,
    conditioning_audio: Optional[Path] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    raw_output = job_dir / "intermediate" / ("musetalk_video_{}.mp4".format(video_index))
    log_path = job_dir / "logs" / ("musetalk_video_{}.log".format(video_index))
    started = time.perf_counter()
    result = musetalk.run_pipeline(
        "run", base_video=base_video, audio=(conditioning_audio or resolve_project_path(args.audio)), duration=args.duration,
        output=raw_output, cache_dir=resolve_project_path(args.cache_dir), fps=FPS,
        batch_size=args.batch_size, musetalk_dir=paths.root, musetalk_python=paths.python,
        ffmpeg_override=args.ffmpeg, ffprobe_override=args.ffprobe, log_path=log_path,
        motion_policy="pingpong", bbox_shift=args.bbox_shift, parsing_mode=args.parsing_mode,
    )
    wall_seconds = time.perf_counter() - started
    cache_hit = bool(result.get("cache_hit"))
    if require_cache_hit and not cache_hit:
        raise RuntimeError("MuseTalk lần 2 không tái sử dụng avatar cache như dự kiến; kết quả bị giữ để kiểm tra.")
    if not raw_output.is_file():
        raise RuntimeError("MuseTalk không tạo intermediate video: {}".format(raw_output))
    cache_path = Path(result["cache_path"])
    run_manifest = find_musetalk_render_manifest(cache_path, raw_output)
    actual_audio = float(result.get("audio_duration") or run_manifest.get("normalized_audio_duration_seconds") or 0.0)
    if actual_audio <= 0:
        raise RuntimeError("Không lấy được audio duration thực tế từ MuseTalk.")
    state = "REUSE" if cache_hit else "CREATE"
    metadata = {
        "video_index": video_index,
        "cache_state": state,
        "avatar_cache_hit": cache_hit,
        "avatar_cache_path": str(cache_path),
        "model_weights_reloaded_for_this_process": bool(run_manifest.get("model_weights_reloaded_for_this_process", True)),
        "musetalk_wall_seconds": round(wall_seconds, 3),
        "backend_process_seconds": run_manifest.get("backend_process_seconds", result.get("backend_seconds")),
        "audio_normalization_seconds": run_manifest.get("audio_normalization_seconds"),
        "audio_duration_seconds": round(actual_audio, 6),
        "nominal_full_motion_cycle_seconds": result.get("nominal_full_motion_cycle_seconds"),
        "nominal_motion_cycles": result.get("nominal_motion_cycles"),
        "lip_sync_settings": {"bbox_shift": args.bbox_shift, "parsing_mode": args.parsing_mode,
                              "audio_padding_left": 2, "audio_padding_right": 2,
                              "audio_offset_ms": args.audio_offset_ms,
                              "audio_offset_sign": "positive delays mouth; negative advances mouth"},
        "log": str(log_path),
    }
    metadata["render_manifest"] = str(next(
        path for path in sorted((cache_path / "jobs").rglob("render_manifest.json"), key=lambda item: item.stat().st_mtime_ns, reverse=True)
        if echo.read_json(path).get("output") and Path(echo.read_json(path)["output"]).resolve() == raw_output.resolve()
    ))
    _write_output = result.get("output")
    if _write_output is not None and Path(_write_output).resolve() != raw_output.resolve():
        raise RuntimeError("MuseTalk trả output path không khớp yêu cầu: {}".format(_write_output))
    return metadata, {"path": raw_output, "result": result, "manifest": run_manifest, "actual_audio_seconds": actual_audio}


def _runtime_versions(echo_root: Path, echo_python: Path) -> Dict[str, Any]:
    code = (
        "import importlib.metadata as m,json,sys;"
        "names=['torch','torchvision','torchaudio','diffusers','transformers','accelerate','numpy'];"
        "out={'python':sys.version.replace('\\n',' '), 'packages':{}};"
        "[(out['packages'].__setitem__(n,m.version(n))) for n in names if any(d.metadata['Name'].lower()==n for d in m.distributions())];"
        "print(json.dumps(out))"
    )
    result = subprocess.run([str(echo_python), "-c", code], cwd=str(echo_root), capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    if result.returncode != 0:
        return {"status": "unavailable", "stderr": result.stderr.strip(), "python_executable": str(echo_python)}
    try:
        return {"status": "queried_from_gpu_venv", "python_executable": str(echo_python), **json.loads(result.stdout)}
    except (ValueError, TypeError):
        return {"status": "unavailable", "python_executable": str(echo_python), "stdout": result.stdout[-1000:]}


def _write_output_metrics(video_entry: Dict[str, Any], output_record: Mapping[str, Any]) -> None:
    actual_seconds = float(output_record["audio_duration_seconds"])
    post_echo_wall = (float(video_entry.get("audio_conditioning_preparation_wall_seconds", 0.0))
                      + float(video_entry["musetalk_wall_seconds"])
                      + float(video_entry.get("pause_reference_audio_preparation_wall_seconds", 0.0))
                      + float(video_entry.get("audio_offset_restore_wall_seconds", 0.0))
                      + float(video_entry.get("pause_mouth_closure_wall_seconds", 0.0))
                      + float(output_record["export_wall_seconds"]))
    video_entry["hd_export_wall_seconds"] = output_record["export_wall_seconds"]
    video_entry["output"] = dict(output_record)
    video_entry["rendered_seconds_per_post_echo_wall_second"] = round(actual_seconds / post_echo_wall, 6) if post_echo_wall > 0 else None
    video_entry["normalized_wall_seconds_per_60_audio_seconds_extrapolation"] = round(post_echo_wall * 60.0 / actual_seconds, 3) if actual_seconds > 0 else None
    video_entry["normalized_60s_is_measured"] = abs(actual_seconds - 60.0) <= 0.16


def _prepare_conditioning_audio(
    args: argparse.Namespace,
    job_dir: Path,
    ffmpeg: str,
    ffprobe: str,
    offsets_ms: Sequence[int],
    pause_policy: str,
) -> Tuple[Path, Path, Dict[int, Path], float, float, Dict[str, Any], Dict[str, Dict[str, Any]]]:
    """Normalize once, gate reliable pauses, then create fixed-length offset variants."""
    intermediate = job_dir / "intermediate"
    intermediate.mkdir(parents=True, exist_ok=True)
    original = intermediate / "audio_unshifted_16k_mono.wav"
    started = time.perf_counter()
    actual_duration, _ = musetalk.normalize_audio(
        resolve_project_path(args.audio), original, args.duration, ffmpeg, ffprobe,
    )
    normalization_seconds = time.perf_counter() - started

    gate_started = time.perf_counter()
    if pause_policy == "off":
        gated_audio = original
        gate_record = _disabled_pause_gate_record(original, pause_policy)
    else:
        minimum_pause_seconds = (PAUSE_FORCE_MIN_DURATION_SECONDS if pause_policy == "force"
                                 else PAUSE_MIN_DURATION_SECONDS)
        gated_audio = intermediate / "audio_conditioning_pause_gated_16k_mono.wav"
        gate_record = gate_pause_audio(original, gated_audio, minimum_pause_seconds)
        gate_record["requested_policy"] = pause_policy
    gate_wall_seconds = time.perf_counter() - gate_started
    gate_record["preparation_wall_seconds"] = round(gate_wall_seconds, 3)

    result: Dict[int, Path] = {0: gated_audio}
    variant_records: Dict[str, Dict[str, Any]] = {}
    base_gate_intervals = gate_record.get("intervals", [])
    offset_started = time.perf_counter()
    for offset in sorted(set(offsets_ms)):
        validate_audio_offset_ms(offset)
        if offset == 0:
            shifted = gated_audio
            offset_record = {"offset_ms": 0, "sample_offset": 0, "sample_rate": 16000,
                             "duration_seconds": round(actual_duration, 6),
                             "original_audio_preserved_for_output": True}
        else:
            shifted = intermediate / "audio_conditioning_{:+d}ms.wav".format(offset)
            offset_record = shift_pcm_wav(gated_audio, shifted, offset)
        result[offset] = shifted
        variant_info = _normalized_wav_info(shifted)
        moved_intervals = _offset_pause_intervals(
            base_gate_intervals, variant_info["sample_count"], offset, variant_info["sample_rate"],
        )
        gated_samples = sum(item["sample_count"] for item in moved_intervals)
        variant_records[str(offset)] = {
            "path": str(shifted.resolve()),
            "sha256": musetalk.sha256_file(shifted),
            **variant_info,
            "offset": offset_record,
            "pause_gate": {
                "status": gate_record["status"],
                "requested_policy": pause_policy,
                "interval_count": len(moved_intervals),
                "gated_sample_count": gated_samples,
                "gated_duration_seconds": round(gated_samples / float(variant_info["sample_rate"]), 6),
                "intervals": moved_intervals,
                "applied_before_offset": True,
            },
        }
    offset_seconds = time.perf_counter() - offset_started
    gate_record["preparation_wall_seconds"] = round(gate_wall_seconds, 3)
    gate_record["total_conditioning_preparation_wall_seconds"] = round(
        normalization_seconds + gate_wall_seconds + offset_seconds, 3,
    )
    return (original, gated_audio, result, actual_duration,
            normalization_seconds + gate_wall_seconds + offset_seconds, gate_record, variant_records)


def _prepare_pause_reference_audio(
    requested_policy: str,
    echo_manifest: Optional[Mapping[str, Any]],
    manifest_audio_sha256: Optional[str],
    current_audio_sha256: str,
    current_audio_path: Path,
    job_dir: Path,
    base_duration_seconds: float,
    ffmpeg: str,
    ffprobe: str,
) -> Tuple[Optional[Path], Dict[str, Any], float]:
    """Get verified Echo conditioning audio used to qualify source-frame pauses."""
    if not manifest_audio_sha256:
        return None, {"status": "unavailable", "reason": "Echo manifest has no conditioning-audio SHA-256."}, 0.0

    current_matches = current_audio_sha256.lower() == manifest_audio_sha256.lower()
    if current_matches:
        source_audio = current_audio_path
        selection = "current_audio_verified_by_echo_manifest_sha256"
    elif requested_policy == "force" and echo_manifest is not None:
        recorded_path = echo_manifest.get("source_audio")
        source_audio = Path(str(recorded_path)).expanduser() if recorded_path else Path()
        if not recorded_path or not source_audio.is_file():
            return None, {
                "status": "unavailable",
                "reason": "force bypassed the auto identity gate, but the original Echo conditioning audio is missing.",
                "manifest_audio_sha256": manifest_audio_sha256,
                "current_audio_sha256": current_audio_sha256,
            }, 0.0
        if echo.hash_file(source_audio).lower() != manifest_audio_sha256.lower():
            return None, {
                "status": "unavailable",
                "reason": "The Echo conditioning-audio file no longer matches its manifest SHA-256.",
                "manifest_audio_sha256": manifest_audio_sha256,
                "current_audio_sha256": current_audio_sha256,
                "recorded_audio_path": str(source_audio.resolve()),
            }, 0.0
        selection = "original_echo_conditioning_audio_verified_by_manifest_sha256"
    else:
        return None, {
            "status": "unavailable",
            "reason": "Current audio does not match the Echo conditioning audio; auto never uses this base for closure.",
            "manifest_audio_sha256": manifest_audio_sha256,
            "current_audio_sha256": current_audio_sha256,
        }, 0.0

    destination = job_dir / "intermediate" / "echo_reference_audio_16k_mono.wav"
    started = time.perf_counter()
    actual_duration, _ = musetalk.normalize_audio(
        source_audio, destination, base_duration_seconds, ffmpeg, ffprobe,
    )
    elapsed = time.perf_counter() - started
    return destination, {
        "status": "verified",
        "selection": selection,
        "path": str(destination.resolve()),
        "source_path": str(source_audio.resolve()),
        "source_sha256": echo.hash_file(source_audio),
        "manifest_audio_sha256": manifest_audio_sha256,
        "current_audio_sha256": current_audio_sha256,
        "normalized_duration_seconds": round(actual_duration, 6),
        "normalization_wall_seconds": round(elapsed, 3),
        "scope": "first motion-base duration only; later ping-pong repeats are eligible only when their mapped source frame is in a verified source pause",
    }, elapsed


def run_workflow(args: argparse.Namespace, job_dir: Path, report: Dict[str, Any]) -> int:
    started = time.perf_counter()
    report_path = job_dir / report_filename(args.action)
    phase_csv_path = job_dir / "phase_timings.csv"
    report.update({"report_path": str(report_path), "phase_csv_path": str(phase_csv_path), "action": args.action,
                   "job_directory": str(job_dir), "status": "running", "requested_profile": args.profile,
                   "target_export": {"width": EXPORT_WIDTH, "height": EXPORT_HEIGHT, "ratio": "9:16", "fps": FPS,
                                     "video": "libx264 CRF18 preset fast, yuv420p", "audio": "AAC copy if input AAC; otherwise 160 kbps"},
                   "motion_policy": "MuseTalk pingpong; source video frames reverse, audio remains forward"})
    echo.write_json_atomic(report_path, report)
    ffmpeg, ffprobe = echo.resolve_tools(args.ffmpeg, args.ffprobe)
    args.ffmpeg, args.ffprobe = ffmpeg, ffprobe
    audio_seconds, audio_info = expected_audio_duration(resolve_project_path(args.audio), args.duration, ffprobe)
    report["audio"] = audio_info
    report["effective_audio_duration_seconds"] = round(audio_seconds, 6)
    report["audio_offset_policy"] = {
        "requested_offset_ms": args.audio_offset_ms,
        "conditioning_sign": "positive delays mouth relative to original audio; negative advances mouth",
        "allowed_step_ms": AUDIO_OFFSET_STEP_MS,
        "range_ms": [-AUDIO_OFFSET_LIMIT_MS, AUDIO_OFFSET_LIMIT_MS],
        "output_audio": "always unshifted normalized source audio",
    }
    profile = echo.PROFILES[args.profile]
    report["profile"] = echo.asdict(profile)
    echo_root = (args.echo_dir or echo.default_echo_root()).expanduser().resolve()
    base_video = resolve_project_path(args.base_video) if args.base_video else None
    preflight_started = time.perf_counter()
    if base_video is not None:
        paths = _find_musetalk_paths(args)
        report["preflight"] = _preflight_with_base(args, base_video, job_dir)
    elif args.action == "dry-run":
        report["preflight"] = _preflight_without_base(args, echo_root, job_dir)
        if report["preflight"]["echo_dry_run_exit_code"] != 0:
            raise RuntimeError("Echo dry-run chưa đạt; không có CUDA/model inference nào chạy.")
        paths = _find_musetalk_paths(args)
    else:
        paths = _find_musetalk_paths(args)
        musetalk.validate_safe_cache_root(resolve_project_path(args.cache_dir))
        musetalk.validate_motion_coverage(audio_seconds, profile.max_duration_seconds, FPS, "pingpong")
        if not resolve_project_path(args.image).is_file():
            raise FileNotFoundError("Không tìm thấy ảnh nguồn: {}".format(resolve_project_path(args.image)))
        report["preflight"] = {
            "musetalk_root": str(paths.root), "musetalk_python": str(paths.python),
            "echo_root": str(echo_root), "echo_gpu_python": str(echo.resolve_python(echo_root, args.echo_python)),
            "echo_mode": "fresh_profile_render" if base_video is None else "reused_motion_base",
            "audio_duration_seconds": audio_seconds,
            "nominal_pingpong_cycle_seconds": 2 * profile.max_duration_seconds,
            "note": "Run action relies on each existing pipeline's own validations; no separate dry-run inference is performed.",
        }
    preflight_seconds = time.perf_counter() - preflight_started
    _append_phase(report, "preflight", preflight_seconds, "File/runtime/configuration checks only; no inference in dry-run.")
    if args.action == "dry-run":
        report["echo"] = {"status": "reused_existing", "motion_base": str(base_video), "wall_seconds": 0.0} if base_video else {"status": "validated_only", "wall_seconds": 0.0}
        report["status"] = "dry_run_passed"
        report["whole_job_wall_seconds"] = round(time.perf_counter() - started, 3)
        echo.write_json_atomic(report_path, report)
        print("Dry-run passed: chỉ kiểm tra file/source/model size/độ phủ; không chạy Echo, MuseTalk, Torch hoặc CUDA.")
        print("Report: {}".format(report_path))
        return 0

    echo_wall = 0.0
    if base_video is None:
        if args.action not in ("run", "benchmark", "calibrate"):
            raise ValueError("Action không hợp lệ.")
        base_video, echo_manifest, echo_wall = _run_echo_generation(args, echo_root, job_dir, report)
        profile_duration = float(echo_manifest.get("duration_seconds") or profile.max_duration_seconds)
        if not math.isfinite(profile_duration) or profile_duration <= 0:
            raise RuntimeError("Echo motion base duration invalid.")
        echo_runtime = _runtime_versions(echo_root, echo.resolve_python(echo_root, args.echo_python))
        report["echo"]["gpu_venv_runtime"] = echo_runtime
    else:
        report["echo"] = _reused_base_metadata(base_video, ffprobe)
        echo_wall = 0.0
        _append_phase(report, "echo_generation_wall", 0.0, "Skipped: supplied motion base reused.", cache_state="REUSED")
    base_info = musetalk.probe_media(base_video, ffprobe)
    musetalk.validate_base_media(base_info, FPS)
    base_duration = base_info.video_duration or base_info.duration
    report["motion_base"] = {"path": str(base_video.resolve()), "width": base_info.width, "height": base_info.height,
                             "fps": base_info.fps, "duration_seconds": base_duration,
                             "sha256": musetalk.sha256_file(base_video),
                             "nominal_pingpong_cycle_seconds": 2 * base_duration}
    source_mouth_mode = report["echo"].get("mouth_mode") or report["echo"].get("source_manifest_mouth_mode")
    base_manifest_path, base_manifest = _find_base_echo_manifest(base_video)
    manifest_audio_sha256 = ((base_manifest.get("fingerprint_inputs") or {}).get("audio_sha256")
                             if base_manifest else report["echo"].get("source_manifest_audio_sha256"))
    current_audio_path = resolve_project_path(args.audio)
    current_audio_sha256 = echo.hash_file(current_audio_path)
    closure_enabled, closure_reason = _pause_closure_decision(
        args.pause_mouth_closure, source_mouth_mode, manifest_audio_sha256, current_audio_sha256,
    )
    closure_min_seconds = (PAUSE_FORCE_MIN_DURATION_SECONDS if args.pause_mouth_closure == "force"
                           else PAUSE_MIN_DURATION_SECONDS)
    offsets = [-40, 0, 40] if args.audio_offset_sweep else [args.audio_offset_ms]
    (unshifted_audio, gated_conditioning_audio, conditioning_audio,
     normalized_audio_seconds, audio_preparation_seconds, pause_gate_record,
     conditioning_variant_records) = _prepare_conditioning_audio(
        args, job_dir, ffmpeg, ffprobe, offsets, args.pause_mouth_closure,
    )
    pause_reference_audio: Optional[Path] = None
    pause_reference_audio_record: Dict[str, Any] = {"status": "not_required; pause closure is disabled"}
    pause_reference_audio_wall = 0.0
    if closure_enabled:
        pause_reference_audio, pause_reference_audio_record, pause_reference_audio_wall = _prepare_pause_reference_audio(
            args.pause_mouth_closure, base_manifest, manifest_audio_sha256, current_audio_sha256,
            current_audio_path, job_dir, base_duration, ffmpeg, ffprobe,
        )
    _append_phase(report, "pause_reference_audio_preparation", pause_reference_audio_wall,
                  "Normalize and verify the Echo conditioning audio used to qualify mapped source-frame pauses.",
                  cache_state="PREPARED" if pause_reference_audio is not None else "SKIPPED")
    if not manifest_audio_sha256:
        motion_alignment_status = "unverified"
        motion_alignment_warning = (
            "Không có SHA-256 audio Echo đã dùng để sinh motion base; đầu/vai đang dùng chuyển động cũ và "
            "không thể xác nhận bám nhịp kịch bản hiện tại. Nếu cần gesture khớp audio này, hãy sinh lại Echo speech base."
        )
    elif manifest_audio_sha256.lower() != current_audio_sha256.lower():
        motion_alignment_status = "mismatch"
        motion_alignment_warning = (
            "Audio hiện tại khác audio dùng để sinh motion base; gate chỉ giúp MuseTalk xử lý khẩu hình/pause, "
            "không đồng bộ lại gesture đầu/vai. Hãy sinh lại Echo speech base nếu cần cử chỉ bám nhịp kịch bản hiện tại."
        )
    else:
        motion_alignment_status = "verified_match"
        motion_alignment_warning = None
    echo_conditioning_audio_path = (
        base_manifest.get("source_audio") if base_manifest else
        report["echo"].get("source_manifest_audio")
    )
    motion_audio_alignment = {
        "status": motion_alignment_status,
        "echo_conditioning_audio_path": echo_conditioning_audio_path,
        "echo_conditioning_audio_sha256": manifest_audio_sha256,
        "current_audio_sha256": current_audio_sha256,
        "sha256_matches": bool(manifest_audio_sha256 and
                                manifest_audio_sha256.lower() == current_audio_sha256.lower()),
        "motion_base_path": str(base_video.resolve()),
        "warning": motion_alignment_warning,
        "recommended_action": ("Regenerate an Echo speech motion base with the current audio before relying on head/shoulder gesture timing."
                               if motion_alignment_status != "verified_match" else
                               "Audio identity is verified; visual gesture quality still needs review."),
        "scope_note": "Pause gating and mouth correction affect lip-sync only; they do not retime Echo-generated head or shoulder motion.",
    }
    report["motion_audio_alignment"] = motion_audio_alignment
    original_audio_info = _normalized_wav_info(unshifted_audio)
    report["audio_alignment"] = {
        "unshifted_normalized_audio": str(unshifted_audio.resolve()),
        "unshifted_normalized_audio_sha256": musetalk.sha256_file(unshifted_audio),
        "original_normalized_output_audio": {
            "path": str(unshifted_audio.resolve()),
            "sha256": musetalk.sha256_file(unshifted_audio),
            **original_audio_info,
        },
        "pre_offset_conditioning_audio": str(gated_conditioning_audio.resolve()),
        "pause_gated_conditioning_audio": pause_gate_record,
        "normalized_duration_seconds": round(normalized_audio_seconds, 6),
        "conditioning_variants": {str(offset): str(path.resolve()) for offset, path in conditioning_audio.items()},
        "conditioning_variant_details": conditioning_variant_records,
        "output_audio_source": "unshifted normalized source; offset affects MuseTalk conditioning only",
        "output_audio_remux": "AAC is re-encoded from original normalized PCM when the conditioning waveform is offset or pause-gated; later stages stream-copy the AAC track",
        "feature_alignment_note": "MuseTalk derives Whisper audio features at 50 Hz and renders video at 25 FPS (about 40 ms per output frame); pause gate zeros only detected conditioning pauses and does not alter motion-base frames.",
        "preparation_wall_seconds": round(audio_preparation_seconds, 3),
        "offset_sweep_model_reload_note": "Each preview starts a separate MuseTalk process and reloads weights." if args.audio_offset_sweep else None,
    }
    _append_phase(report, "audio_conditioning_preparation", audio_preparation_seconds,
                  "Normalize output audio; gate reliable pauses in the MuseTalk conditioning copy, then create exact-length offset variants.")
    report["pause_mouth_closure_policy"] = {
        "requested": args.pause_mouth_closure,
        "conditioning_audio_gate": pause_gate_record,
        "conditioning_gate_enabled": args.pause_mouth_closure != "off",
        "enabled_for_this_base": closure_enabled,
        "source_mouth_mode": source_mouth_mode or "unknown",
        "source_run_manifest": str(base_manifest_path) if base_manifest_path else
                               report["echo"].get("run_manifest") or report["echo"].get("source_run_manifest"),
        "manifest_audio_sha256": manifest_audio_sha256,
        "current_input_audio_sha256": current_audio_sha256,
        "audio_identity_matches": bool(manifest_audio_sha256 and manifest_audio_sha256.lower() == current_audio_sha256.lower()),
        "reference_audio": pause_reference_audio_record,
        "decision": closure_reason,
        "minimum_pause_seconds": closure_min_seconds,
        "reference": "same approved motion-base frames with the same forward+reverse ping-pong mapping; no neutral pass or extra model render",
        "source_pause_guard": "Every corrected output frame must be inside an output pause and map to a source frame whose Echo-conditioning-audio time is also a detected pause; unmatched repeated pauses remain uncovered.",
        "fallback_if_correction_fails": "fail workflow and preserve intermediates; never mark output corrected",
        "note": ("The conditioning pause gate is independent of manifest identity and zeros only confidently detected pauses in the current audio. "
                 "Post-render pause correction is secondary: safe pause frames may be restored from the same animated motion base at the matching ping-pong frame index, "
                 "so head/shoulder movement continues instead of freezing. Auto correction requires a speech-mode manifest and matching input-audio SHA-256. "
                 "Even then, repeated pauses are corrected only when the mapped source time was also silent during Echo conditioning. "
                 "Force uses a 0.16s gate/correction threshold and bypasses correction mode/audio identity checks, but still requires verified source-time silence. "
                 "Neither gate nor correction guarantees perfect lip-sync, and neither retimes Echo head/shoulder gesture."),
    }
    print("MuseTalk pause conditioning gate: {} | {} interval(s), {} samples zeroed".format(
        pause_gate_record["status"], pause_gate_record["interval_count"], pause_gate_record["gated_sample_count"],
    ))
    if not closure_enabled:
        print("Post-render pause correction: skipped ({})".format(closure_reason))
    else:
        print("Post-render pause correction: enabled ({}, minimum {:.2f}s)".format(closure_reason, closure_min_seconds))
    outputs: List[Dict[str, Any]] = []
    settings = [("first", args.bbox_shift, args.parsing_mode, args.audio_offset_ms)]
    if args.action == "benchmark":
        settings.append(("cached", args.bbox_shift, args.parsing_mode, args.audio_offset_ms))
    elif args.action == "calibrate":
        if args.audio_offset_sweep:
            settings = [("jaw_offset_m40ms", 0, "jaw", -40),
                        ("jaw_offset_0ms", 0, "jaw", 0),
                        ("jaw_offset_p40ms", 0, "jaw", 40)]
        else:
            settings = [("baseline", 0, "jaw", args.audio_offset_ms),
                        ("raw_mask", 0, "raw", args.audio_offset_ms)]
        report["manual_lip_sync_review_required"] = True
        report["calibration_note"] = (
            ("Optional offset sweep compares jaw parsing at -40/0/+40 ms. Every variant reloads MuseTalk; "
             "choose by listening and frame review, since no phoneme/sync score is inferred." if args.audio_offset_sweep else
             "MuseTalk v1.5 on this Windows setup forces bbox_shift=0. Compare jaw/raw parsing masks; "
             "timestamp/codec checks do not score phoneme accuracy. Review speech and pauses manually.")
        )
    video_count = len(settings)
    for index, (variant, shift, parsing, audio_offset_ms) in enumerate(settings, 1):
        variant_args = argparse.Namespace(**vars(args))
        variant_args.bbox_shift, variant_args.parsing_mode = shift, parsing
        variant_args.audio_offset_ms = audio_offset_ms
        muse_meta, muse_data = _run_one_musetalk(
            variant_args, base_video, paths, job_dir, index,
            require_cache_hit=args.action == "benchmark" and index == 2,
            conditioning_audio=conditioning_audio[audio_offset_ms],
        )
        muse_meta["variant"] = variant
        _append_phase(report, "musetalk_video_{}_wall".format(index), muse_meta["musetalk_wall_seconds"],
                      "Full run_pipeline wall time, including runtime validation, audio normalization, cache work, backend/model load, inference and output verification.",
                      cache_state=muse_meta["cache_state"], cache_hit=muse_meta["avatar_cache_hit"], video_index=index)
        manifest = muse_data["manifest"]
        run_manifest_path = Path(muse_meta["render_manifest"])
        muse_meta["render_manifest"] = str(run_manifest_path)
        muse_meta["model_weights_reloaded_for_this_process"] = bool(manifest.get("model_weights_reloaded_for_this_process", True))
        original_intermediate = muse_data["path"]
        conditioning_variant = conditioning_variant_records[str(audio_offset_ms)]
        unshifted_audio_sha256 = musetalk.sha256_file(unshifted_audio)
        conditioning_differs_from_output = conditioning_variant["sha256"] != unshifted_audio_sha256
        needs_audio_restore = audio_offset_ms != 0 or conditioning_differs_from_output
        muse_data["audio_conditioning"] = {
            "offset_ms": audio_offset_ms,
            "sign": "positive delays mouth relative to original audio; negative advances mouth",
            "conditioning_audio": str(conditioning_audio[audio_offset_ms].resolve()),
            "conditioning_audio_sha256": conditioning_variant["sha256"],
            "sample_rate": conditioning_variant["sample_rate"],
            "sample_count": conditioning_variant["sample_count"],
            "duration_seconds": conditioning_variant["duration_seconds"],
            "pause_gate": conditioning_variant["pause_gate"],
            "unshifted_output_audio": str(unshifted_audio.resolve()),
            "conditioning_audio_only": audio_offset_ms != 0,
            "conditioning_waveform_differs_from_output": conditioning_differs_from_output,
        }
        audio_restore_wall = 0.0
        audio_restore_record: Dict[str, Any] = {
            "status": "not_needed; MuseTalk conditioned with unshifted audio",
            "source": str(unshifted_audio.resolve()), "source_sha256": unshifted_audio_sha256,
        }
        if needs_audio_restore:
            audio_restore_started = time.perf_counter()
            restored_intermediate = job_dir / "intermediate" / ("audio_unshifted_video_{}.mp4".format(index))
            audio_restore_record = remux_unshifted_audio(
                original_intermediate, unshifted_audio, restored_intermediate,
                ffmpeg, ffprobe, muse_data["actual_audio_seconds"],
            )
            audio_restore_wall = time.perf_counter() - audio_restore_started
            muse_data["path"] = restored_intermediate
            muse_meta["audio_intermediate_original"] = str(original_intermediate.resolve())
        muse_meta["audio_output_restoration"] = audio_restore_record
        muse_meta["audio_output_restoration_required"] = needs_audio_restore
        muse_meta["audio_offset_restore_wall_seconds"] = round(audio_restore_wall, 3)
        _append_phase(report, "audio_offset_restore_video_{}_wall".format(index), audio_restore_wall,
                      "Restore unshifted normalized source audio when conditioning was gated or offset; AAC is copied by later phases.",
                      video_index=index)
        closure_started = time.perf_counter()
        if not closure_enabled:
            skipped_pause_intervals = detect_silence_intervals(
                unshifted_audio, min_duration_seconds=closure_min_seconds,
            )
            closure_record = {"status": "skipped", "reason": closure_reason,
                              "reference_source": "existing_motion_base_video",
                              "reference_cache_state": "not_needed; reuses existing Echo motion base",
                              "requested_intervals": skipped_pause_intervals,
                              "intervals": [], "uncovered_intervals": skipped_pause_intervals,
                              "audio_unchanged": True,
                              "fallback": "correction not attempted by the selected policy"}
        elif pause_reference_audio is None:
            requested_pause_intervals = detect_silence_intervals(
                unshifted_audio, min_duration_seconds=closure_min_seconds,
            )
            closure_record = {
                "status": "skipped_no_verified_reference_audio",
                "reason": pause_reference_audio_record.get("reason", "Echo conditioning audio could not be verified."),
                "reference_source": "existing_motion_base_video",
                "reference_cache_state": "not_needed; reuses existing Echo motion base",
                "reference_audio_provenance": pause_reference_audio_record,
                "requested_intervals": requested_pause_intervals,
                "intervals": [],
                "uncovered_intervals": requested_pause_intervals,
                "uncovered_duration_seconds": round(sum(item["duration_seconds"] for item in requested_pause_intervals), 6),
                "audio_unchanged": True,
                "fallback": "No frame was restored because source-time silence could not be verified.",
            }
        else:
            corrected_intermediate = job_dir / "intermediate" / ("pause_closed_video_{}.mp4".format(index))
            closure_record = apply_pause_mouth_closure(
                muse_data["path"], base_video, unshifted_audio, corrected_intermediate,
                ffmpeg, ffprobe, muse_data["actual_audio_seconds"], FPS, closure_min_seconds,
                reference_audio=pause_reference_audio,
            )
            closure_record["reference_audio_provenance"] = pause_reference_audio_record
            if closure_record["status"] == "applied":
                muse_data["path"] = corrected_intermediate
        closure_wall = time.perf_counter() - closure_started
        closure_record["requested_policy"] = args.pause_mouth_closure
        closure_record["source_mouth_mode"] = source_mouth_mode or "unknown"
        muse_meta["pause_mouth_closure"] = closure_record
        muse_meta["pause_mouth_closure_wall_seconds"] = round(closure_wall, 3)
        muse_meta["musetalk_intermediate_original"] = str(original_intermediate.resolve())
        muse_meta["intermediate_for_hd_export"] = str(muse_data["path"].resolve())
        _append_phase(report, "pause_mouth_closure_video_{}_wall".format(index), closure_wall,
                      "Conservative unshifted-WAV pause detection and same-frame motion-base restore; audio stream is copied unchanged.",
                      video_index=index)
        output_name = "vertical_ad_1080x1920.mp4" if video_count == 1 else "vertical_ad_1080x1920_{}.mp4".format(variant)
        final_output = job_dir / output_name
        export_seconds, exported = export_hd_video(
            muse_data["path"], final_output, ffmpeg, ffprobe, muse_data["actual_audio_seconds"],
            job_dir / "logs" / ("hd_export_video_{}.log".format(index)),
        )
        _append_phase(report, "hd_export_video_{}_wall".format(index), export_seconds,
                      "CPU libx264/Lanczos export, audio copy-or-AAC encode and ffprobe validation.",
                      video_index=index)
        video_entry = dict(muse_meta)
        video_entry["audio_conditioning"] = muse_data["audio_conditioning"]
        video_entry["audio_conditioning_preparation_wall_seconds"] = audio_preparation_seconds if index == 1 else 0.0
        video_entry["pause_reference_audio_preparation_wall_seconds"] = pause_reference_audio_wall if index == 1 else 0.0
        _write_output_metrics(video_entry, exported)
        video_entry["audio_normalization_seconds"] = manifest.get("audio_normalization_seconds")
        video_entry["backend_process_seconds"] = manifest.get("backend_process_seconds")
        outputs.append(video_entry)
        report["videos"] = outputs
        echo.write_json_atomic(report_path, report)

    first_video_total = (echo_wall + outputs[0].get("audio_conditioning_preparation_wall_seconds", 0.0)
                         + outputs[0]["musetalk_wall_seconds"]
                         + outputs[0].get("pause_reference_audio_preparation_wall_seconds", 0.0)
                         + outputs[0].get("audio_offset_restore_wall_seconds", 0.0)
                         + outputs[0].get("pause_mouth_closure_wall_seconds", 0.0)
                         + outputs[0]["hd_export_wall_seconds"])
    _append_phase(report, "video_1_render_phase_sum_including_shared_echo", first_video_total,
                  "Sum of Echo (or 0 when base reused) + MuseTalk + optional pause-mouth closure + HD export; excludes preflight and metadata-query/reporting overhead.",
                  cache_state=outputs[0]["cache_state"], cache_hit=outputs[0]["avatar_cache_hit"], video_index=1)
    if args.action == "benchmark":
        second_total = (outputs[1].get("audio_conditioning_preparation_wall_seconds", 0.0)
                        + outputs[1]["musetalk_wall_seconds"]
                        + outputs[1].get("pause_reference_audio_preparation_wall_seconds", 0.0)
                        + outputs[1].get("audio_offset_restore_wall_seconds", 0.0)
                        + outputs[1].get("pause_mouth_closure_wall_seconds", 0.0)
                        + outputs[1]["hd_export_wall_seconds"])
        _append_phase(report, "video_2_reuse_render_phase_sum", second_total,
                      "Second ad on same motion base; includes MuseTalk reload, optional pause-mouth closure and reuses avatar preprocessing cache.",
                      cache_state=outputs[1]["cache_state"], cache_hit=outputs[1]["avatar_cache_hit"], video_index=2)
    whole_job = time.perf_counter() - started
    report.update({"status": "complete", "videos": outputs, "echo_generation_wall_seconds": round(echo_wall, 3),
                   "whole_job_wall_seconds": round(whole_job, 3),
                   "whole_job_includes": "preflight + optional one-time Echo generation + audio preparation + all MuseTalk processes + unshifted audio restoration when offset + optional pause-mouth closure + all HD exports + verification",
                   "timing_note": "Normalized wall seconds per 60 audio seconds are linear extrapolations when actual audio is shorter than 60s; benchmark retains actual duration. Avatar cache hit means preprocessing reuse; MuseTalk model weights reload every run.",
                   "no_telemetry_note": "No system RAM, GPU temperature, or background-app load telemetry is sampled."})
    echo.write_json_atomic(report_path, report)
    write_phase_csv(phase_csv_path, report["phase_timings"])
    for item in outputs:
        print("Verified 1080x1920 output: {} | duration {:.3f}s | cache {} | MuseTalk+audio+pause-fix+export {:.1f}s".format(
            item["output"]["path"], item["audio_duration_seconds"], item["cache_state"],
            item.get("audio_conditioning_preparation_wall_seconds", 0.0) + item["musetalk_wall_seconds"]
            + item.get("audio_offset_restore_wall_seconds", 0.0)
            + item.get("pause_mouth_closure_wall_seconds", 0.0) + item["hd_export_wall_seconds"],
        ))
        print("Normalized 60s wall estimate: {:.1f}s{}".format(
            item["normalized_wall_seconds_per_60_audio_seconds_extrapolation"],
            " (extrapolation; actual audio shorter than 60s)" if not item["normalized_60s_is_measured"] else " (measured)",
        ))
    print("Whole job: {:.1f}s | report: {} | phases: {}".format(whole_job, report_path, phase_csv_path))
    return 0


def report_filename(action: str) -> str:
    return {"dry-run": "dry_run_report.json", "benchmark": "benchmark_report.json",
            "calibrate": "lip_calibration_report.json", "run": "vertical_ad_report.json"}[action]


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = make_parser()
    args = parser.parse_args(argv)
    if args.duration is None:
        args.duration = 3.24 if args.action == "calibrate" else DEFAULT_DURATION
    try:
        validate_audio_offset_ms(args.audio_offset_ms)
    except ValueError as error:
        parser.error(str(error))
    if args.action == "calibrate" and args.duration > 6:
        parser.error("calibrate chỉ test tối đa 6 giây; duyệt khẩu hình trước khi chạy dài.")
    if args.audio_offset_sweep:
        if args.action != "calibrate":
            parser.error("--audio-offset-sweep chỉ dùng với action calibrate.")
        if args.base_video is None:
            parser.error("--audio-offset-sweep cần --base-video để tránh mất thời gian sinh motion base.")
        if args.audio_offset_ms != 0:
            parser.error("--audio-offset-sweep so sánh cố định -40/0/+40 ms; bỏ --audio-offset-ms hoặc dùng 0.")
    if args.batch_size < 1 or not math.isfinite(args.duration) or args.duration <= 0 or not -20 <= args.bbox_shift <= 20:
        parser.error("duration/batch-size phải dương; bbox-shift trong [-20, 20].")
    started = time.perf_counter()
    output_root = args.output_root.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    token = _datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]
    job_dir = output_root / ("job_" + token)
    job_dir.mkdir(parents=True, exist_ok=False)
    logs = job_dir / "logs"
    logs.mkdir()
    outer_log = logs / "vertical_ads.log"
    console_out, console_err = sys.stdout, sys.stderr
    report_path = job_dir / report_filename(args.action)
    report: Dict[str, Any] = {
        "schema_version": 1,
        "created_at": _datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "report_path": str(report_path),
        "phase_csv_path": str(job_dir / "phase_timings.csv"),
        "action": args.action,
        "job_directory": str(job_dir),
        "status": "running",
        "phase_timings": [],
    }
    try:
        with outer_log.open("w", encoding="utf-8", newline="\n") as log:
            sys.stdout = TeeStream(console_out, log)
            sys.stderr = TeeStream(console_err, log)
            print("Vertical ads test | action={} | profile={} | output={}".format(args.action, args.profile, job_dir))
            code = run_workflow(args, job_dir, report)
            return code
    except KeyboardInterrupt:
        report.update({"status": "interrupted", "error": "KeyboardInterrupt"})
        report["whole_job_wall_seconds"] = round(time.perf_counter() - started, 3)
        echo.write_json_atomic(report_path, report)
        write_phase_csv(job_dir / "phase_timings.csv", report.get("phase_timings", []))
        return 130
    except Exception as exc:
        report.update({"status": "failed", "error_type": type(exc).__name__, "error": str(exc),
                       "logs": str(outer_log), "partial_outputs_preserved": True,
                       "whole_job_wall_seconds": round(time.perf_counter() - started, 3)})
        echo.write_json_atomic(report_path, report)
        write_phase_csv(job_dir / "phase_timings.csv", report.get("phase_timings", []))
        print("Vertical ads run failed: {}".format(exc), file=console_err)
        print("Partial report: {}".format(report_path), file=console_err)
        return 1
    finally:
        sys.stdout = console_out
        sys.stderr = console_err


if __name__ == "__main__":
    raise SystemExit(main())
