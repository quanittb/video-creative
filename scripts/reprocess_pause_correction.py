#!/usr/bin/env python3
"""Reapply exact-source-aligned pause correction to a completed vertical-ad job."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import wave
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import echo_flash_windows as echo
import test_vertical_ads as ads
import test_cached_musetalk as musetalk


def _required_file(path: Path, label: str) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError("Không tìm thấy {}: {}".format(label, resolved))
    return resolved


def _validated_output_label(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,47}", value):
        raise ValueError("--output-label must be 1-48 letters, digits, '_' or '-' and start with a letter or digit.")
    return value


def _reprocess_output_paths(
    job_dir: Path, correction_region: str, output_label: Optional[str],
) -> Dict[str, Path]:
    suffix = "source_aligned" if correction_region == "full-frame" else "mouth_only"
    tag = "_" + output_label if output_label else ""
    default_report = ("pause_reprocess_report.json" if correction_region == "full-frame"
                      else "pause_mouth_only_reprocess_report.json")
    report_name = (default_report if output_label is None
                   else "pause_{}_{}_reprocess_report.json".format(suffix, output_label))
    return {
        "corrected": job_dir / "intermediate" / "pause_{}{}_reprocessed_video_1.mp4".format(suffix, tag),
        "final_video": job_dir / "vertical_ad_1080x1920_pause_{}{}_reprocessed.mp4".format(suffix, tag),
        "report": job_dir / report_name,
        "unshifted_video": job_dir / "intermediate" / "reprocess_unshifted{}_video_1.mp4".format(tag),
        "silence_audio": job_dir / "intermediate" / "pause_silence_conditioning{}_16k_mono.wav".format(tag),
        "silence_donor_video": job_dir / "intermediate" / "pause_silence_conditioned_musetalk_donor{}.mp4".format(tag),
        "silence_donor_log": job_dir / "logs" / "pause_silence_conditioned_musetalk_donor{}.log".format(tag),
        "helper_log": job_dir / "logs" / "mouth_mask_extraction_reprocess{}.log".format(tag),
        "export_log": job_dir / "logs" / "hd_export_pause_{}{}_reprocessed.log".format(suffix, tag),
    }


def _ensure_outputs_unused(paths: Sequence[Path]) -> None:
    collision = next((path for path in paths if path.exists()), None)
    if collision is not None:
        raise FileExistsError("Output reprocess đã tồn tại; không ghi đè: {}".format(collision))


def _verified_job_inputs(job_dir: Path, motion_base: Optional[Path]) -> Dict[str, Any]:
    report_path = _required_file(job_dir / "vertical_ad_report.json", "vertical_ad_report.json")
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise RuntimeError("Không đọc được report job: {}".format(error)) from error
    videos = report.get("videos") or []
    if not videos:
        raise ValueError("Report job không có video đã render để reprocess.")
    video_entry = videos[0]
    policy = report.get("pause_mouth_closure_policy") or {}
    alignment = report.get("motion_audio_alignment") or {}
    old_closure = video_entry.get("pause_mouth_closure") or {}
    provenance = (old_closure.get("reference_audio_provenance")
                  or policy.get("reference_audio") or {})
    manifest_hash = str(policy.get("manifest_audio_sha256") or "")
    current_hash = str(policy.get("current_input_audio_sha256") or "")
    if policy.get("source_mouth_mode") != "speech":
        raise ValueError("Chỉ reprocess job có Echo mouth_mode=speech.")
    if (not manifest_hash or manifest_hash.lower() != current_hash.lower()
            or not policy.get("audio_identity_matches")
            or alignment.get("status") != "verified_match"
            or alignment.get("sha256_matches") is not True):
        raise ValueError("Từ chối reprocess: report không xác minh SHA-256 audio Echo khớp audio hiện tại.")
    if (provenance.get("status") != "verified"
            or str(provenance.get("manifest_audio_sha256") or "").lower() != manifest_hash.lower()
            or str(provenance.get("source_sha256") or "").lower() != manifest_hash.lower()):
        raise ValueError("Từ chối reprocess: provenance audio Echo không khớp manifest.")

    if motion_base is None:
        raise ValueError("Cần --motion-base gốc để khôi phục đúng frame theo ping-pong mapping; không dùng pause_closed_video_1.mp4 làm donor.")
    motion_base = _required_file(motion_base, "motion base")

    intermediate = job_dir / "intermediate"
    unshifted_audio = _required_file(intermediate / "audio_unshifted_16k_mono.wav", "audio_unshifted_16k_mono.wav")
    expected_output_audio_hash = str((report.get("audio_alignment") or {}).get("unshifted_normalized_audio_sha256") or "")
    if not expected_output_audio_hash or musetalk.sha256_file(unshifted_audio).lower() != expected_output_audio_hash.lower():
        raise ValueError("SHA-256 WAV unshifted không khớp report; dừng để bảo toàn tiếng gốc.")

    echo_reference_audio = _required_file(
        intermediate / "echo_reference_audio_16k_mono.wav", "echo_reference_audio_16k_mono.wav",
    )
    expected_reference_hash = str(old_closure.get("reference_audio_sha256") or "")
    if not expected_reference_hash or musetalk.sha256_file(echo_reference_audio).lower() != expected_reference_hash.lower():
        raise ValueError("SHA-256 Echo reference WAV không khớp report; không thể xác minh frame nguồn im lặng.")

    motion_metadata = report.get("motion_base") or {}
    expected_base_hash = str(motion_metadata.get("sha256") or "")
    if not expected_base_hash:
        raise ValueError("Report job thiếu SHA-256 motion base.")
    if musetalk.sha256_file(motion_base).lower() != expected_base_hash.lower():
        raise ValueError("SHA-256 motion base không khớp report của job; dừng để tránh dùng nhầm video.")
    reference_video = motion_base
    reference_policy = "exact_pingpong_source_frame_mapping"

    audio_unshifted_video = intermediate / "audio_unshifted_video_1.mp4"
    if audio_unshifted_video.is_file():
        rendered_video = audio_unshifted_video.resolve()
        restore_audio = False
    else:
        rendered_video = _required_file(intermediate / "musetalk_video_1.mp4", "musetalk_video_1.mp4")
        restore_audio = True
    return {
        "report_path": report_path,
        "report": report,
        "video_entry": video_entry,
        "provenance": provenance,
        "motion_base": motion_base,
        "reference_video": reference_video,
        "reference_policy": reference_policy,
        "motion_metadata": motion_metadata,
        "rendered_video": rendered_video,
        "restore_audio": restore_audio,
        "unshifted_audio": unshifted_audio,
        "echo_reference_audio": echo_reference_audio,
    }


def _write_exact_silence_wav(path: Path, sample_count: int, sample_rate: int = 16000) -> Dict[str, Any]:
    if sample_count < 1 or sample_rate < 1:
        raise ValueError("Silent donor WAV requires a positive sample count and sample rate.")
    if path.exists():
        raise FileExistsError("Refusing to overwrite silence-conditioned donor WAV: {}".format(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name("." + path.name + ".partial")
    if temporary.exists():
        raise FileExistsError("Refusing to overwrite temporary donor WAV: {}".format(temporary))
    chunk_samples = 65536
    remaining = sample_count
    try:
        with wave.open(str(temporary), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(sample_rate)
            silence_chunk = b"\x00\x00" * chunk_samples
            while remaining:
                count = min(remaining, chunk_samples)
                output.writeframesraw(silence_chunk[:count * 2])
                remaining -= count
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    with wave.open(str(path), "rb") as audio:
        actual_samples = audio.getnframes()
        actual_duration = actual_samples / float(audio.getframerate())
        if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) != (1, 2, sample_rate):
            raise ValueError("Created silent donor WAV does not have 16 kHz mono PCM16 format.")
        if actual_samples != sample_count:
            raise ValueError("Created silent donor WAV sample count differs from requested frame-aligned duration.")
    return {
        "path": str(path.resolve()),
        "sample_rate": sample_rate,
        "channels": 1,
        "sample_width_bytes": 2,
        "sample_count": actual_samples,
        "duration_seconds": round(actual_duration, 9),
        "sha256": musetalk.sha256_file(path),
        "digital_silence": True,
    }


def _render_silence_conditioned_donor(
    job_dir: Path,
    inputs: Mapping[str, Any],
    ffmpeg: str,
    ffprobe: str,
    musetalk_dir: Optional[str],
    musetalk_python: Optional[str],
    output_label: Optional[str] = None,
) -> Dict[str, Any]:
    """Render a motion-base-length neutral donor and require the cache from the original job."""
    video_entry = inputs["video_entry"]
    cache_value = video_entry.get("avatar_cache_path")
    if not cache_value:
        raise ValueError("Job report thiếu videos[0].avatar_cache_path; không thể chứng minh tái sử dụng avatar cache.")
    expected_cache = Path(str(cache_value)).expanduser().resolve()
    cache_root = expected_cache.parent
    settings = video_entry.get("lip_sync_settings") or {}
    bbox_shift = int(settings.get("bbox_shift", 0))
    parsing_mode = str(settings.get("parsing_mode") or "jaw")
    audio_padding_left = int(settings.get("audio_padding_left", 2))
    audio_padding_right = int(settings.get("audio_padding_right", 2))
    paths = musetalk.discover_musetalk_paths(musetalk_dir, musetalk_python)
    musetalk.validate_safe_cache_root(cache_root)
    ffmpeg, ffprobe = musetalk.find_ffmpeg_pair(ffmpeg, ffprobe)
    source_frames = ads.count_video_frames(inputs["motion_base"], ffprobe)
    reported_fps = float(inputs["motion_metadata"].get("fps") or ads.FPS)
    if abs(reported_fps - ads.FPS) > 0.01:
        raise ValueError("Silence-conditioned donor currently requires the verified 25 FPS motion-base profile.")
    fps = ads.FPS
    sample_numerator = source_frames * 16000
    if fps < 1 or sample_numerator % fps:
        raise ValueError("Motion-base frame duration cannot be represented as an exact 16 kHz WAV sample count.")
    sample_count = sample_numerator // fps
    duration = source_frames / float(fps)
    output_paths = _reprocess_output_paths(job_dir, "mouth-only", output_label)
    silence_audio = output_paths["silence_audio"]
    donor_video = output_paths["silence_donor_video"]
    log_path = output_paths["silence_donor_log"]
    for path, label in ((donor_video, "neutral donor video"), (log_path, "neutral donor log")):
        if path.exists():
            raise FileExistsError("Refusing to overwrite {}: {}".format(label, path))
    silence_record = _write_exact_silence_wav(silence_audio, sample_count)
    pipeline_args = {
        "base_video": inputs["motion_base"],
        "audio": silence_audio,
        "duration": duration,
        "output": donor_video,
        "cache_dir": cache_root,
        "fps": fps,
        "batch_size": 2,
        "musetalk_dir": paths.root,
        "musetalk_python": paths.python,
        "ffmpeg_override": ffmpeg,
        "ffprobe_override": ffprobe,
        "motion_policy": "error",
        "bbox_shift": bbox_shift,
        "parsing_mode": parsing_mode,
        "audio_padding_left": audio_padding_left,
        "audio_padding_right": audio_padding_right,
    }
    dry_run = musetalk.run_pipeline("dry-run", **pipeline_args)
    dry_cache = Path(dry_run["cache_path"]).resolve()
    if (not dry_run.get("cache_hit") or dry_cache != expected_cache
            or not expected_cache.is_dir()):
        raise RuntimeError(
            "Từ chối chạy silence donor: cache dry-run không khớp cache trong job report "
            "(expected={}, actual={}, hit={}).".format(expected_cache, dry_cache, dry_run.get("cache_hit"))
        )
    pipeline_args["log_path"] = log_path
    run = musetalk.run_pipeline("run", **pipeline_args)
    run_cache = Path(run["cache_path"]).resolve()
    if not run.get("cache_hit") or run_cache != expected_cache:
        raise RuntimeError("MuseTalk silence donor không xác nhận reuse đúng avatar cache trong report job.")
    if not donor_video.is_file():
        raise RuntimeError("MuseTalk không tạo silence-conditioned donor video: {}".format(donor_video))
    donor_info = ads.probe_media(donor_video, ffprobe)
    donor_stream = ads.stream_by_type(donor_info, "video")
    if donor_stream is None:
        raise ValueError("Silence-conditioned donor output không có video stream.")
    donor_frames = ads.count_video_frames(donor_video, ffprobe)
    donor_fps = echo.parse_fraction(str(donor_stream.get("avg_frame_rate") or "0/1"))
    expected_dimensions = (int(inputs["motion_metadata"].get("width", 0)),
                          int(inputs["motion_metadata"].get("height", 0)))
    donor_dimensions = (int(donor_stream.get("width", 0)), int(donor_stream.get("height", 0)))
    if (donor_frames != source_frames or donor_dimensions != expected_dimensions
            or abs(donor_fps - fps) > 0.01):
        raise ValueError(
            "Silence-conditioned donor failed validation: expected {} frames, {}x{}, {} FPS; got {} frames, {}x{}, {:.3f} FPS.".format(
                source_frames, expected_dimensions[0], expected_dimensions[1], fps,
                donor_frames, donor_dimensions[0], donor_dimensions[1], donor_fps,
            )
        )
    return {
        "status": "generated",
        "mode": "same_motion_base_silence_conditioned_musetalk",
        "motion_base": str(inputs["motion_base"]),
        "motion_base_sha256": inputs["motion_metadata"]["sha256"],
        "silent_audio": silence_record,
        "donor_video": str(donor_video.resolve()),
        "donor_video_sha256": musetalk.sha256_file(donor_video),
        "donor_video_frame_count": donor_frames,
        "donor_video_fps": donor_fps,
        "donor_video_dimensions": list(donor_dimensions),
        "avatar_cache_path": str(run_cache),
        "avatar_cache_hit": bool(run.get("cache_hit")),
        "cache_preflight_hit": bool(dry_run.get("cache_hit")),
        "cache_preflight_path": str(dry_cache),
        "lip_sync_settings": {
            "bbox_shift": bbox_shift, "parsing_mode": parsing_mode,
            "audio_padding_left": audio_padding_left, "audio_padding_right": audio_padding_right,
        },
        "audio_duration_seconds": run.get("audio_duration"),
        "backend_seconds": run.get("backend_seconds"),
        "log": str(log_path.resolve()),
        "visual_quality_status": "not_assessed_by_pipeline; inspect output frames and diagnostics",
    }


def reprocess(
    job_dir: Path, motion_base: Optional[Path], ffmpeg_arg: str, ffprobe_arg: str,
    correction_region: str = "full-frame", musetalk_dir: Optional[str] = None,
    musetalk_python: Optional[str] = None, mouth_donor_mode: str = "quiet-source",
    output_label: Optional[str] = None,
) -> Dict[str, Any]:
    if correction_region not in ("full-frame", "mouth-only"):
        raise ValueError("--pause-correction-region must be full-frame or mouth-only.")
    if mouth_donor_mode not in ("quiet-source", "silence-conditioned"):
        raise ValueError("--mouth-donor-mode must be quiet-source or silence-conditioned.")
    if mouth_donor_mode == "silence-conditioned" and correction_region != "mouth-only":
        raise ValueError("--mouth-donor-mode silence-conditioned requires --pause-correction-region mouth-only.")
    output_label = _validated_output_label(output_label)
    job_dir = _required_file(job_dir / "vertical_ad_report.json", "vertical_ad_report.json").parent
    inputs = _verified_job_inputs(job_dir, motion_base)
    ffmpeg, ffprobe = echo.resolve_tools(ffmpeg_arg, ffprobe_arg)
    output_paths = _reprocess_output_paths(job_dir, correction_region, output_label)
    suffix = "source_aligned" if correction_region == "full-frame" else "mouth_only"
    corrected = output_paths["corrected"]
    final_video = output_paths["final_video"]
    report_path = output_paths["report"]
    protected_outputs = [corrected, final_video, report_path, output_paths["helper_log"], output_paths["export_log"]]
    if inputs["restore_audio"]:
        protected_outputs.append(output_paths["unshifted_video"])
    if mouth_donor_mode == "silence-conditioned":
        protected_outputs.extend((
            output_paths["silence_audio"], output_paths["silence_donor_video"],
            output_paths["silence_donor_log"],
        ))
    _ensure_outputs_unused(protected_outputs)
    unshifted_video = inputs["rendered_video"]
    reencoded_audio_restore: Optional[Dict[str, Any]] = None
    if inputs["restore_audio"]:
        unshifted_video = output_paths["unshifted_video"]
        reencoded_audio_restore = ads.remux_unshifted_audio(
            inputs["rendered_video"], inputs["unshifted_audio"], unshifted_video,
            ffmpeg, ffprobe,
            float((inputs["report"].get("effective_audio_duration_seconds") or 0.0)),
        )

    actual_data = ads.probe_media(unshifted_video, ffprobe)
    actual_audio = ads.stream_by_type(actual_data, "audio")
    actual_video = ads.stream_by_type(actual_data, "video")
    if actual_audio is None or actual_video is None:
        raise ValueError("Intermediate không có audio để giữ nguyên qua reprocess.")
    duration = ads.media_duration(actual_data, actual_audio)
    reference_data = ads.probe_media(inputs["reference_video"], ffprobe)
    reference_stream = ads.stream_by_type(reference_data, "video")
    if reference_stream is None:
        raise ValueError("Motion base tham chiếu không có video stream.")
    expected_dimensions = (int(inputs["motion_metadata"].get("width", 0)),
                           int(inputs["motion_metadata"].get("height", 0)))
    reference_dimensions = (int(reference_stream.get("width", 0)), int(reference_stream.get("height", 0)))
    rendered_dimensions = (int(actual_video.get("width", 0)), int(actual_video.get("height", 0)))
    expected_fps = float(inputs["motion_metadata"].get("fps") or 0.0)
    reference_fps = echo.parse_fraction(str(reference_stream.get("avg_frame_rate") or "0/1"))
    rendered_fps = echo.parse_fraction(str(actual_video.get("avg_frame_rate") or "0/1"))
    if (reference_dimensions != expected_dimensions or rendered_dimensions != expected_dimensions
            or abs(reference_fps - expected_fps) > 0.01 or abs(rendered_fps - expected_fps) > 0.01):
        raise ValueError("Motion base, report metadata và MuseTalk intermediate phải cùng kích thước/FPS.")

    silence_donor_record: Optional[Dict[str, Any]] = None
    if mouth_donor_mode == "silence-conditioned":
        silence_donor_record = _render_silence_conditioned_donor(
            job_dir, inputs, ffmpeg, ffprobe, musetalk_dir, musetalk_python, output_label,
        )

    started = time.perf_counter()
    correction = ads.apply_pause_mouth_closure(
        unshifted_video, inputs["reference_video"], inputs["unshifted_audio"], corrected,
        ffmpeg, ffprobe, duration, ads.FPS,
        float((inputs["report"].get("pause_mouth_closure_policy") or {}).get("minimum_pause_seconds") or ads.PAUSE_MIN_DURATION_SECONDS),
        reference_audio=inputs["echo_reference_audio"],
        reference_audio_provenance=inputs["provenance"],
        requested_policy="auto",
        reference_source=("exact_pingpong_source_frame_mapping" if correction_region == "full-frame"
                          else "same_motion_base_silence_conditioned_musetalk_exact_pingpong_frame"
                          if mouth_donor_mode == "silence-conditioned" else
                          "verified_quiet_source_mouth_donor_bank"),
        correction_region=correction_region,
        mouth_donor_mode=mouth_donor_mode,
        silence_conditioned_donor_video=(Path(silence_donor_record["donor_video"])
                                         if silence_donor_record else None),
        musetalk_dir=musetalk_dir,
        musetalk_python=musetalk_python,
        helper_log_path=output_paths["helper_log"],
    )
    if silence_donor_record is not None:
        correction["silence_conditioned_donor_render"] = silence_donor_record
        correction["reference_cache_state"] = (
            "REUSED avatar cache from the source job report; separate silence-conditioned MuseTalk donor pass rendered"
        )
    if correction["status"] not in ("applied", "partially_applied"):
        report = {
            "status": "skipped",
            "reason": correction["status"],
            "correction_region": correction_region,
            "mouth_donor_mode": mouth_donor_mode,
            "job_directory": str(job_dir),
            "output_label": output_label,
            "report_path": str(report_path),
            "motion_base": str(inputs["motion_base"] or inputs["report"].get("motion_base", {}).get("path")),
            "reference_policy": (inputs["reference_policy"] if correction_region == "full-frame"
                                 else "same_motion_base_silence_conditioned_musetalk_exact_pingpong_frame"
                                 if mouth_donor_mode == "silence-conditioned" else
                                 "verified_quiet_source_mouth_donor_bank"),
            "silence_conditioned_donor_render": silence_donor_record,
            "pause_correction": correction,
            "note": ("Không tạo final đã sửa vì pause correction không có đủ frame/donor đạt kiểm tra; Echo và full-audio lip-sync không được chạy lại."
                     + (" MuseTalk đã chạy pass silence-conditioned donor." if silence_donor_record else "")),
        }
        echo.write_json_atomic(report_path, report)
        raise RuntimeError("Pause correction bị bỏ qua: {}. Report: {}".format(correction["status"], report_path))

    export_seconds, exported = ads.export_hd_video(
        corrected, final_video, ffmpeg, ffprobe, duration,
        output_paths["export_log"],
    )
    report = {
        "status": ("complete_with_partial_pause_coverage"
                   if correction.get("pause_coverage_status") == "partial"
                   or correction["status"] == "partially_applied" else "complete"),
        "correction_region": correction_region,
        "mouth_donor_mode": mouth_donor_mode,
        "job_directory": str(job_dir),
        "output_label": output_label,
        "source_video": str(inputs["rendered_video"]),
        "input_audio_restoration": reencoded_audio_restore,
        "unshifted_audio": str(inputs["unshifted_audio"]),
        "unshifted_audio_sha256": musetalk.sha256_file(inputs["unshifted_audio"]),
        "echo_reference_audio": str(inputs["echo_reference_audio"]),
        "motion_base": str(inputs["motion_base"] or inputs["report"].get("motion_base", {}).get("path")),
        "motion_base_sha256": inputs["motion_metadata"]["sha256"],
        "source_frame_reference_video": str(inputs["reference_video"]),
        "reference_policy": (inputs["reference_policy"] if correction_region == "full-frame"
                             else "same_motion_base_silence_conditioned_musetalk_exact_pingpong_frame"
                             if mouth_donor_mode == "silence-conditioned" else
                             "verified_quiet_source_mouth_donor_bank"),
        "silence_conditioned_donor_render": silence_donor_record,
        "manifest_audio_identity": {
            "status": "verified_match",
            "manifest_audio_sha256": (inputs["report"].get("pause_mouth_closure_policy") or {}).get("manifest_audio_sha256"),
            "current_audio_sha256": (inputs["report"].get("pause_mouth_closure_policy") or {}).get("current_input_audio_sha256"),
        },
        "pause_correction": correction,
        "corrected_intermediate": str(corrected),
        "final_output": str(final_video),
        "export": exported,
        "export_wall_seconds": round(export_seconds, 3),
        "postprocess_wall_seconds": round(time.perf_counter() - started, 3),
        "models_rerun": silence_donor_record is not None,
        "models_rerun_scope": "Echo and full-audio lip-sync were not rerun; silence-conditioned mode performs a separate MuseTalk donor inference.",
        "musetalk_silence_conditioned_donor_rendered": silence_donor_record is not None,
        "report_path": str(report_path),
        "audio_policy": "use the job's unshifted audio; AAC stream is copied through correction and HD export",
        "scope_note": ("Only output pauses whose exact MuseTalk ping-pong source frame is also verified silent are restored. Other pause frames remain unchanged and are reported uncovered; visual closure still requires human review."
                       if correction_region == "full-frame" else
                       "Silence-conditioned mode uses only the exact ping-pong-mapped frame from a separate MuseTalk pass over the same motion base; parser, closure, or geometry failure leaves that output frame unchanged. No unrelated donor fallback is allowed. Diagnostics describe preparation only, not visual quality; inspect the output before use."
                       if mouth_donor_mode == "silence-conditioned" else
                       "Only parser-validated lip pixels in output pause frames are replaced from a verified quiet-source frame with confident normalized face geometry. All other pixels/audio remain from the MuseTalk intermediate; this experimental path requires human A/B review."),
    }
    echo.write_json_atomic(report_path, report)
    return report


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reprocess a completed job at verified pauses. Echo is not rerun; MuseTalk reruns only when mouth-only silence-conditioned donors are explicitly selected.",
    )
    parser.add_argument("--job-dir", required=True, type=Path, help="Completed output\\vertical_ads\\job_... folder.")
    parser.add_argument("--motion-base", required=True, type=Path, help="Original Echo motion_base.mp4 whose SHA-256 is in the job report; required for exact ping-pong frame mapping.")
    parser.add_argument("--pause-correction-region", choices=("full-frame", "mouth-only"), default="full-frame",
                        help="full-frame preserves the prior reprocess behavior; mouth-only is an opt-in semantic lip patch.")
    parser.add_argument("--mouth-donor-mode", choices=("quiet-source", "silence-conditioned"), default="quiet-source",
                        help="mouth-only donors: legacy quiet-source bank or same-motion-base silent MuseTalk pass with exact mapped-frame-only selection.")
    parser.add_argument("--output-label", default=None,
                        help="Optional suffix (1-48 letters/digits/_/-; starts with a letter/digit) so a new attempt writes beside prior outputs without overwriting them.")
    parser.add_argument("--musetalk-dir", default=None, help="MuseTalk checkout containing existing FaceParsing code and weights; omit for automatic discovery.")
    parser.add_argument("--musetalk-python", default=None, help="Python executable of the installed MuseTalk runtime; omit for automatic discovery.")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--ffprobe", default="ffprobe")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = make_parser().parse_args(argv)
    try:
        report = reprocess(
            args.job_dir, args.motion_base, args.ffmpeg, args.ffprobe,
            args.pause_correction_region, args.musetalk_dir, args.musetalk_python,
            args.mouth_donor_mode, args.output_label,
        )
    except Exception as error:
        print("ERROR: {}".format(error), file=sys.stderr)
        return 1
    correction = report["pause_correction"]
    coverage = correction.get("pause_coverage_status")
    if coverage is not None:
        coverage_label = "đầy đủ" if coverage == "full" else "một phần" if coverage == "partial" else "không có frame nào"
        corrected_count = int(correction.get("corrected_pause_frame_count", 0))
        requested_count = int(correction.get("requested_output_pause_frame_count", 0))
        ratio = float(correction.get("pause_frame_coverage_ratio", 0.0))
        rerun_note = ("không chạy lại Echo hoặc lip-sync MuseTalk theo audio; đã render pass donor MuseTalk im lặng"
                      if report.get("musetalk_silence_conditioned_donor_rendered")
                      else "không chạy lại Echo/MuseTalk")
        print("Reprocess xong, {}; độ phủ frame pause trong video {}. Frame có patch đã composite: {}/{} ({:.1%}); chưa xác nhận trực quan miệng đã khép tự nhiên.".format(
            rerun_note, coverage_label, corrected_count, requested_count, ratio,
        ))
    else:
        rerun_note = ("Echo không chạy lại; đã render pass donor MuseTalk im lặng"
                      if report.get("musetalk_silence_conditioned_donor_rendered")
                      else "không chạy lại Echo/MuseTalk")
        print("Reprocess thành công, {} (mapping: {}).".format(rerun_note, report["reference_policy"]))
    all_uncovered = correction.get("uncovered_intervals") or []
    video_uncovered = correction.get("video_uncovered_intervals")
    if video_uncovered is None:
        video_uncovered = [
            item for item in all_uncovered
            if item.get("reason") != "audio_pause_after_end_of_rendered_video"
        ]
    tail_intervals = correction.get("audio_tail_pause_intervals")
    if tail_intervals is None:
        tail_intervals = [
            item for item in all_uncovered
            if item.get("reason") == "audio_pause_after_end_of_rendered_video"
        ]
    classified_video_uncovered_seconds = sum(
        float(item["duration_seconds"]) for item in video_uncovered
    )
    video_uncovered_seconds = float(correction.get(
        "video_uncovered_duration_seconds", classified_video_uncovered_seconds,
    ))
    audio_tail_seconds = float(correction.get(
        "audio_tail_duration_seconds",
        sum(float(item["duration_seconds"]) for item in tail_intervals),
    ))
    print("Pause-time bên trong video nằm ngoài patch frame đầy đủ: {:.3f}s qua {} đoạn (có thể gồm biên pause ngắn hơn một frame).".format(
        video_uncovered_seconds, len(video_uncovered),
    ))
    for interval in video_uncovered:
        print("  {:.3f}–{:.3f}s ({:.3f}s): {}".format(
            float(interval["start_seconds"]), float(interval["end_seconds"]),
            float(interval["duration_seconds"]), interval.get("reason", "uncovered"),
        ))
    print("Audio pause nằm sau frame video cuối: {:.3f}s qua {} đoạn; audio được giữ nguyên.".format(
        audio_tail_seconds, len(tail_intervals),
    ))
    for interval in tail_intervals:
        print("  {:.3f}–{:.3f}s ({:.3f}s)".format(
            float(interval["start_seconds"]), float(interval["end_seconds"]),
            float(interval["duration_seconds"]),
        ))
    outside_video = correction.get("pause_frame_indices_outside_rendered_video") or []
    if outside_video:
        print("Pause frame index vượt số frame video (được giữ nguyên audio): {}".format(outside_video))
    uncorrected_frames = correction.get("uncorrected_output_pause_frame_indices") or []
    if uncorrected_frames:
        print("In-video pause frame chưa có patch mask/donor: {}".format(uncorrected_frames))
    print("Native: {}".format(report["corrected_intermediate"]))
    print("Final: {}".format(report["final_output"]))
    print("Report: {}".format(report.get("report_path") or Path(report["job_directory"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
