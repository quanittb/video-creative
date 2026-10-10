#!/usr/bin/env python3
"""Reapply verified quiet-motion pause correction to a completed vertical-ad job."""

from __future__ import annotations

import argparse
import json
import sys
import time
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
        raise ValueError("SHA-256 Echo reference WAV không khớp report; không thể xác minh quiet bank.")

    motion_metadata = report.get("motion_base") or {}
    expected_base_hash = str(motion_metadata.get("sha256") or "")
    if not expected_base_hash:
        raise ValueError("Report job thiếu SHA-256 motion base.")
    quiet_bank_intervals: Optional[list] = None
    if motion_base is not None:
        motion_base = _required_file(motion_base, "motion base")
        if musetalk.sha256_file(motion_base).lower() != expected_base_hash.lower():
            raise ValueError("SHA-256 motion base không khớp report của job; dừng để tránh dùng nhầm video.")
        reference_video = motion_base
        reference_policy = "original_motion_base"
    else:
        if old_closure.get("status") != "applied":
            raise ValueError("Không có motion base gốc; fallback cần old pause correction có status=applied.")
        if str(old_closure.get("reference_sha256") or "").lower() != expected_base_hash.lower():
            raise ValueError("Fallback bị từ chối: SHA-256 nguồn của old pause correction không khớp motion base report.")
        if str(old_closure.get("reference_source") or "") != "existing_motion_base_video":
            raise ValueError("Fallback bị từ chối: old pause correction không trỏ tới motion base đã duyệt.")
        donor_report_path = str(old_closure.get("output") or "").replace("\\", "/")
        if donor_report_path.rsplit("/", 1)[-1] != "pause_closed_video_1.mp4":
            raise ValueError("Fallback chỉ chấp nhận output pause_closed_video_1.mp4 có trong job.")
        reference_video = _required_file(intermediate / "pause_closed_video_1.mp4", "pause_closed_video_1.mp4")
        pause_detection = old_closure.get("pause_detection") or {}
        transition_seconds = pause_detection.get("transition_seconds")
        previous_intervals = old_closure.get("intervals") or []
        if not previous_intervals:
            raise ValueError("Fallback bị từ chối: report không có interval cũ đã sửa để xác định frame donor an toàn.")
        source_pauses = ads.detect_silence_intervals(echo_reference_audio, min_duration_seconds=1.0 / ads.FPS)
        quiet_bank_intervals = ads.safe_quiet_donor_intervals(
            source_pauses, previous_intervals, float(transition_seconds or 0.0),
        )
        if not quiet_bank_intervals:
            raise ValueError("Fallback bị từ chối: không có frame giao giữa source silence và old correction sau khi trim transition.")
        reference_policy = "previous_pause_closed_video_safe_quiet_overlap"

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
        "quiet_bank_intervals": quiet_bank_intervals,
        "motion_metadata": motion_metadata,
        "rendered_video": rendered_video,
        "restore_audio": restore_audio,
        "unshifted_audio": unshifted_audio,
        "echo_reference_audio": echo_reference_audio,
    }


def reprocess(job_dir: Path, motion_base: Optional[Path], ffmpeg_arg: str, ffprobe_arg: str) -> Dict[str, Any]:
    job_dir = _required_file(job_dir / "vertical_ad_report.json", "vertical_ad_report.json").parent
    inputs = _verified_job_inputs(job_dir, motion_base)
    ffmpeg, ffprobe = echo.resolve_tools(ffmpeg_arg, ffprobe_arg)
    intermediate = job_dir / "intermediate"
    logs = job_dir / "logs"
    corrected = intermediate / "pause_quietbank_reprocessed_video_1.mp4"
    final_video = job_dir / "vertical_ad_1080x1920_pause_quietbank_reprocessed.mp4"
    report_path = job_dir / "pause_reprocess_report.json"
    if corrected.exists() or final_video.exists() or report_path.exists():
        raise FileExistsError("Output reprocess đã tồn tại; không ghi đè: {}".format(job_dir))
    unshifted_video = inputs["rendered_video"]
    reencoded_audio_restore: Optional[Dict[str, Any]] = None
    if inputs["restore_audio"]:
        unshifted_video = intermediate / "reprocess_unshifted_video_1.mp4"
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
        raise ValueError("Video tham chiếu cho quiet bank không có video stream.")
    if inputs["reference_policy"] != "original_motion_base":
        expected_dimensions = (int(inputs["motion_metadata"].get("width", 0)),
                               int(inputs["motion_metadata"].get("height", 0)))
        reference_dimensions = (int(reference_stream.get("width", 0)), int(reference_stream.get("height", 0)))
        rendered_dimensions = (int(actual_video.get("width", 0)), int(actual_video.get("height", 0)))
        expected_fps = float(inputs["motion_metadata"].get("fps") or 0.0)
        reference_fps = echo.parse_fraction(str(reference_stream.get("avg_frame_rate") or "0/1"))
        rendered_fps = echo.parse_fraction(str(actual_video.get("avg_frame_rate") or "0/1"))
        if (reference_dimensions != expected_dimensions or rendered_dimensions != expected_dimensions
                or abs(reference_fps - expected_fps) > 0.01 or abs(rendered_fps - expected_fps) > 0.01):
            raise ValueError("Fallback donor, original motion metadata và MuseTalk intermediate phải cùng kích thước/FPS.")
        donor_indices = ads.quiet_bank_frame_indices(
            inputs["quiet_bank_intervals"], ads.count_video_frames(inputs["reference_video"], ffprobe), ads.FPS,
        )
        if not donor_indices:
            raise ValueError("Fallback bị từ chối: overlap đã trim không bao phủ frame donor hoàn chỉnh nào.")

    started = time.perf_counter()
    correction = ads.apply_pause_mouth_closure(
        unshifted_video, inputs["reference_video"], inputs["unshifted_audio"], corrected,
        ffmpeg, ffprobe, duration, ads.FPS,
        float((inputs["report"].get("pause_mouth_closure_policy") or {}).get("minimum_pause_seconds") or ads.PAUSE_MIN_DURATION_SECONDS),
        reference_audio=inputs["echo_reference_audio"],
        reference_audio_provenance=inputs["provenance"],
        requested_policy="auto",
        quiet_bank_intervals=inputs["quiet_bank_intervals"],
        reference_source=inputs["reference_policy"],
    )
    if correction["status"] != "applied":
        report = {
            "status": "skipped",
            "reason": correction["status"],
            "job_directory": str(job_dir),
            "motion_base": str(inputs["motion_base"] or inputs["report"].get("motion_base", {}).get("path")),
            "reference_policy": inputs["reference_policy"],
            "pause_correction": correction,
            "note": "Không tạo final đã sửa vì không có quiet bank đủ điều kiện; MuseTalk/Echo không được chạy lại.",
        }
        echo.write_json_atomic(report_path, report)
        raise RuntimeError("Quiet-bank correction bị bỏ qua: {}. Report: {}".format(correction["status"], report_path))

    export_seconds, exported = ads.export_hd_video(
        corrected, final_video, ffmpeg, ffprobe, duration,
        logs / "hd_export_pause_quietbank_reprocessed.log",
    )
    report = {
        "status": "complete",
        "job_directory": str(job_dir),
        "source_video": str(inputs["rendered_video"]),
        "input_audio_restoration": reencoded_audio_restore,
        "unshifted_audio": str(inputs["unshifted_audio"]),
        "unshifted_audio_sha256": musetalk.sha256_file(inputs["unshifted_audio"]),
        "echo_reference_audio": str(inputs["echo_reference_audio"]),
        "motion_base": str(inputs["motion_base"] or inputs["report"].get("motion_base", {}).get("path")),
        "motion_base_sha256": inputs["motion_metadata"]["sha256"],
        "quiet_bank_reference_video": str(inputs["reference_video"]),
        "reference_policy": inputs["reference_policy"],
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
        "models_rerun": False,
        "audio_policy": "use the job's unshifted audio; AAC stream is copied through correction and HD export",
        "scope_note": "Only detected pause frames use the verified quiet-frame bank. Speech frames and head motion during speech are retained; visual closure still requires human review.",
    }
    echo.write_json_atomic(report_path, report)
    return report


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Offline reprocess a completed Echo/MuseTalk job with its verified quiet-motion bank; no model inference runs.",
    )
    parser.add_argument("--job-dir", required=True, type=Path, help="Completed output\\vertical_ads\\job_... folder.")
    parser.add_argument("--motion-base", type=Path, help="Original Echo motion_base.mp4 whose SHA-256 is in the job report; preferred. If omitted, only a validated old pause_closed_video_1.mp4 may supply donor frames.")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--ffprobe", default="ffprobe")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = make_parser().parse_args(argv)
    try:
        report = reprocess(args.job_dir, args.motion_base, args.ffmpeg, args.ffprobe)
    except Exception as error:
        print("ERROR: {}".format(error), file=sys.stderr)
        return 1
    print("Reprocess thành công, không chạy lại Echo/MuseTalk (policy: {}).".format(report["reference_policy"]))
    print("Native: {}".format(report["corrected_intermediate"]))
    print("Final: {}".format(report["final_output"]))
    print("Report: {}".format(Path(report["job_directory"]) / "pause_reprocess_report.json"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
