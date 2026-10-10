from __future__ import annotations

import contextlib
import io
import json
import math
import shutil
import subprocess
import sys
import tempfile
import unittest
import wave
import struct
import zlib
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import test_vertical_ads as ads
import reprocess_pause_correction as reprocess_pause
import musetalk_mouth_masks as mouth_masks
from tests import test_cached_musetalk as cached_fixture

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")


class VerticalAdsTests(unittest.TestCase):
    @staticmethod
    def _mouth_landmarks(aperture_pixels: float = 0.0):
        points = [[0.0, 0.0] for _ in range(68)]
        points[48] = (40, 50)
        points[54] = (80, 50)
        points[61], points[62], points[63] = (51, 48), (60, 48), (69, 48)
        points[67], points[66], points[65] = (
            (51, 48 + aperture_pixels), (60, 48 + aperture_pixels), (69, 48 + aperture_pixels),
        )
        return points

    @staticmethod
    def _static_landmark_detector(aperture_pixels: float = 0.5):
        landmarks = [list(point) for point in VerticalAdsTests._mouth_landmarks(aperture_pixels)]
        # A finite, non-degenerate jaw outline lets the detector wrapper rank this as one face.
        for index in range(17):
            landmarks[index] = (30 + index * 3.75, 40 + 20 * math.sin(index * math.pi / 16))

        class Detector:
            def get_landmarks(self, _rgb):
                return [landmarks]

        return Detector()

    def test_landmark_mouth_aperture_rejects_gap_accepts_closed_and_fails_invalid(self):
        closed, reason, width = mouth_masks.measure_mouth_aperture(
            self._mouth_landmarks(0.5), (120, 120),
        )
        self.assertEqual(reason, "measured")
        self.assertAlmostEqual(width, 40.0)
        self.assertLessEqual(closed, mouth_masks.MAX_MOUTH_APERTURE_RATIO)

        open_gap, reason, _ = mouth_masks.measure_mouth_aperture(
            self._mouth_landmarks(4.0), (120, 120),
        )
        self.assertEqual(reason, "measured")
        self.assertGreater(open_gap, mouth_masks.MAX_MOUTH_APERTURE_RATIO)

        invalid, reason, _ = mouth_masks.measure_mouth_aperture([[1.0, 2.0]], (120, 120))
        self.assertIsNone(invalid)
        self.assertEqual(reason, "invalid_landmark_shape")
        invalid, reason, _ = mouth_masks.measure_mouth_aperture(
            self._mouth_landmarks(float("nan")), (120, 120),
        )
        self.assertIsNone(invalid)
        self.assertEqual(reason, "non_finite_landmarks")
        for aperture_pixels in (0.0, -1.0):
            invalid, reason, _ = mouth_masks.measure_mouth_aperture(
                self._mouth_landmarks(aperture_pixels), (120, 120),
            )
            self.assertIsNone(invalid)
            self.assertEqual(reason, "non_positive_inner_lip_aperture")

        self.assertFalse(mouth_masks.is_closed_donor({"inner_mouth_fraction": 0.0}))
        self.assertTrue(mouth_masks.is_closed_donor({
            "inner_mouth_fraction": 0.0,
            "mouth_aperture_status": "measured",
            "mouth_aperture_ratio": closed,
        }))
        self.assertFalse(mouth_masks.is_closed_donor({
            "inner_mouth_fraction": 0.0,
            "mouth_aperture_status": "measured",
            "mouth_aperture_ratio": open_gap,
        }))

    @unittest.skipUnless(FFMPEG and mouth_masks.cv2 is not None and mouth_masks.np is not None,
                         "OpenCV and FFmpeg are required for final-frame mouth QC")
    def test_final_output_mouth_qc_fails_when_any_pause_frame_is_open_or_uncertain(self):
        with tempfile.TemporaryDirectory() as directory:
            video = Path(directory) / "final.mp4"
            frame = mouth_masks.np.full((120, 120, 3), 120, dtype=mouth_masks.np.uint8)
            writer = mouth_masks.cv2.VideoWriter(
                str(video), mouth_masks.cv2.VideoWriter_fourcc(*"mp4v"), 25.0, (120, 120),
            )
            self.assertTrue(writer.isOpened())
            for _ in range(3):
                writer.write(frame)
            writer.release()

            qc = mouth_masks.validate_output_pause_frames(
                video, [0, 1], self._static_landmark_detector(aperture_pixels=4.0),
            )
            self.assertEqual(qc["status"], "failed")
            self.assertEqual(qc["failed_frame_indices"], [0, 1])
            self.assertEqual(qc["passed_frame_count"], 0)
            unavailable = mouth_masks.validate_output_pause_frames(video, [0], None)
            self.assertEqual(unavailable["status"], "failed")
            self.assertEqual(unavailable["reason"], "landmark_detector_unavailable")

    def test_profiles_cli_and_phase_metrics(self):
        args = ads.make_parser().parse_args(["run"])
        self.assertEqual((args.profile, args.mouth_mode), ("A10", "speech"))
        self.assertEqual(args.pause_mouth_closure, "auto")
        self.assertEqual(args.pause_correction_region, "full-frame")
        self.assertEqual(reprocess_pause.make_parser().parse_args([
            "--job-dir", "job", "--motion-base", "base.mp4",
        ]).mouth_donor_mode, "quiet-source")
        self.assertIsNone(reprocess_pause.make_parser().parse_args([
            "--job-dir", "job", "--motion-base", "base.mp4",
        ]).output_label)
        self.assertIsNone(reprocess_pause.make_parser().parse_args([
            "--job-dir", "job", "--motion-base", "base.mp4",
        ]).reuse_silence_donor_label)
        self.assertEqual(args.audio_offset_ms, 0)
        help_text = " ".join(ads.make_parser().format_help().split())
        self.assertIn("speech dùng audio thật để sinh chuyển động", help_text)
        self.assertIn("không khuyến nghị làm motion base chuyển động", help_text)
        self.assertIn("đúng frame ping-pong nguồn", help_text)
        self.assertIn("off tắt cả hai", help_text)
        self.assertIn("Dương làm miệng trễ audio", help_text)
        self.assertIn("silence-conditioned", " ".join(reprocess_pause.make_parser().format_help().split()))
        self.assertIn("Echo is not rerun", " ".join(reprocess_pause.make_parser().format_help().split()))
        echo_help = " ".join(ads.echo.make_parser().format_help().split())
        self.assertIn("speech dùng audio thật để sinh chuyển động", echo_help)
        self.assertIn("đầu gần tĩnh", echo_help)
        self.assertIn("không phù hợp làm motion base có chuyển động", echo_help)
        for name, dimensions in [("A10", (512, 640)), ("A10HQ", (640, 800))]:
            p = ads.echo.PROFILES[name]
            self.assertEqual((p.width, p.height), dimensions)
            self.assertEqual(p.frames, 129)
        row = {"musetalk_wall_seconds": 2}
        ads._write_output_metrics(row, {"audio_duration_seconds": 55.584, "export_wall_seconds": 1})
        self.assertFalse(row["normalized_60s_is_measured"])
        self.assertAlmostEqual(row["normalized_wall_seconds_per_60_audio_seconds_extrapolation"], 3 * 60 / 55.584, places=3)
        self.assertEqual(ads.report_filename("calibrate"), "lip_calibration_report.json")

    def test_quality_assessment_separates_file_checks_from_unverified_quality_claims(self):
        export = {
            "ffprobe_checks": {
                "width": True, "height": True, "fps_25": True,
                "aac_packet_payload_hashes_match_source": True,
            },
        }
        pause = {
            "output_mouth_closure_qc": {
                "status": "passed",
                "method": "68-point inner-lip aperture",
            },
            "output_mouth_closure_qc_report": "job/quality_assessment/qc.json",
        }
        assessment = ads._build_quality_assessment(export, pause, "mouth-only")
        self.assertEqual(assessment["certification_status"], "not_certified")
        self.assertEqual(
            assessment["objective_checks"]["container_audio_frame_integrity"]["status"],
            "passed",
        )
        self.assertEqual(assessment["objective_checks"]["pause_mouth_geometry"]["status"], "passed")
        for claim in (
            "speech_lip_sync", "temporal_smoothness", "similarity_to_reference_video",
            "cross_character_generalization", "cross_language_generalization",
        ):
            self.assertTrue(assessment["unverified_claims"][claim].startswith("unverified:"))

    def test_mouth_qc_detector_preflight_runs_in_musetalk_python_and_fails_fast(self):
        default_args = ads.make_parser().parse_args(["run"])
        mouth_only_args = ads.make_parser().parse_args(["run", "--pause-correction-region", "mouth-only"])
        disabled_args = ads.make_parser().parse_args([
            "run", "--pause-correction-region", "mouth-only", "--pause-mouth-closure", "off",
        ])
        dry_run_args = ads.make_parser().parse_args([
            "dry-run", "--pause-correction-region", "mouth-only",
        ])
        self.assertFalse(ads._mouth_qc_detector_preflight_required(default_args))
        self.assertTrue(ads._mouth_qc_detector_preflight_required(mouth_only_args))
        self.assertFalse(ads._mouth_qc_detector_preflight_required(disabled_args))
        self.assertFalse(ads._mouth_qc_detector_preflight_required(dry_run_args))

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = type("Paths", (), {"root": root / "musetalk", "python": Path(sys.executable)})()
            calls = []

            def backend(command, cwd, environment, log_path):
                calls.append((command, cwd, log_path))
                return 0, 0.25

            with (
                mock.patch.object(ads.musetalk, "build_backend_environment", return_value={}),
                mock.patch.object(ads.musetalk, "run_backend_process", side_effect=backend),
            ):
                result = ads._preflight_mouth_qc_detector(paths, "ffmpeg", root / "job")
            self.assertEqual(result["status"], "ready")
            self.assertIn("--check-landmark-detector", calls[0][0])
            self.assertEqual(calls[0][1], paths.root)
            self.assertIn("mouth_qc_detector_preflight.log", calls[0][2].name)

            with (
                mock.patch.object(ads.musetalk, "build_backend_environment", return_value={}),
                mock.patch.object(ads.musetalk, "run_backend_process", return_value=(2, 0.1)),
                self.assertRaisesRegex(RuntimeError, "stopping before Echo/MuseTalk inference"),
            ):
                ads._preflight_mouth_qc_detector(paths, "ffmpeg", root / "failed_job")

    def test_reprocess_output_label_namespaces_all_outputs_and_rejects_paths(self):
        job = Path("job")
        legacy = reprocess_pause._reprocess_output_paths(job, "mouth-only", None)
        labeled = reprocess_pause._reprocess_output_paths(job, "mouth-only", "retry_2")
        self.assertEqual(legacy["corrected"], job / "intermediate" / "pause_mouth_only_reprocessed_video_1.mp4")
        self.assertEqual(legacy["report"], job / "pause_mouth_only_reprocess_report.json")
        self.assertEqual(labeled["corrected"], job / "intermediate" / "pause_mouth_only_retry_2_reprocessed_video_1.mp4")
        self.assertEqual(labeled["report"], job / "pause_mouth_only_retry_2_reprocess_report.json")
        self.assertTrue(all(legacy[key] != labeled[key] for key in legacy))
        self.assertEqual(
            labeled["silence_donor_video"],
            job / "intermediate" / "pause_silence_conditioned_musetalk_donor_retry_2.mp4",
        )
        for invalid in ("../retry", "with space", "-starts-with-dash", "x" * 49):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    reprocess_pause._validated_output_label(invalid)
        self.assertEqual(reprocess_pause._validated_output_label("retry-3"), "retry-3")
        with tempfile.TemporaryDirectory() as directory:
            collision = Path(directory) / "prior.log"
            collision.write_text("prior attempt", encoding="utf-8")
            with self.assertRaisesRegex(FileExistsError, "không ghi đè"):
                reprocess_pause._ensure_outputs_unused([Path(directory) / "new.mp4", collision])

    @unittest.skipUnless(FFMPEG and FFPROBE, "FFmpeg/ffprobe are required for donor timeline tests")
    def test_donor_frame0_prefix_accepts_only_exact_or_one_missing_trailing_frame(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            exact = root / "exact.mp4"
            one_short = root / "one_short.mp4"
            two_short = root / "two_short.mp4"
            gap = root / "gap.mp4"
            source = root / "source.mp4"
            self._ffmpeg([
                "-f", "lavfi", "-i", "color=red:s=64x80:r=25:d=0.16", "-frames:v", "4", "-an",
                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(source),
            ])
            self._ffmpeg(["-i", str(source), "-frames:v", "4", "-an", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(exact)])
            self._ffmpeg(["-i", str(source), "-frames:v", "3", "-an", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(one_short)])
            self._ffmpeg(["-i", str(source), "-frames:v", "2", "-an", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(two_short)])
            self._ffmpeg([
                "-i", str(source), "-vf", "select='not(eq(n,1))'", "-fps_mode", "vfr", "-an",
                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(gap),
            ])

            exact_timeline = ads.validate_donor_frame0_prefix(exact, 4, (64, 80), 25, FFPROBE)
            self.assertEqual(exact_timeline["status"], "verified_exact_frame_count")
            short_timeline = ads.validate_donor_frame0_prefix(one_short, 4, (64, 80), 25, FFPROBE)
            self.assertEqual(short_timeline["status"], "verified_trailing_frame_truncation")
            self.assertEqual(short_timeline["missing_trailing_source_frame_index"], 3)
            for invalid in (two_short, gap):
                with self.subTest(invalid=invalid.name):
                    with self.assertRaises(ValueError):
                        ads.validate_donor_frame0_prefix(invalid, 4, (64, 80), 25, FFPROBE)

    def test_auto_pause_closure_requires_speech_mode_and_matching_source_audio(self):
        digest = "a" * 64
        self.assertEqual(ads._pause_closure_decision("auto", "speech", digest, digest),
                         (True, "echo_manifest_confirms_speech_mode_and_matching_audio_sha256"))
        self.assertEqual(ads._pause_closure_decision("auto", "speech", digest, "b" * 64),
                         (False, "skipped_because_current_audio_does_not_match_echo_conditioning_audio_sha256"))
        self.assertEqual(ads._pause_closure_decision("auto", "speech", None, digest),
                         (False, "skipped_because_echo_audio_identity_is_unverified"))
        self.assertEqual(ads._pause_closure_decision("auto", "neutral", digest, digest),
                         (False, "skipped_because_echo_manifest_marks_neutral_motion_base"))
        self.assertEqual(ads._pause_closure_decision("auto", None, digest, digest),
                         (False, "skipped_because_motion_base_mode_is_unverified"))
        self.assertTrue(ads._pause_closure_decision("force", "neutral", digest, "b" * 64)[0])
        self.assertFalse(ads._pause_closure_decision("off", "neutral", digest, digest)[0])

    def test_audio_offset_is_frame_granular_bounded_and_signed(self):
        for value in (-160, -40, 0, 40, 160):
            self.assertEqual(ads.validate_audio_offset_ms(value), value)
        for value in (-200, -20, 20, 200):
            with self.assertRaises(ValueError):
                ads.validate_audio_offset_ms(value)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, delayed, advanced = root / "source.wav", root / "delayed.wav", root / "advanced.wav"
            samples = list(range(1, 1601))
            with wave.open(str(source), "wb") as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(16000)
                data = ads.array("h", samples).tobytes()
                output.writeframes(data)
            delayed_info = ads.shift_pcm_wav(source, delayed, 40)
            advanced_info = ads.shift_pcm_wav(source, advanced, -40)
            with wave.open(str(delayed), "rb") as shifted:
                delayed_samples = ads.array("h", shifted.readframes(shifted.getnframes()))
            with wave.open(str(advanced), "rb") as shifted:
                advanced_samples = ads.array("h", shifted.readframes(shifted.getnframes()))
            self.assertEqual(len(delayed_samples), len(samples))
            self.assertEqual(len(advanced_samples), len(samples))
            self.assertEqual(list(delayed_samples[:640]), [0] * 640)
            self.assertEqual(list(delayed_samples[640:]), samples[:-640])
            self.assertEqual(list(advanced_samples[:-640]), samples[640:])
            self.assertEqual(list(advanced_samples[-640:]), [0] * 640)
            self.assertEqual(delayed_info["sample_offset"], 640)
            self.assertEqual(advanced_info["offset_ms"], -40)

    def test_pause_gate_mutes_only_confident_intervals_and_preserves_speech_and_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, gated = root / "source.wav", root / "gated.wav"
            source_samples, segments = self._write_synthetic_gate_audio(source)
            original_sha = ads.musetalk.sha256_file(source)
            record = ads.gate_pause_audio(source, gated)
            _, gated_samples = ads._read_normalized_pcm(gated)

            self.assertEqual(record["status"], "applied")
            self.assertEqual(record["interval_count"], 1)
            interval = record["intervals"][0]
            self.assertAlmostEqual(interval["start_seconds"], 3.0, delta=0.02)
            self.assertAlmostEqual(interval["end_seconds"], 3.4, delta=0.02)
            self.assertEqual(record["gated_sample_count"], 6400)
            self.assertEqual(record["sample_count"], len(source_samples))
            self.assertEqual(len(gated_samples), len(source_samples))
            self.assertGreater(record["changed_nonzero_sample_count"], 0)
            self.assertEqual(record["sha256"], ads.musetalk.sha256_file(gated))
            self.assertEqual(record["source_sha256"], original_sha)
            self.assertEqual(ads.musetalk.sha256_file(source), original_sha)
            self.assertEqual(gated_samples[:interval["start_sample"]], source_samples[:interval["start_sample"]])
            self.assertFalse(any(gated_samples[interval["start_sample"]:interval["end_sample"]]))
            self.assertEqual(gated_samples[interval["end_sample"]:], source_samples[interval["end_sample"]:])
            quiet_speech_start = int(segments["quiet_speech_start"] * 16000)
            quiet_speech_end = int(segments["quiet_speech_end"] * 16000)
            self.assertEqual(gated_samples[quiet_speech_start:quiet_speech_end],
                             source_samples[quiet_speech_start:quiet_speech_end],
                             "globally quiet speech must remain byte-identical")

            forced = root / "forced.wav"
            force_record = ads.gate_pause_audio(source, forced, ads.PAUSE_FORCE_MIN_DURATION_SECONDS)
            self.assertEqual(force_record["interval_count"], 2)
            self.assertAlmostEqual(force_record["intervals"][1]["duration_seconds"], 0.24, delta=0.02)

    def test_pause_gate_precedes_signed_audio_offset_and_preserves_duration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, gated = root / "source.wav", root / "gated.wav"
            source_samples, _ = self._write_synthetic_gate_audio(source)
            gate_record = ads.gate_pause_audio(source, gated)
            _, gated_samples = ads._read_normalized_pcm(gated)
            interval = gate_record["intervals"][0]
            for offset in (-40, 40):
                shifted_path = root / "offset_{:+d}.wav".format(offset)
                offset_record = ads.shift_pcm_wav(gated, shifted_path, offset)
                _, shifted_samples = ads._read_normalized_pcm(shifted_path)
                moved = ads._offset_pause_intervals([interval], len(gated_samples), offset)
                shift_samples = 640
                self.assertEqual(len(shifted_samples), len(source_samples))
                self.assertEqual(offset_record["duration_seconds"], len(source_samples) / 16000)
                self.assertEqual(len(moved), 1)
                self.assertEqual(moved[0]["start_sample"], interval["start_sample"] + (shift_samples if offset > 0 else -shift_samples))
                self.assertEqual(moved[0]["end_sample"], interval["end_sample"] + (shift_samples if offset > 0 else -shift_samples))
                self.assertFalse(any(shifted_samples[moved[0]["start_sample"]:moved[0]["end_sample"]]))

                expected = ads.array("h")
                if offset > 0:
                    expected.extend([0] * shift_samples)
                    expected.extend(gated_samples[:-shift_samples])
                else:
                    expected.extend(gated_samples[shift_samples:])
                    expected.extend([0] * shift_samples)
                self.assertEqual(shifted_samples, expected, "offset variants must be derived from the gated WAV")

    def test_audio_offset_sweep_requires_short_preview_and_reused_base(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            ads.main(["run", "--audio-offset-sweep"])

    def test_echo_prompts_request_centered_calm_head_and_neutral_closed_lips(self):
        neutral = ads.echo.NEUTRAL_PROMPT.lower()
        self.assertIn("upright, centered and facing the camera", neutral)
        self.assertIn("lips stay naturally closed and relaxed", neutral)
        self.assertIn("no repeated left-right head turns", neutral)
        self.assertIn("side-to-side sway or rocking", neutral)
        self.assertNotIn("slight head turns", neutral)
        self.assertIn("repeated left-right head turns", ads.echo.NEGATIVE_PROMPT.lower())
        self.assertIn("no repeated left-right turns", ads.echo.DEFAULT_PROMPT.lower())

    def test_pingpong_mapping_matches_forward_then_full_reverse_sequence(self):
        expected = [0, 1, 2, 3, 3, 2, 1, 0, 0, 1, 2]
        actual = [ads.pingpong_frame_index(index, 4) for index in range(len(expected))]
        self.assertEqual(actual, expected)
        graph = ads.build_pause_closure_filter(4, 1.0, [{"start_seconds": 0.1, "end_seconds": 0.7}])
        self.assertIn("loop=loop=-1:size=8:start=0", graph)
        self.assertIn("concat=n=2:v=1:a=0", graph)
        self.assertIn("trim=end_frame=4", graph)
        self.assertIn("[source_aligned_reference]", graph)
        self.assertIn("[0:v]fps=25,setpts=N/(25*TB)[musetalk]", graph)

    def test_mouth_only_pause_frames_and_filter_are_bounded_by_decoded_video_frames(self):
        audio_duration = 55.584
        decoded_video_frames = 1388
        pause = [{"start_seconds": 55.48, "end_seconds": audio_duration,
                  "duration_seconds": audio_duration - 55.48}]

        audio_timeline_frames = ads.pause_frame_indices(pause, audio_duration, 25)
        video_timeline_frames = ads.pause_frame_indices(
            pause, audio_duration, 25, frame_count=decoded_video_frames,
        )
        self.assertEqual(audio_timeline_frames, [1387, 1388, 1389])
        self.assertEqual(video_timeline_frames, [1387])
        audio_aligned = ads.source_aligned_pause_intervals(
            pause, [{"start_seconds": 55.48, "end_seconds": 55.60}], audio_duration,
            source_frame_count=2000, fps=25,
        )
        video_aligned = ads.source_aligned_pause_intervals(
            pause, [{"start_seconds": 55.48, "end_seconds": 55.60}], audio_duration,
            source_frame_count=2000, fps=25, output_frame_count=decoded_video_frames,
        )
        self.assertEqual(audio_aligned, [{"start_seconds": 55.48, "end_seconds": 55.584,
                                          "duration_seconds": 0.104}])
        self.assertEqual(video_aligned, [{"start_seconds": 55.48, "end_seconds": 55.52,
                                          "duration_seconds": 0.04}])

        graph = ads.build_mouth_only_pause_closure_filter(
            audio_duration, 25, frame_count=decoded_video_frames,
        )
        self.assertEqual(graph.count("trim=end_frame=1388"), 3)
        self.assertNotIn("trim=end_frame=1390", graph)
        covered = ads.frame_indices_to_intervals(
            [1387], audio_duration, 25, frame_count=decoded_video_frames,
        )
        self.assertEqual(covered, [{"start_seconds": 55.48, "end_seconds": 55.52,
                                    "duration_seconds": 0.04}])
        classified = ads.classify_uncovered_by_video_duration([{
            "start_seconds": 55.48, "end_seconds": audio_duration,
            "duration_seconds": audio_duration - 55.48, "reason": "mouth_mask_or_face_alignment_was_not_confident",
        }], decoded_video_frames / 25.0)
        self.assertEqual(classified, [
            {"start_seconds": 55.48, "end_seconds": 55.52, "duration_seconds": 0.04,
             "reason": "mouth_mask_or_face_alignment_was_not_confident"},
            {"start_seconds": 55.52, "end_seconds": 55.584, "duration_seconds": 0.064,
             "reason": "audio_pause_after_end_of_rendered_video"},
        ])

    def test_job_pause_frame_set_matches_decoded_video_timeline(self):
        audio_duration = 55.584
        decoded_video_frames = 1388
        requested_intervals = [
            (1.94, 2.86), (7.02, 7.90), (13.20, 14.08), (20.90, 21.80),
            (30.88, 31.74), (39.64, 40.56), (47.88, 48.72), (50.74, 51.62),
            (54.84, 55.584),
        ]
        intervals = [
            {"start_seconds": start, "end_seconds": end, "duration_seconds": end - start}
            for start, end in requested_intervals
        ]

        pause_frames = ads.pause_frame_indices(
            intervals, audio_duration, 25, frame_count=decoded_video_frames,
        )

        self.assertEqual(len(pause_frames), 190)
        self.assertIn(782, pause_frames)  # 31.28 seconds, within the 30.88–31.74 pause.
        self.assertEqual(pause_frames[-1], 1387)
        self.assertNotIn(1388, pause_frames)
        self.assertNotIn(1389, pause_frames)

        covered_intervals = ads.frame_indices_to_intervals(
            pause_frames, audio_duration, 25, frame_count=decoded_video_frames,
        )
        coverage = ads.summarize_pause_coverage(
            intervals, covered_intervals, decoded_video_frames / 25.0,
            pause_frames, pause_frames,
        )
        self.assertEqual(coverage["pause_coverage_status"], "full")
        self.assertEqual(coverage["uncorrected_output_pause_frame_indices"], [])
        self.assertAlmostEqual(coverage["audio_tail_duration_seconds"], 0.064, places=6)
        self.assertEqual(coverage["audio_tail_pause_intervals"], [{
            "start_seconds": 55.52, "end_seconds": 55.584, "duration_seconds": 0.064,
            "reason": "audio_pause_after_end_of_rendered_video",
        }])
        self.assertAlmostEqual(coverage["uncovered_duration_seconds"], 0.16, places=6)
        self.assertAlmostEqual(
            coverage["uncovered_duration_seconds"],
            sum(item["duration_seconds"] for item in coverage["video_uncovered_intervals"]), places=6,
        )
        self.assertTrue(all(
            item["reason"] != "audio_pause_after_end_of_rendered_video"
            for item in coverage["video_uncovered_intervals"]
        ))

    def test_mouth_only_parser_mask_and_donor_checks_are_conservative(self):
        if mouth_masks.cv2 is None or mouth_masks.np is None:
            self.skipTest("OpenCV/NumPy from the MuseTalk runtime are required for parser-mask checks")
        cv2, np = mouth_masks.cv2, mouth_masks.np
        labels = np.zeros((200, 200), dtype=np.uint8)
        cv2.ellipse(labels, (100, 90), (45, 60), 0, 0, 360, 1, -1)
        labels[121:125, 87:98] = 12
        labels[121:125, 98:113] = 13
        labels[122:124, 98:102] = 11
        alpha, descriptor, reason = mouth_masks.build_feathered_mouth_mask(labels)
        self.assertEqual(reason, "ok")
        self.assertIsNotNone(descriptor)
        self.assertFalse(mouth_masks.is_closed_donor(descriptor), "parser labels alone must not certify a visually closed donor")
        measured_closed = dict(descriptor, mouth_aperture_status="measured", mouth_aperture_ratio=0.01)
        self.assertTrue(mouth_masks.is_closed_donor(measured_closed))
        self.assertEqual(alpha.shape, labels.shape)
        self.assertGreater(np.count_nonzero(alpha), 0)
        self.assertLess(np.count_nonzero(alpha), labels.size * 0.02)

        open_labels = labels.copy()
        open_labels[120:130, 87:113] = 11
        _, open_descriptor, reason = mouth_masks.build_feathered_mouth_mask(open_labels)
        self.assertEqual(reason, "ok")
        self.assertIsNotNone(open_descriptor)
        self.assertFalse(mouth_masks.is_closed_donor(open_descriptor))
        invalid, invalid_descriptor, reason = mouth_masks.build_feathered_mouth_mask(np.zeros((200, 200), dtype=np.uint8))
        self.assertIsNone(invalid)
        self.assertIsNone(invalid_descriptor)
        self.assertEqual(reason, "face_skin_not_detected")

    def test_truncated_donor_skips_only_missing_terminal_index_without_fallback(self):
        reason = mouth_masks._exact_source_donor_missing_reason(128, 129, 128, True)
        self.assertEqual(reason, "exact_mapped_donor_frame_missing_trailing_truncation")
        self.assertIsNone(mouth_masks._exact_source_donor_missing_reason(127, 129, 128, True))
        self.assertIsNone(mouth_masks._exact_source_donor_missing_reason(128, 129, 128, False))
        unrelated_donor = (object(), {}, {})
        self.assertIsNone(mouth_masks._exact_mapped_donor(
            {"exact_source_frame_index": 128, "donor_frame_index": 128}, {127: unrelated_donor},
        ), "a nearby available donor must never substitute for missing source frame 128")

    def test_mouth_only_geometry_rejects_pose_proxy_mismatch(self):
        if mouth_masks.cv2 is None or mouth_masks.np is None:
            self.skipTest("OpenCV/NumPy from the MuseTalk runtime are required for parser geometry checks")
        cv2, np = mouth_masks.cv2, mouth_masks.np
        labels = np.zeros((200, 200), dtype=np.uint8)
        cv2.ellipse(labels, (100, 90), (45, 60), 0, 0, 360, 1, -1)
        labels[121:125, 87:113] = 12
        target, reason = mouth_masks.describe_face_and_mouth(labels)
        self.assertEqual(reason, "ok")
        shifted = np.zeros_like(labels)
        cv2.ellipse(shifted, (145, 90), (45, 60), 0, 0, 360, 1, -1)
        shifted[121:125, 132:158] = 12
        donor, reason = mouth_masks.describe_face_and_mouth(shifted)
        self.assertEqual(reason, "ok")
        allowed, _, reason = mouth_masks.compare_face_geometry(target, donor, 200, 200)
        self.assertFalse(allowed)
        self.assertEqual(reason, "face_center_mismatch")

        slight_shift = np.zeros_like(labels)
        cv2.ellipse(slight_shift, (106, 90), (45, 60), 0, 0, 360, 1, -1)
        slight_shift[121:125, 93:119] = 12
        donor, reason = mouth_masks.describe_face_and_mouth(slight_shift)
        self.assertEqual(reason, "ok")
        allowed, _, reason = mouth_masks.compare_face_geometry(target, donor, 200, 200)
        self.assertFalse(allowed, "a 3% face-center shift should be rejected before patching the mouth")
        self.assertEqual(reason, "face_center_mismatch")

    def test_mouth_only_transform_anchors_translation_on_lips(self):
        if mouth_masks.cv2 is None or mouth_masks.np is None:
            self.skipTest("OpenCV/NumPy from the MuseTalk runtime are required for mouth alignment checks")
        np = mouth_masks.np
        donor = np.zeros((100, 100), dtype=np.uint8)
        donor[49, 49] = 255
        warped = mouth_masks._warp_donor_to_target(
            donor, [20, 10, 80, 90], [20, 10, 80, 90],
            [45, 47, 55, 53], [48, 47, 58, 53],
            interpolation=mouth_masks.cv2.INTER_NEAREST,
        )
        self.assertEqual(int(warped[49, 52]), 255)
        self.assertEqual(int(np.count_nonzero(warped)), 1)

    def test_mouth_only_color_match_reduces_lip_seam_without_touching_inner_mouth(self):
        if mouth_masks.cv2 is None or mouth_masks.np is None:
            self.skipTest("OpenCV/NumPy from the MuseTalk runtime are required for lip-color checks")
        cv2, np = mouth_masks.cv2, mouth_masks.np
        target = np.full((40, 64, 3), (100, 120, 150), dtype=np.uint8)
        donor = np.full((40, 64, 3), (100, 120, 150), dtype=np.uint8)
        target_labels = np.ones((40, 64), dtype=np.uint8)
        donor_labels = np.ones((40, 64), dtype=np.uint8)
        alpha = np.zeros((40, 64), dtype=np.uint8)
        target_lips = np.zeros((40, 64), dtype=bool)
        donor_lips = np.zeros((40, 64), dtype=bool)
        inner_mouth = np.zeros((40, 64), dtype=bool)
        target_lips[18:21, 24:40] = True
        donor_lips[18:21, 24:40] = True
        inner_mouth[19, 29:35] = True
        target_labels[target_lips] = 12
        donor_labels[donor_lips] = 12
        target_labels[20, 24:40] = 13
        donor_labels[20, 24:40] = 13
        target_labels[inner_mouth] = 11
        donor_labels[inner_mouth] = 11
        feather = np.asarray([32, 64, 96, 128, 160, 192, 224, 255] * 2, dtype=np.uint8)
        alpha[18:21, 24:40] = feather
        target[target_lips] = (95, 110, 180)
        donor[donor_lips] = (105, 112, 168)
        target[inner_mouth] = (12, 10, 15)
        donor[inner_mouth] = (8, 7, 9)

        def median_lab(frame):
            lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
            return np.median(lab[target_lips & ~inner_mouth], axis=0)

        before_delta = np.abs(median_lab(target).astype(float) - median_lab(donor).astype(float))
        corrected, diagnostic = mouth_masks._match_donor_lip_color(
            donor, target, alpha, target_labels, donor_labels,
        )
        after_delta = np.abs(median_lab(target).astype(float) - median_lab(corrected).astype(float))

        self.assertEqual(diagnostic["status"], "applied")
        self.assertEqual(diagnostic["sample_pixel_count"], int(np.count_nonzero(target_lips & ~inner_mouth)))
        self.assertTrue(np.all(after_delta < before_delta))
        self.assertTrue(np.all(after_delta <= 2.0), "bounded Lab matching should remove synthetic lip color/brightness mismatch")
        self.assertTrue(np.array_equal(corrected[inner_mouth], donor[inner_mouth]),
                        "inner-mouth pixels must remain exactly from the closed donor")
        self.assertTrue(np.array_equal(corrected[~donor_lips], donor[~donor_lips]),
                        "color matching must not alter pixels outside semantic donor lips")

        alpha_weight = alpha.astype(np.float32)[..., None] / 255.0
        composite = np.rint(
            target.astype(np.float32) * (1.0 - alpha_weight)
            + corrected.astype(np.float32) * alpha_weight
        ).astype(np.uint8)
        self.assertTrue(np.array_equal(composite[alpha == 0], target[alpha == 0]),
                        "zero-alpha area around the lip seam must preserve the rendered face exactly")
        patch_delta = composite.astype(np.int16) - target.astype(np.int16)
        edge_steps = np.abs(np.diff(patch_delta[18, 23:41], axis=0))
        self.assertLessEqual(int(edge_steps[:-1].max()), 8,
                             "a feathered synthetic lip seam should not introduce a hard color edge")

    def test_mouth_only_extractor_prefers_best_aligned_closed_donor_and_reports_frame_diagnostics(self):
        if mouth_masks.cv2 is None or mouth_masks.np is None:
            self.skipTest("OpenCV/NumPy from the MuseTalk runtime are required for donor extraction checks")
        cv2, np = mouth_masks.cv2, mouth_masks.np
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference_video = root / "reference.avi"
            rendered_video = root / "rendered.avi"
            width = height = 200
            fourcc = cv2.VideoWriter_fourcc(*"MJPG")

            def write_video(path: Path, colors: tuple[tuple[int, int, int], ...]) -> None:
                writer = cv2.VideoWriter(str(path), fourcc, 25.0, (width, height))
                self.assertTrue(writer.isOpened(), "OpenCV must open the test AVI writer")
                try:
                    for color in colors:
                        writer.write(np.full((height, width, 3), color, dtype=np.uint8))
                finally:
                    writer.release()

            write_video(reference_video, ((20, 40, 220), (20, 40, 220), (20, 40, 220)))
            write_video(rendered_video, ((80, 100, 120), (80, 100, 120), (80, 100, 120)))

            tight_labels = np.zeros((height, width), dtype=np.uint8)
            cv2.ellipse(tight_labels, (100, 90), (45, 60), 0, 0, 360, 1, -1)
            tight_labels[121:125, 87:98] = 12
            tight_labels[121:125, 98:113] = 13
            aligned_labels = np.zeros_like(tight_labels)
            cv2.ellipse(aligned_labels, (101, 90), (45, 60), 0, 0, 360, 1, -1)
            aligned_labels[121:125, 88:99] = 12
            aligned_labels[121:125, 99:114] = 13
            aligned_labels[122:124, 99:103] = 11
            target_labels = aligned_labels.copy()
            target_labels[122:123, 99:103] = 11
            target_mask, target_geometry, _ = mouth_masks.build_feathered_mouth_mask(target_labels)
            self.assertIsNotNone(target_mask)
            tight_donor, _ = mouth_masks.describe_face_and_mouth(tight_labels)
            aligned_donor, _ = mouth_masks.describe_face_and_mouth(aligned_labels)
            self.assertIsNotNone(tight_donor)
            self.assertIsNotNone(aligned_donor)
            tight_allowed, tight_score, _ = mouth_masks.compare_face_geometry(target_geometry, tight_donor, width, height)
            aligned_allowed, aligned_score, _ = mouth_masks.compare_face_geometry(target_geometry, aligned_donor, width, height)
            self.assertTrue(tight_allowed)
            self.assertTrue(aligned_allowed)
            self.assertLess(tight_donor["inner_mouth_fraction"], aligned_donor["inner_mouth_fraction"])
            self.assertLessEqual(aligned_donor["inner_mouth_fraction"], mouth_masks.MAX_INNER_MOUTH_FRACTION)
            self.assertLess(aligned_score, tight_score)
            request_path = root / "request.json"
            request_path.write_text(json.dumps({
                "fps": 25,
                "width": width,
                "height": height,
                "output_frame_count": 3,
                "quiet_source_frame_indices": [0, 1],
                "output_pause_frames": [
                    {"output_frame_index": 1, "exact_source_frame_index": 1},
                    {"output_frame_index": 2, "exact_source_frame_index": 2},
                ],
            }), encoding="utf-8")
            mask_dir, donor_dir = root / "masks", root / "donors"
            report_path = root / "report.json"
            with mock.patch.object(
                mouth_masks, "_raw_label_map", side_effect=[tight_labels, aligned_labels, target_labels, np.zeros_like(tight_labels)],
            ):
                report = mouth_masks.run_extraction(
                    rendered_video, reference_video, mask_dir, donor_dir, report_path, request_path,
                    parser=object(), torch=object(), landmark_detector=self._static_landmark_detector(),
                )

            self.assertEqual(report["status"], "partially_applied")
            self.assertEqual(report["coverage_status"], "partial")
            self.assertEqual(report["corrected_output_frame_indices"], [1])
            self.assertEqual(report["uncorrected_output_pause_frame_indices"], [2])
            self.assertEqual(report["uncovered_output_pause_frame_count"], 1)
            self.assertEqual(report["selected_donor_by_output_frame"], {"1": 1})
            self.assertEqual(report["selected_donor_frame_counts"], {"1": 1})
            self.assertIn("patch preparation", report["diagnostic_scope"])
            prepared, skipped = report["frame_diagnostics"]
            self.assertEqual(prepared["output_frame_index"], 1)
            self.assertEqual(prepared["exact_source_frame_index"], 1)
            self.assertEqual(prepared["timestamp_seconds"], 0.04)
            self.assertEqual(prepared["frame_interval_seconds"], [0.04, 0.08])
            self.assertEqual(prepared["status"], "patch_prepared")
            self.assertTrue(prepared["patch_prepared"])
            self.assertIsNone(prepared["skip_reason"])
            self.assertIsNotNone(prepared["target_geometry"]["face_bbox"])
            self.assertIsNotNone(prepared["target_geometry"]["mouth_bbox"])
            self.assertGreater(prepared["mask_pixel_count"], 0)
            self.assertEqual(prepared["alpha_written_pixel_count"], prepared["mask_pixel_count"])
            self.assertEqual(prepared["selected_donor_frame_index"], 1,
                             "after both donors pass the closed-mouth gate, geometry fit outranks extra closure")
            donor_metric = prepared["selected_donor_closed_mouth_metric"]
            self.assertEqual(donor_metric["name"], "inner_mouth_fraction")
            self.assertEqual(donor_metric["maximum_closed_threshold"], mouth_masks.MAX_INNER_MOUTH_FRACTION)
            self.assertEqual(donor_metric["landmark_mouth_aperture"]["name"], "inner_lip_gap_over_mouth_width")
            self.assertTrue(donor_metric["passed"])
            self.assertLessEqual(donor_metric["value"], donor_metric["maximum_closed_threshold"])
            self.assertEqual(prepared["selected_donor_geometry_score"], round(aligned_score, 6))
            self.assertEqual(prepared["selected_donor_geometry_deltas"]["normalized_face_center_delta"], [0.0, 0.0])
            self.assertIsNotNone(prepared["selected_donor_geometry"]["mouth_bbox"])
            self.assertEqual(prepared["lip_color_adjustment"]["status"], "applied")
            self.assertEqual(set(prepared["lip_color_adjustment"]["sample_pixel_counts_by_label"]), {"12", "13"})
            self.assertEqual(set(prepared["lip_color_adjustment"]["class_adjustments"]), {"12", "13"})
            self.assertEqual(skipped["output_frame_index"], 2)
            self.assertEqual(skipped["exact_source_frame_index"], 2)
            self.assertEqual(skipped["timestamp_seconds"], 0.08)
            self.assertFalse(skipped["patch_prepared"])
            self.assertEqual(skipped["skip_reason"], "target_face_skin_not_detected")
            self.assertIsNone(skipped["target_geometry"])
            self.assertEqual(skipped["mask_pixel_count"], 0)
            self.assertEqual(np.count_nonzero(cv2.imread(str(mask_dir / "00000000.png"), cv2.IMREAD_GRAYSCALE)), 0)
            self.assertGreater(np.count_nonzero(cv2.imread(str(mask_dir / "00000001.png"), cv2.IMREAD_GRAYSCALE)), 0)
            self.assertEqual(np.count_nonzero(cv2.imread(str(mask_dir / "00000002.png"), cv2.IMREAD_GRAYSCALE)), 0)
            donor = cv2.imread(str(donor_dir / "00000001.png"), cv2.IMREAD_COLOR)
            self.assertIsNotNone(donor)
            self.assertLess(int(donor[40, 40, 0]), 50,
                            "the output-timed patch should be sourced from the selected quiet donor")

    @unittest.skipUnless(FFMPEG and FFPROBE, "FFmpeg/ffprobe are required for silence donor tests")
    def test_silence_wav_is_exact_motion_base_frame_duration_pcm16(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "silence.wav"
            record = reprocess_pause._write_exact_silence_wav(path, sample_count=1388 * 16000 // 25)
            with wave.open(str(path), "rb") as source:
                self.assertEqual((source.getnchannels(), source.getsampwidth(), source.getframerate()), (1, 2, 16000))
                self.assertEqual(source.getnframes(), 888320)
                self.assertFalse(any(source.readframes(source.getnframes())))
            self.assertEqual(record["sample_count"], 888320)
            self.assertAlmostEqual(record["duration_seconds"], 55.52, places=8)
            with self.assertRaises(FileExistsError):
                reprocess_pause._write_exact_silence_wav(path, 100)

    @unittest.skipUnless(FFMPEG and FFPROBE, "FFmpeg/ffprobe are required for silence donor tests")
    def test_silence_donor_renderer_reuses_report_cache_and_rejects_cache_miss(self):
        from types import SimpleNamespace

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = root / "motion_base.mp4"
            self._ffmpeg([
                "-f", "lavfi", "-i", "color=red:s=64x80:r=25:d=0.16", "-frames:v", "4", "-an",
                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(base),
            ])
            job = root / "job"
            (job / "intermediate").mkdir(parents=True)
            (job / "logs").mkdir()
            cache_path = root / "vcs_cache" / "cache-key"
            cache_path.mkdir(parents=True)
            (cache_path / "cache_manifest.json").write_text(json.dumps({
                "inputs": {
                    "base_video": {
                        "sha256": ads.musetalk.sha256_file(base), "width": 64,
                        "height": 80, "target_fps": 25,
                    },
                    "musetalk": {"parameters": {"bbox_shift": 0, "parsing_mode": "jaw",
                                                  "extra_margin": 10, "left_cheek_width": 90,
                                                  "right_cheek_width": 90}},
                },
            }), encoding="utf-8")
            paths = SimpleNamespace(root=root / "musetalk", python=root / "python.exe")
            job_lip_settings = {"bbox_shift": 0, "parsing_mode": "jaw",
                                "audio_padding_left": 2, "audio_padding_right": 2,
                                "extra_margin": 10}
            inputs = {
                "video_entry": {
                    "avatar_cache_path": str(cache_path),
                    "lip_sync_settings": job_lip_settings,
                },
                "motion_base": base,
                "motion_metadata": {"width": 64, "height": 80, "fps": 25.0,
                                    "sha256": ads.musetalk.sha256_file(base)},
            }
            actions = []

            def fake_pipeline(action, **kwargs):
                actions.append((action, kwargs))
                if action == "dry-run":
                    return {"cache_hit": True, "cache_path": cache_path}
                shutil.copyfile(base, kwargs["output"])
                kwargs["log_path"].write_text(
                    "Total process time of 4 frames including saving images = 0.1s\n",
                    encoding="utf-8",
                )
                return {"cache_hit": True, "cache_path": cache_path,
                        "audio_duration": 0.16, "backend_seconds": 2.0}

            def render_manifest_lookup(_cache, output_path):
                return {
                    "output": str(output_path.resolve()),
                    "audio_source": str((job / "intermediate" / "pause_silence_conditioning_16k_mono.wav").resolve()),
                    "cache_state": "REUSE", "motion_policy": "error",
                    "source_video_duration_seconds": 0.16,
                    "normalized_audio_duration_seconds": 0.16,
                    "normalized_audio": {"sample_rate": 16000, "channels": 1, "codec": "pcm_s16le"},
                    "lip_sync_settings": job_lip_settings,
                }

            with (
                mock.patch.object(reprocess_pause.musetalk, "discover_musetalk_paths", return_value=paths),
                mock.patch.object(reprocess_pause.musetalk, "validate_safe_cache_root"),
                mock.patch.object(reprocess_pause.musetalk, "find_ffmpeg_pair", return_value=(FFMPEG, FFPROBE)),
                mock.patch.object(reprocess_pause.musetalk, "run_pipeline", side_effect=fake_pipeline),
                mock.patch.object(reprocess_pause.ads, "find_musetalk_render_manifest", side_effect=render_manifest_lookup),
            ):
                record = reprocess_pause._render_silence_conditioned_donor(
                    job, inputs, FFMPEG, FFPROBE, str(paths.root), str(paths.python),
                )
            self.assertEqual([item[0] for item in actions], ["dry-run", "run"])
            self.assertTrue(all(Path(item[1]["cache_dir"]).resolve() == cache_path.parent.resolve() for item in actions), actions)
            self.assertTrue(all(item[1]["duration"] == 0.16 for item in actions))
            self.assertEqual(record["donor_video_frame_count"], 4)
            self.assertTrue(record["avatar_cache_hit"])
            self.assertEqual(record["avatar_cache_path"], str(cache_path.resolve()))
            self.assertEqual(record["silent_audio"]["sample_count"], 2560)

            failed_job = root / "failed_job"
            (failed_job / "intermediate").mkdir(parents=True)
            (failed_job / "logs").mkdir()
            calls = []
            with (
                mock.patch.object(reprocess_pause.musetalk, "discover_musetalk_paths", return_value=paths),
                mock.patch.object(reprocess_pause.musetalk, "validate_safe_cache_root"),
                mock.patch.object(reprocess_pause.musetalk, "find_ffmpeg_pair", return_value=(FFMPEG, FFPROBE)),
                mock.patch.object(reprocess_pause.musetalk, "run_pipeline", side_effect=lambda action, **kw: calls.append(action) or {"cache_hit": False, "cache_path": cache_path}),
            ):
                with self.assertRaisesRegex(RuntimeError, "Từ chối chạy silence donor"):
                    reprocess_pause._render_silence_conditioned_donor(
                        failed_job, inputs, FFMPEG, FFPROBE, str(paths.root), str(paths.python),
                    )
            self.assertEqual(calls, ["dry-run"], "cache miss must fail before any inference backend call")
            self.assertFalse((failed_job / "intermediate" / "pause_silence_conditioned_musetalk_donor.mp4").exists())

    @unittest.skipUnless(FFMPEG and FFPROBE, "FFmpeg/ffprobe are required for donor reuse")
    def test_existing_silence_donor_reuse_verifies_provenance_and_accepts_aligned_trailing_truncation(self):
        from types import SimpleNamespace

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            job = root / "job"
            (job / "intermediate").mkdir(parents=True)
            (job / "logs").mkdir()
            base = root / "motion_base.mp4"
            donor = root / "silence_donor.mp4"
            self._ffmpeg([
                "-f", "lavfi", "-i", "color=red:s=64x80:r=25:d=0.16", "-frames:v", "4", "-an",
                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(base),
            ])
            self._ffmpeg([
                "-f", "lavfi", "-i", "color=blue:s=64x80:r=25:d=0.12", "-frames:v", "3", "-an",
                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(donor),
            ])
            cache_path = root / "vcs_cache" / "cache-key"
            cache_path.mkdir(parents=True)
            base_sha = ads.musetalk.sha256_file(base)
            (cache_path / "cache_manifest.json").write_text(json.dumps({
                "inputs": {
                    "base_video": {"sha256": base_sha, "width": 64, "height": 80, "target_fps": 25},
                    "musetalk": {"parameters": {"bbox_shift": 0, "parsing_mode": "jaw",
                                                  "extra_margin": 10, "left_cheek_width": 90,
                                                  "right_cheek_width": 90}},
                },
            }), encoding="utf-8")
            settings = {"bbox_shift": 0, "parsing_mode": "jaw",
                        "audio_padding_left": 2, "audio_padding_right": 2,
                        "extra_margin": 10}
            inputs = {
                "video_entry": {"avatar_cache_path": str(cache_path), "lip_sync_settings": settings},
                "motion_base": base,
                "motion_metadata": {"sha256": base_sha, "width": 64, "height": 80, "fps": 25.0},
            }
            prior_paths = reprocess_pause._reprocess_output_paths(job, "mouth-only", "sameframe_v1")
            shutil.copyfile(donor, prior_paths["silence_donor_video"])
            reprocess_pause._write_exact_silence_wav(prior_paths["silence_audio"], 4 * 16000 // 25)
            prior_paths["silence_donor_log"].write_text(
                "Total process time of 4 frames including saving images = 11.1s\n",
                encoding="utf-8",
            )
            donor_sha_before = ads.musetalk.sha256_file(prior_paths["silence_donor_video"])
            silence_sha_before = ads.musetalk.sha256_file(prior_paths["silence_audio"])
            manifest = {
                "output": str(prior_paths["silence_donor_video"].resolve()),
                "audio_source": str(prior_paths["silence_audio"].resolve()),
                "cache_state": "REUSE", "motion_policy": "error",
                "source_video_duration_seconds": 0.16,
                "normalized_audio_duration_seconds": 0.16,
                "normalized_audio": {"sample_rate": 16000, "channels": 1, "codec": "pcm_s16le"},
                "lip_sync_settings": settings,
            }
            paths = SimpleNamespace(root=root / "musetalk", python=root / "python.exe")
            with (
                mock.patch.object(reprocess_pause.musetalk, "validate_safe_cache_root"),
                mock.patch.object(reprocess_pause.musetalk, "find_ffmpeg_pair", return_value=(FFMPEG, FFPROBE)),
                mock.patch.object(reprocess_pause.musetalk, "run_pipeline", side_effect=AssertionError("must reuse; do not render")) as runner,
                mock.patch.object(reprocess_pause.ads, "find_musetalk_render_manifest", return_value=manifest),
            ):
                record = reprocess_pause._render_silence_conditioned_donor(
                    job, inputs, FFMPEG, FFPROBE, str(paths.root), str(paths.python),
                    output_label="retry_2", reuse_silence_donor_label="sameframe_v1",
                )
            runner.assert_not_called()
            self.assertEqual(record["reuse_status"], "reused_existing_donor_assets")
            self.assertEqual(record["donor_video_frame_count"], 3)
            self.assertEqual(record["frame_timeline_validation"]["status"], "verified_trailing_frame_truncation")
            self.assertEqual(record["frame_timeline_validation"]["missing_trailing_source_frame_index"], 3)
            self.assertFalse(record["models_rerun"])
            self.assertEqual(ads.musetalk.sha256_file(prior_paths["silence_donor_video"]), donor_sha_before)
            self.assertEqual(ads.musetalk.sha256_file(prior_paths["silence_audio"]), silence_sha_before)

            wrong_manifest = dict(manifest, audio_source=str((job / "intermediate" / "wrong.wav").resolve()))
            with (
                mock.patch.object(reprocess_pause.musetalk, "validate_safe_cache_root"),
                mock.patch.object(reprocess_pause.musetalk, "find_ffmpeg_pair", return_value=(FFMPEG, FFPROBE)),
                mock.patch.object(reprocess_pause.ads, "find_musetalk_render_manifest", return_value=wrong_manifest),
            ):
                with self.assertRaisesRegex(ValueError, "does not point to the selected donor MP4 and silence WAV"):
                    reprocess_pause._render_silence_conditioned_donor(
                        job, inputs, FFMPEG, FFPROBE, str(paths.root), str(paths.python),
                        output_label="retry_3", reuse_silence_donor_label="sameframe_v1",
                    )

    @unittest.skipUnless(FFMPEG and FFPROBE, "FFmpeg/ffprobe are required for mapped-donor extraction")
    def test_silence_donor_mode_uses_only_exact_mapped_frame_and_reports_skip(self):
        if mouth_masks.cv2 is None or mouth_masks.np is None:
            self.skipTest("OpenCV/NumPy from the MuseTalk runtime are required for donor extraction checks")
        cv2, np = mouth_masks.cv2, mouth_masks.np
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            width = height = 200
            donor_video, rendered_video = root / "neutral.avi", root / "rendered.avi"
            writer = cv2.VideoWriter(str(donor_video), cv2.VideoWriter_fourcc(*"MJPG"), 25.0, (width, height))
            self.assertTrue(writer.isOpened())
            for color in ((20, 40, 220), (20, 40, 220), (20, 40, 220)):
                writer.write(np.full((height, width, 3), color, dtype=np.uint8))
            writer.release()
            writer = cv2.VideoWriter(str(rendered_video), cv2.VideoWriter_fourcc(*"MJPG"), 25.0, (width, height))
            self.assertTrue(writer.isOpened())
            for index in range(10):
                writer.write(np.full((height, width, 3), (80, 100, 120), dtype=np.uint8))
            writer.release()

            closed = np.zeros((height, width), dtype=np.uint8)
            cv2.ellipse(closed, (100, 90), (45, 60), 0, 0, 360, 1, -1)
            closed[121:125, 87:100] = 12
            closed[121:125, 100:113] = 13
            open_labels = closed.copy()
            open_labels[121:124, 92:104] = 11
            target = open_labels.copy()
            request = root / "request.json"
            request.write_text(json.dumps({
                "fps": 25, "width": width, "height": height,
                "output_frame_count": 10,
                "donor_mode": "silence-conditioned-exact-source",
                "donor_video_frame_count": 3,
                "donor_source_frame_count": 4,
                "donor_trailing_truncation_verified": True,
                "output_pause_frames": [
                    {"output_frame_index": 5, "exact_source_frame_index": 2, "donor_frame_index": 2},
                    {"output_frame_index": 9, "exact_source_frame_index": 3, "donor_frame_index": 3},
                ],
            }), encoding="utf-8")
            with mock.patch.object(
                mouth_masks, "_raw_label_map", side_effect=[closed, target, target],
            ) as parser:
                report = mouth_masks.run_extraction(
                    rendered_video, donor_video, root / "alpha", root / "donors",
                    root / "report.json", request, parser=object(), torch=object(),
                    landmark_detector=self._static_landmark_detector(),
                )
            self.assertEqual(parser.call_count, 3, "the helper should parse only available exact donors and targets, never scan/fallback to others")
            frames = {item["output_frame_index"]: item for item in report["frame_diagnostics"]}
            self.assertEqual(frames[5]["source_frame_index"], 2)
            self.assertEqual(frames[5]["donor_frame_index_requested"], 2)
            self.assertEqual(frames[5]["donor_frame_index"], 2)
            self.assertTrue(frames[5]["patch_prepared"])
            self.assertEqual(frames[9]["source_frame_index"], 3)
            self.assertEqual(frames[9]["donor_frame_index_requested"], 3)
            self.assertIsNone(frames[9]["donor_frame_index"])
            self.assertEqual(frames[9]["skip_reason"], "exact_mapped_donor_frame_missing_trailing_truncation")
            self.assertFalse(frames[9]["patch_prepared"], "missing terminal source frame must stay unchanged, without padding or fallback")
            self.assertEqual(report["donor_mode"], "silence-conditioned-exact-source")
            self.assertEqual(report["corrected_output_frame_indices"], [5])
            self.assertEqual(report["uncovered_output_pause_frame_count"], 1)
            self.assertIn("no fallback", report["donor_validation"])
            self.assertEqual(report["missing_trailing_donor_frame_index"], 3)

            invalid_request = root / "invalid_request.json"
            payload = json.loads(request.read_text(encoding="utf-8"))
            payload["donor_trailing_truncation_verified"] = False
            invalid_request.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "approved exact/prefix match"):
                mouth_masks.run_extraction(
                    rendered_video, donor_video, root / "invalid_alpha", root / "invalid_donors",
                    root / "invalid_report.json", invalid_request, parser=object(), torch=object(),
                )

    def test_mouth_only_filter_changes_only_masked_pixels_and_copies_audio(self):
        if not FFMPEG or not FFPROBE:
            self.skipTest("FFmpeg/ffprobe are required for the synthetic media test")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_raw = root / "source.rgb"
            source = root / "source.mp4"
            lossless_output = root / "output_lossless.mkv"
            lossy_output = root / "output_lossy.mp4"
            donor_dir, alpha_dir = root / "donors", root / "alpha"
            donor_dir.mkdir()
            alpha_dir.mkdir()
            source_frame = bytearray()
            for y in range(64):
                for x in range(64):
                    source_frame.extend((150 + x // 8, 120 + y // 8, 100 + (x + y) // 16))
            source_raw.write_bytes(bytes(source_frame) * 4)
            subprocess.run([
                FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo",
                "-pixel_format", "rgb24", "-video_size", "64x64", "-framerate", "25",
                "-i", str(source_raw), "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=16000:duration=0.20",
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "0", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "64k", str(source),
            ], check=True)
            for index in range(4):
                donor = donor_dir / ("{:08d}.ppm".format(index))
                donor.write_bytes(b"P6\n64 64\n255\n" + bytes((185, 150, 130)) * (64 * 64))
                alpha = bytearray(64 * 64)
                if index == 1:
                    for y in range(27, 37):
                        for x in range(27, 37):
                            alpha[y * 64 + x] = 255
                (alpha_dir / ("{:08d}.pgm".format(index))).write_bytes(b"P5\n64 64\n255\n" + alpha)
            graph = ads.build_mouth_only_pause_closure_filter(0.20, 25, frame_count=4)
            common_command = [
                FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
                "-framerate", "25", "-start_number", "0", "-i", str(donor_dir / "%08d.ppm"),
                "-framerate", "25", "-start_number", "0", "-i", str(alpha_dir / "%08d.pgm"),
                "-filter_complex", graph, "-map", "[closed]", "-map", "0:a:0", "-t", "0.20",
                "-c:a", "copy",
            ]
            result = subprocess.run(
                common_command + ["-c:v", "ffv1", "-pix_fmt", "rgb24", str(lossless_output)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(ads.count_video_frames(lossless_output, FFPROBE), 4,
                             "output video must stop at the four decoded source frames, not grow to match longer audio")
            source_info = ads.probe_media(source, FFPROBE)
            source_audio = ads.stream_by_type(source_info, "audio")
            lossless_info = ads.probe_media(lossless_output, FFPROBE)
            lossless_audio = ads.stream_by_type(lossless_info, "audio")
            self.assertIsNotNone(source_audio)
            self.assertIsNotNone(lossless_audio)

            def audio_packet_hashes(path: Path) -> list[str]:
                payload = json.loads(subprocess.check_output([
                    FFPROBE, "-v", "error", "-select_streams", "a:0", "-show_packets",
                    "-show_data_hash", "sha256", "-show_entries", "packet=data_hash", "-of", "json", str(path),
                ], text=True))
                return [packet["data_hash"] for packet in payload["packets"]]

            self.assertEqual(audio_packet_hashes(lossless_output), audio_packet_hashes(source),
                             "stream-copy must preserve every AAC packet, even when Matroska rounds its duration")
            self.assertLessEqual(abs(ads.media_duration(lossless_info, lossless_audio)
                                     - ads.media_duration(source_info, source_audio)), 0.07,
                                 "container duration may round to the next AAC packet boundary")

            result = subprocess.run(
                common_command + ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
                                  "-pix_fmt", "yuv420p", str(lossy_output)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

            def decode_rgb(path: Path) -> np.ndarray:
                raw = subprocess.check_output([FFMPEG, "-v", "error", "-i", str(path), "-map", "0:v:0",
                                               "-f", "rawvideo", "-pix_fmt", "rgb24", "-"])
                return raw

            source_frames = decode_rgb(source)
            lossless_frames = decode_rgb(lossless_output)
            lossy_frames = decode_rgb(lossy_output)
            frame_bytes = 64 * 64 * 3
            mask_indices = {y * 64 + x for y in range(27, 37) for x in range(27, 37)}
            changed_inside = False
            maximum_outside_error = 0
            for frame_index in range(4):
                frame_start = frame_index * frame_bytes
                for pixel in range(64 * 64):
                    start = frame_start + pixel * 3
                    source_pixel = source_frames[start:start + 3]
                    lossless_pixel = lossless_frames[start:start + 3]
                    output_pixel = lossy_frames[start:start + 3]
                    if frame_index == 1 and pixel in mask_indices:
                        if source_pixel != output_pixel:
                            changed_inside = True
                    else:
                        self.assertEqual(source_pixel, lossless_pixel,
                                         "lossless RGB output must preserve every unmasked pixel")
                    if pixel not in mask_indices:
                        maximum_outside_error = max(
                            maximum_outside_error,
                            *(abs(left - right) for left, right in zip(source_pixel, output_pixel)),
                        )
            self.assertTrue(changed_inside, "donor content should be visible inside the lip alpha only")
            self.assertLessEqual(maximum_outside_error, 12,
                                 "lossy 4:2:0 output may vary outside the mask, but only within codec tolerance")
            source_audio = subprocess.check_output([FFMPEG, "-v", "error", "-i", str(source), "-map", "0:a:0", "-f", "s16le", "-"])
            output_audio = subprocess.check_output([FFMPEG, "-v", "error", "-i", str(lossy_output), "-map", "0:a:0", "-f", "s16le", "-"])
            self.assertEqual(source_audio, output_audio)

            def audio_packet_hashes(path: Path) -> list[str]:
                data = subprocess.check_output([
                    FFPROBE, "-v", "error", "-select_streams", "a:0", "-show_packets",
                    "-show_data_hash", "sha256", "-show_entries", "packet=data_hash", "-of", "json", str(path),
                ])
                return [packet["data_hash"] for packet in json.loads(data)["packets"]]

            self.assertEqual(audio_packet_hashes(source), audio_packet_hashes(lossy_output))

    @unittest.skipUnless(FFMPEG and FFPROBE, "FFmpeg/ffprobe are required for end-to-end pause mux checks")
    def test_silence_conditioned_mouth_reprocess_and_hd_export_preserve_aac_tail_and_video_frames(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio_wav = root / "silence_200ms.wav"
            with wave.open(str(audio_wav), "wb") as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(16000)
                output.writeframes(b"\x00\x00" * 3200)
            base = root / "motion_base.mp4"
            self._ffmpeg([
                "-f", "lavfi", "-i", "color=red:s=64x80:r=25:d=0.16", "-frames:v", "4", "-an",
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "0", "-pix_fmt", "yuv420p", str(base),
            ])
            rendered = root / "musetalk_short_video_long_audio.mp4"
            self._ffmpeg([
                "-i", str(base), "-i", str(audio_wav), "-map", "0:v:0", "-map", "1:a:0",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "64k", "-movflags", "+faststart", str(rendered),
            ])
            donor_video = root / "silence_conditioned_donor.mp4"
            shutil.copyfile(base, donor_video)
            output_path = root / "mouth_corrected.mp4"
            helper_report = {
                "status": "partially_applied", "coverage_status": "partial",
                "corrected_output_frame_indices": [1], "corrected_output_frames": 1,
                "corrected_pause_frame_fraction": 0.25, "uncovered_output_pause_frame_count": 3,
                "uncorrected_output_pause_frame_indices": [0, 2, 3],
                "diagnostic_scope": "Per-frame records do not visually validate the output mouth.",
                "frame_diagnostics": [{"output_frame_index": 1, "source_frame_index": 1,
                                       "donor_frame_index": 1, "skip_reason": None}],
            }
            qc_status = ["passed"]

            def png_chunk(kind: bytes, data: bytes) -> bytes:
                return (struct.pack(">I", len(data)) + kind + data
                        + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))

            def write_rgb_png(path: Path, width: int, height: int, color: tuple[int, int, int]) -> None:
                row = b"\x00" + bytes(color) * width
                image_data = zlib.compress(row * height)
                header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
                path.write_bytes(b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", header)
                                 + png_chunk(b"IDAT", image_data) + png_chunk(b"IEND", b""))

            def write_gray_png(path: Path, width: int, height: int, selected: bool) -> None:
                rows = []
                for y in range(height):
                    row = bytearray(width)
                    if selected and 25 <= y < 40:
                        row[25:40] = b"\xff" * 15
                    rows.append(b"\x00" + bytes(row))
                image_data = zlib.compress(b"".join(rows))
                header = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
                path.write_bytes(b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", header)
                                 + png_chunk(b"IDAT", image_data) + png_chunk(b"IEND", b""))

            def fake_helper(command, cwd, environment, log_path):
                if "--validate-output-video" in command:
                    request_path = Path(command[command.index("--validate-request") + 1])
                    request = json.loads(request_path.read_text(encoding="utf-8"))
                    report_path = Path(command[command.index("--validation-report") + 1])
                    frame_count = len(request["output_pause_frames"])
                    report_path.write_text(json.dumps({
                        "status": qc_status[0],
                        "requested_frame_count": frame_count,
                        "passed_frame_count": frame_count if qc_status[0] == "passed" else 0,
                        "failed_frame_indices": [] if qc_status[0] == "passed" else [1],
                    }), encoding="utf-8")
                    return 0 if qc_status[0] == "passed" else 2, 0.01
                request_path = Path(command[command.index("--request") + 1])
                request = json.loads(request_path.read_text(encoding="utf-8"))
                donor_dir = Path(command[command.index("--donor-directory") + 1])
                mask_dir = Path(command[command.index("--mask-directory") + 1])
                report_path = Path(command[command.index("--report") + 1])
                donor_dir.mkdir(parents=True)
                mask_dir.mkdir(parents=True)
                for frame_index in range(request["output_frame_count"]):
                    write_rgb_png(donor_dir / "{:08d}.png".format(frame_index),
                                  request["width"], request["height"], (30, 180, 220))
                    write_gray_png(mask_dir / "{:08d}.png".format(frame_index),
                                   request["width"], request["height"], frame_index == 1)
                report_path.write_text(json.dumps(helper_report), encoding="utf-8")
                return 0, 0.01

            digest = ads.musetalk.sha256_file(audio_wav)
            fake_paths = mock.Mock(root=root / "musetalk", python=Path(sys.executable))
            with (
                mock.patch.object(ads.musetalk, "discover_musetalk_paths", return_value=fake_paths),
                mock.patch.object(ads.musetalk, "run_backend_process", side_effect=fake_helper),
            ):
                correction = ads.apply_pause_mouth_closure(
                    rendered, base, audio_wav, output_path, FFMPEG, FFPROBE, 0.20,
                    min_pause_seconds=0.08,
                    reference_audio=audio_wav,
                    reference_audio_provenance={
                        "status": "verified", "manifest_audio_sha256": digest,
                        "source_sha256": digest, "current_audio_sha256": digest,
                    },
                    requested_policy="auto", correction_region="mouth-only",
                    mouth_donor_mode="silence-conditioned",
                    silence_conditioned_donor_video=donor_video,
                )
            self.assertEqual(correction["status"], "partially_applied")
            self.assertEqual(correction["corrected_video_frame_count"], 4)
            self.assertTrue(correction["audio_packet_payload_hashes_match"])
            self.assertEqual(correction["source_audio_packet_count"], correction["corrected_audio_packet_count"])
            self.assertEqual(correction["mouth_donor_mode"], "silence-conditioned")
            self.assertEqual(correction["mouth_mask_extraction"]["frame_diagnostics"][0]["donor_frame_index"], 1)
            self.assertEqual(correction["output_mouth_closure_qc"]["status"], "passed")
            self.assertEqual(correction["measured_pause_mouth_closure"], "passed_geometric_aperture_gate")
            qc_report_path = Path(correction["output_mouth_closure_qc_report"])
            self.assertTrue(qc_report_path.is_file())
            self.assertEqual(json.loads(qc_report_path.read_text(encoding="utf-8"))["status"], "passed")
            self.assertIn("quality_assessment", qc_report_path.parts)
            self.assertEqual(ads.count_video_frames(output_path, FFPROBE), 4)
            source_info = ads.probe_media(rendered, FFPROBE)
            output_info = ads.probe_media(output_path, FFPROBE)
            source_audio = ads.stream_by_type(source_info, "audio")
            output_audio = ads.stream_by_type(output_info, "audio")
            self.assertGreater(ads.media_duration(source_info, source_audio), 0.16)
            self.assertEqual(ads.audio_packet_hashes(rendered, FFPROBE), ads.audio_packet_hashes(output_path, FFPROBE))

            qc_status[0] = "failed"
            rejected_output = root / "mouth_qc_rejected.mp4"
            with (
                mock.patch.object(ads.musetalk, "discover_musetalk_paths", return_value=fake_paths),
                mock.patch.object(ads.musetalk, "run_backend_process", side_effect=fake_helper),
            ):
                rejected = ads.apply_pause_mouth_closure(
                    rendered, base, audio_wav, rejected_output, FFMPEG, FFPROBE, 0.20,
                    min_pause_seconds=0.08,
                    reference_audio=audio_wav,
                    reference_audio_provenance={
                        "status": "verified", "manifest_audio_sha256": digest,
                        "source_sha256": digest, "current_audio_sha256": digest,
                    },
                    requested_policy="auto", correction_region="mouth-only",
                    mouth_donor_mode="silence-conditioned",
                    silence_conditioned_donor_video=donor_video,
                )
            self.assertEqual(rejected["status"], "failed_output_mouth_qc")
            self.assertFalse(rejected["output_promoted"])
            self.assertFalse(rejected_output.exists())
            self.assertFalse(rejected_output.with_name("." + rejected_output.stem + ".partial.mp4").exists())

            hd_path = root / "vertical_ad.mp4"
            _, hd_report = ads.export_hd_video(
                output_path, hd_path, FFMPEG, FFPROBE,
                ads.media_duration(output_info, output_audio), root / "hd-export.log",
            )
            self.assertEqual(hd_report["source_decoded_frame_count"], 4)
            self.assertEqual(hd_report["output_decoded_frame_count"], 4)
            self.assertTrue(hd_report["audio_packet_payload_hashes_match_source"])
            self.assertEqual(ads.audio_packet_hashes(output_path, FFPROBE), ads.audio_packet_hashes(hd_path, FFPROBE))
            self.assertEqual(ads.count_video_frames(hd_path, FFPROBE), 4)

            short_donor = root / "short_donor.mp4"
            self._ffmpeg([
                "-f", "lavfi", "-i", "color=blue:s=64x80:r=25:d=0.12", "-frames:v", "3", "-an",
                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(short_donor),
            ])
            unsafe_output = root / "must_not_exist.mp4"
            with mock.patch.object(ads.musetalk, "run_backend_process", side_effect=AssertionError("invalid donor must fail before helper inference")):
                with self.assertRaisesRegex(ValueError, "provenance-verified frame-0 timeline"):
                    ads.apply_pause_mouth_closure(
                        rendered, base, audio_wav, unsafe_output, FFMPEG, FFPROBE, 0.20,
                        min_pause_seconds=0.08,
                        reference_audio=audio_wav,
                        reference_audio_provenance={
                            "status": "verified", "manifest_audio_sha256": digest,
                            "source_sha256": digest, "current_audio_sha256": digest,
                        },
                        requested_policy="auto", correction_region="mouth-only",
                        mouth_donor_mode="silence-conditioned",
                        silence_conditioned_donor_video=short_donor,
                    )
            self.assertFalse(unsafe_output.exists())

    def test_pause_correction_only_matches_exact_pingpong_source_silence(self):
        source_pauses = [{"start_seconds": 0.4, "end_seconds": 0.8, "duration_seconds": 0.4}]
        requested = [
            {"start_seconds": 0.41, "end_seconds": 0.79},
            {"start_seconds": 2.4, "end_seconds": 2.8},
        ]
        aligned = ads.source_aligned_pause_intervals(requested, source_pauses, 3.2, source_frame_count=30)
        self.assertEqual(aligned, [{"start_seconds": 0.44, "end_seconds": 0.76, "duration_seconds": 0.32}])
        residual = ads.subtract_pause_intervals(requested, aligned, "no-exact-source-silence")
        self.assertAlmostEqual(sum(item["duration_seconds"] for item in residual), 0.46, places=6)
        self.assertEqual(ads.pingpong_frame_index(60, 30), 0)

    def test_silence_donor_lookup_never_falls_back_from_exact_source_index(self):
        unrelated = (object(), {"closed": True}, object())
        requested = {"exact_source_frame_index": 8, "donor_frame_index": 8}
        self.assertIsNone(mouth_masks._exact_mapped_donor(requested, {5: unrelated, 7: unrelated}))
        mapped = (object(), {"closed": True}, object())
        selected = mouth_masks._exact_mapped_donor(requested, {5: unrelated, 8: mapped})
        self.assertIsNotNone(selected)
        self.assertEqual(selected[0], 8)
        self.assertIs(selected[1], mapped[0])
        self.assertIsNone(mouth_masks._exact_mapped_donor(
            {"exact_source_frame_index": 8, "donor_frame_index": 5}, {5: unrelated, 8: mapped},
        ))

    def test_offline_reprocess_requires_report_audio_and_motion_base_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            job = Path(directory) / "job"
            intermediate = job / "intermediate"
            intermediate.mkdir(parents=True)
            base = Path(directory) / "motion_base.mp4"
            base.write_bytes(b"verified base")
            audio = intermediate / "audio_unshifted_16k_mono.wav"
            audio.write_bytes(b"verified output wav")
            echo_audio = intermediate / "echo_reference_audio_16k_mono.wav"
            echo_audio.write_bytes(b"verified Echo reference wav")
            unshifted_video = intermediate / "audio_unshifted_video_1.mp4"
            unshifted_video.write_bytes(b"audio-restored video")
            digest = "a" * 64
            report = {
                "pause_mouth_closure_policy": {
                    "source_mouth_mode": "speech", "manifest_audio_sha256": digest,
                    "current_input_audio_sha256": digest, "audio_identity_matches": True,
                    "reference_audio": {
                        "status": "verified", "manifest_audio_sha256": digest, "source_sha256": digest,
                    },
                },
                "motion_audio_alignment": {"status": "verified_match", "sha256_matches": True},
                "motion_base": {"sha256": ads.musetalk.sha256_file(base)},
                "audio_alignment": {"unshifted_normalized_audio_sha256": ads.musetalk.sha256_file(audio)},
                "videos": [{"pause_mouth_closure": {
                    "reference_audio_sha256": ads.musetalk.sha256_file(echo_audio),
                    "reference_audio_provenance": {
                        "status": "verified", "manifest_audio_sha256": digest,
                        "source_sha256": digest, "current_audio_sha256": digest,
                    },
                }}],
            }
            (job / "vertical_ad_report.json").write_text(json.dumps(report), encoding="utf-8")
            verified = reprocess_pause._verified_job_inputs(job, base)
            self.assertEqual(verified["rendered_video"], unshifted_video.resolve())
            self.assertFalse(verified["restore_audio"])
            audio.write_bytes(b"tampered output wav")
            with self.assertRaisesRegex(ValueError, "WAV unshifted"):
                reprocess_pause._verified_job_inputs(job, base)

    def test_reprocess_cli_reports_partial_pause_coverage_and_uncovered_frames(self):
        partial_result = {
            "reference_policy": "verified_quiet_source_mouth_donor_bank",
            "correction_region": "mouth-only",
            "job_directory": ".",
            "corrected_intermediate": "native.mp4",
            "final_output": "final.mp4",
            "pause_correction": {
                "status": "partially_applied",
                "pause_coverage_status": "partial",
                "corrected_pause_frame_count": 189,
                "requested_output_pause_frame_count": 190,
                "pause_frame_coverage_ratio": 189 / 190,
                "covered_duration_seconds": 7.56,
                "uncovered_duration_seconds": 0.04,
                "audio_tail_duration_seconds": 0.064,
                "video_uncovered_intervals": [{
                    "start_seconds": 31.28, "end_seconds": 31.32, "duration_seconds": 0.04,
                    "reason": "mouth_mask_or_face_alignment_was_not_confident",
                }],
                "audio_tail_pause_intervals": [{
                    "start_seconds": 55.52, "end_seconds": 55.584, "duration_seconds": 0.064,
                    "reason": "audio_pause_after_end_of_rendered_video",
                }],
                "uncovered_intervals": [{
                    "start_seconds": 31.28, "end_seconds": 31.32, "duration_seconds": 0.04,
                    "reason": "mouth_mask_or_face_alignment_was_not_confident",
                }, {
                    "start_seconds": 55.52, "end_seconds": 55.584, "duration_seconds": 0.064,
                    "reason": "audio_pause_after_end_of_rendered_video",
                }],
                "uncorrected_output_pause_frame_indices": [782],
                "pause_frame_indices_outside_rendered_video": [1388, 1389],
            },
        }
        stdout = io.StringIO()
        with mock.patch.object(reprocess_pause, "reprocess", return_value=partial_result), contextlib.redirect_stdout(stdout):
            status = reprocess_pause.main([
                "--job-dir", "job", "--motion-base", "motion.mp4", "--pause-correction-region", "mouth-only",
            ])
        self.assertEqual(status, 0)
        output = stdout.getvalue()
        self.assertIn("độ phủ frame pause trong video một phần. Frame có patch đã composite: 189/190 (99.5%)", output)
        self.assertIn("chưa xác nhận trực quan miệng đã khép tự nhiên", output)
        self.assertIn("Pause-time bên trong video nằm ngoài patch frame đầy đủ: 0.040s", output)
        self.assertIn("31.280–31.320s", output)
        self.assertIn("[782]", output)
        self.assertIn("[1388, 1389]", output)
        self.assertIn("Audio pause nằm sau frame video cuối: 0.064s qua 1 đoạn", output)

    def test_offline_reprocess_refuses_old_full_frame_donor_without_original_motion_base(self):
        with tempfile.TemporaryDirectory() as directory:
            job = Path(directory) / "job"
            job.mkdir()
            digest = "a" * 64
            (job / "vertical_ad_report.json").write_text(json.dumps({
                "pause_mouth_closure_policy": {
                    "source_mouth_mode": "speech", "manifest_audio_sha256": digest,
                    "current_input_audio_sha256": digest, "audio_identity_matches": True,
                    "reference_audio": {
                        "status": "verified", "manifest_audio_sha256": digest, "source_sha256": digest,
                    },
                },
                "motion_audio_alignment": {"status": "verified_match", "sha256_matches": True},
                "motion_base": {"path": "C:\\old-machine\\motion_base.mp4", "sha256": digest},
                "videos": [{"pause_mouth_closure": {
                    "status": "applied", "reference_source": "existing_motion_base_video",
                }}],
            }), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "Cần --motion-base gốc"):
                reprocess_pause._verified_job_inputs(job, None)

    @unittest.skipUnless(FFMPEG and FFPROBE, "FFmpeg unavailable")
    def test_offline_reprocess_writes_corrected_native_and_hd_without_model_rerun(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            job = root / "job"
            intermediate = job / "intermediate"
            intermediate.mkdir(parents=True)
            (job / "logs").mkdir()
            audio = intermediate / "audio_unshifted_16k_mono.wav"
            sample_rate = 16000
            pcm = ads.array("h")
            for start, end, amplitude in ((0.0, 0.8, 4000), (0.8, 1.6, 0), (1.6, 3.2, 4000)):
                count = int((end - start) * sample_rate)
                for index in range(count):
                    value = (int(amplitude * math.sin(2.0 * math.pi * 440.0 * (len(pcm) + index) / sample_rate))
                             if amplitude else 0)
                    pcm.append(value)
            with wave.open(str(audio), "wb") as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(sample_rate)
                output.writeframes(pcm.tobytes())
            echo_audio = intermediate / "echo_reference_audio_16k_mono.wav"
            shutil.copyfile(audio, echo_audio)

            base = root / "motion_base.mp4"
            self._ffmpeg([
                "-f", "lavfi", "-i", "color=c=red:s=64x80:r=25:d=3.2",
                "-vf", "drawbox=x=0:y=0:w=iw:h=ih:color=green:t=fill:enable='between(n,20,39)'",
                "-frames:v", "80", "-an", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "0",
                "-pix_fmt", "yuv420p", str(base),
            ])
            rendered = intermediate / "audio_unshifted_video_1.mp4"
            self._ffmpeg([
                "-f", "lavfi", "-i", "color=c=magenta:s=64x80:r=25:d=3.2", "-i", str(audio),
                "-map", "0:v:0", "-map", "1:a:0", "-t", "3.2", "-c:v", "libx264", "-crf", "0",
                "-pix_fmt", "yuv420p", "-c:a", "aac", str(rendered),
            ])

            digest = ads.musetalk.sha256_file(audio)
            report = {
                "effective_audio_duration_seconds": 3.2,
                "pause_mouth_closure_policy": {
                    "source_mouth_mode": "speech", "manifest_audio_sha256": digest,
                    "current_input_audio_sha256": digest, "audio_identity_matches": True,
                    "minimum_pause_seconds": 0.32,
                },
                "motion_audio_alignment": {"status": "verified_match", "sha256_matches": True},
                "motion_base": {"sha256": ads.musetalk.sha256_file(base), "width": 64, "height": 80, "fps": 25.0},
                "audio_alignment": {"unshifted_normalized_audio_sha256": digest},
                "videos": [{"pause_mouth_closure": {
                    "reference_audio_sha256": ads.musetalk.sha256_file(echo_audio),
                    "reference_audio_provenance": {
                        "status": "verified", "manifest_audio_sha256": digest,
                        "source_sha256": digest, "current_audio_sha256": digest,
                    },
                }}],
            }
            (job / "vertical_ad_report.json").write_text(json.dumps(report), encoding="utf-8")

            result = reprocess_pause.reprocess(job, base, FFMPEG, FFPROBE)

            corrected = Path(result["corrected_intermediate"])
            final_video = Path(result["final_output"])
            self.assertTrue(corrected.is_file())
            self.assertTrue(final_video.is_file())
            self.assertEqual(result["models_rerun"], False)
            self.assertEqual(result["pause_correction"]["status"], "applied")
            self.assertEqual(result["reference_policy"], "exact_pingpong_source_frame_mapping")
            self.assertEqual(result["report_path"], str((job / "pause_reprocess_report.json").resolve()))
            self.assertEqual(result["pause_correction"]["source_frame_mapping"]["source_frame_count"], 80)
            self.assertEqual(result["pause_correction"]["covered_duration_seconds"], 0.8)
            final_data = ads.probe_media(final_video, FFPROBE)
            final_stream = ads.stream_by_type(final_data, "video")
            self.assertEqual((int(final_stream["width"]), int(final_stream["height"])), (1080, 1920))
            self.assertTrue((job / "pause_reprocess_report.json").is_file())

    def test_late_pause_without_matching_source_silence_is_left_uncovered(self):
        output_pause = [{"start_seconds": 10.4, "end_seconds": 10.8, "duration_seconds": 0.4}]
        source_pause = [{"start_seconds": 0.4, "end_seconds": 0.8, "duration_seconds": 0.4}]
        aligned = ads.source_aligned_pause_intervals(output_pause, source_pause, 10.8, source_frame_count=129)
        self.assertEqual(aligned, [{"start_seconds": 10.72, "end_seconds": 10.8, "duration_seconds": 0.08}])
        uncovered = ads.subtract_pause_intervals(output_pause, aligned, "no-exact-source-silence")
        self.assertEqual(uncovered, [{
            "start_seconds": 10.4, "end_seconds": 10.72, "duration_seconds": 0.32,
            "reason": "no-exact-source-silence",
        }])

    def test_rms_pauses_protect_quiet_speech_merge_short_interruptions_and_cover_edges(self):
        with tempfile.TemporaryDirectory() as directory:
            audio = Path(directory) / "edge_and_quiet_speech.wav"
            sample_rate = 16000
            segments = [
                (0.40, 0),            # leading pause
                (0.40, 5000),         # ordinary speech
                (0.18, 0),            # pause interrupted by a brief plosive
                (0.02, 18),             # near-threshold interruption, bridged by hysteresis
                (0.22, 0),
                (0.40, 50),           # globally quiet speech, protected by adaptive gate
                (0.24, 0),            # too short for auto
                (0.40, 5000),
                (0.40, 0),            # trailing pause
            ]
            with wave.open(str(audio), "wb") as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(sample_rate)
                pcm = ads.array("h")
                sample_index = 0
                for duration, amplitude in segments:
                    count = int(round(duration * sample_rate))
                    for index in range(count):
                        value = int(amplitude * math.sin(2.0 * math.pi * 440.0 * (sample_index + index) / sample_rate)) if amplitude else 0
                        pcm.append(value)
                    sample_index += count
                output.writeframes(pcm.tobytes())
            auto_intervals = ads.detect_silence_intervals(audio)
            self.assertEqual(len(auto_intervals), 3)
            self.assertAlmostEqual(auto_intervals[0]["start_seconds"], 0.0, delta=0.02)
            self.assertAlmostEqual(auto_intervals[0]["end_seconds"], 0.40, delta=0.02)
            self.assertAlmostEqual(auto_intervals[1]["start_seconds"], 0.80, delta=0.02)
            self.assertAlmostEqual(auto_intervals[1]["end_seconds"], 1.22, delta=0.02)
            self.assertAlmostEqual(auto_intervals[2]["end_seconds"], sample_index / sample_rate, delta=0.02)
            forced_intervals = ads.detect_silence_intervals(audio, min_duration_seconds=0.16)
            self.assertEqual(len(forced_intervals), 4)
            self.assertAlmostEqual(forced_intervals[2]["duration_seconds"], 0.24, delta=0.02)

    @unittest.skipUnless(FFMPEG and FFPROBE, "FFmpeg unavailable")
    def test_ffmpeg_pause_restores_exact_source_silence_matches_and_preserves_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio = root / "speech_two_pauses.wav"
            self._ffmpeg([
                "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=16000:duration=0.8",
                "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono:d=0.4",
                "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=16000:duration=0.76,volume=0.1",
                "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono:d=0.44",
                "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=16000:duration=0.8,volume=0.1",
                "-filter_complex", "[0:a][1:a][2:a][3:a][4:a]concat=n=5:v=0:a=1[a]", "-map", "[a]",
                "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(audio),
            ])
            intervals = ads.detect_silence_intervals(audio)
            self.assertEqual(len(intervals), 2)
            self.assertAlmostEqual(intervals[0]["start_seconds"], 0.8, delta=0.02)
            self.assertAlmostEqual(intervals[1]["start_seconds"], 1.96, delta=0.02)

            base = root / "motion_reference.mp4"
            self._ffmpeg([
                "-f", "lavfi", "-i", "color=c=red:s=64x80:r=25:d=1.2",
                "-vf", "drawbox=x=0:y=0:w=iw:h=ih:color=blue:t=fill:enable='between(n,10,19)',"
                      "drawbox=x=0:y=0:w=iw:h=ih:color=green:t=fill:enable='gte(n,20)'",
                "-frames:v", "30", "-an", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "0",
                "-pix_fmt", "yuv420p", str(base),
            ])
            rendered = root / "musetalk.mp4"
            self._ffmpeg([
                "-f", "lavfi", "-i", "color=c=magenta:s=64x80:r=25:d=3.2", "-i", str(audio),
                "-map", "0:v:0", "-map", "1:a:0", "-t", "3.2", "-c:v", "libx264", "-crf", "0", "-pix_fmt", "yuv420p",
                "-c:a", "aac", str(rendered),
            ])
            corrected = root / "pause_exact_source.mp4"
            provenance = {"status": "verified", "manifest_audio_sha256": "a" * 64,
                          "source_sha256": "a" * 64, "current_audio_sha256": "a" * 64}
            unverified = ads.apply_pause_mouth_closure(
                rendered, base, audio, root / "pause_unverified.mp4", FFMPEG, FFPROBE, 3.2,
                reference_audio=audio,
                reference_audio_provenance={"status": "unverified"},
            )
            self.assertEqual(unverified["status"], "skipped_unverified_reference_audio")
            self.assertEqual(unverified["covered_duration_seconds"], 0.0)
            self.assertGreater(unverified["uncovered_duration_seconds"], 0.7)
            self.assertFalse((root / "pause_unverified.mp4").exists())

            record = ads.apply_pause_mouth_closure(
                rendered, base, audio, corrected, FFMPEG, FFPROBE, 3.2,
                reference_audio=audio, reference_audio_provenance=provenance,
            )
            self.assertEqual(record["status"], "applied")
            self.assertEqual(record["source_frame_count"], 30)
            self.assertEqual(record["source_frame_mapping"]["cycle_frame_count"], 60)
            self.assertEqual(record["intervals"], [
                {"start_seconds": 0.8, "end_seconds": 1.2, "duration_seconds": 0.4},
            ])
            self.assertGreater(record["uncovered_duration_seconds"], 0.4)
            original_info = ads.probe_media(rendered, FFPROBE)
            corrected_info = ads.probe_media(corrected, FFPROBE)
            original_audio = ads.stream_by_type(original_info, "audio")
            corrected_audio = ads.stream_by_type(corrected_info, "audio")
            self.assertEqual(corrected_audio["codec_name"], original_audio["codec_name"])
            self.assertAlmostEqual(ads.media_duration(corrected_info, corrected_audio),
                                   ads.media_duration(original_info, original_audio), delta=0.01)
            original_pcm = subprocess.check_output([
                FFMPEG, "-v", "error", "-i", str(rendered), "-map", "0:a:0", "-ar", "16000", "-ac", "1", "-f", "s16le", "-",
            ])
            corrected_pcm = subprocess.check_output([
                FFMPEG, "-v", "error", "-i", str(corrected), "-map", "0:a:0", "-ar", "16000", "-ac", "1", "-f", "s16le", "-",
            ])
            self.assertEqual(corrected_pcm, original_pcm, "pause closure must preserve every decoded audio sample")

            audio_restored = root / "unshifted_audio_restored.mp4"
            audio_restore = ads.remux_unshifted_audio(rendered, audio, audio_restored, FFMPEG, FFPROBE, 3.2)
            self.assertEqual(audio_restore["status"], "restored")
            restored_closed = root / "restored_audio_pause_closed.mp4"
            ads.apply_pause_mouth_closure(
                audio_restored, base, audio, restored_closed, FFMPEG, FFPROBE, 3.2,
                reference_audio=audio, reference_audio_provenance=provenance,
            )
            restored_pcm = subprocess.check_output([
                FFMPEG, "-v", "error", "-i", str(audio_restored), "-map", "0:a:0", "-ar", "16000", "-ac", "1", "-f", "s16le", "-",
            ])
            final_pcm = subprocess.check_output([
                FFMPEG, "-v", "error", "-i", str(restored_closed), "-map", "0:a:0", "-ar", "16000", "-ac", "1", "-f", "s16le", "-",
            ])
            self.assertEqual(final_pcm, restored_pcm, "pause correction must stream-copy the restored unshifted AAC track")

            selected_frames = (10, 20, 22, 29, 40, 49, 52, 57, 60, 61)
            select_expr = "+".join("eq(n\\,{})".format(index) for index in selected_frames)
            raw = subprocess.check_output([
                FFMPEG, "-v", "error", "-i", str(corrected), "-vf", "select=" + select_expr,
                "-fps_mode", "passthrough", "-frames:v", str(len(selected_frames)), "-f", "rawvideo",
                "-pix_fmt", "rgb24", "-",
            ])
            frame_bytes = 64 * 80 * 3
            self.assertEqual(len(raw), frame_bytes * len(selected_frames))
            expected_colors = ("speech", "transition", "green", "transition", "speech", "speech", "speech", "speech", "speech", "speech")
            pause_colors = set()
            for index, expected in enumerate(expected_colors):
                offset = index * frame_bytes + (40 * 64 + 32) * 3
                red, green, blue = raw[offset:offset + 3]
                if expected in ("green", "transition"):
                    pause_colors.add((red, green, blue))
                if expected == "speech":
                    self.assertGreater(red, 150, "speech frame was replaced at {}: {}".format(selected_frames[index], (red, green, blue)))
                    self.assertGreater(blue, 150, "speech frame was replaced at {}: {}".format(selected_frames[index], (red, green, blue)))
                    self.assertLess(green, 100, "speech frame was altered at {}: {}".format(selected_frames[index], (red, green, blue)))
                elif expected == "transition":
                    self.assertGreater(green, 30, "exact source frame was not blended in the matched pause: {}".format((red, green, blue)))
                    self.assertGreater(red, 30, "transition should retain a short MuseTalk edge: {}".format((red, green, blue)))
                    self.assertGreater(blue, 30, "transition should retain a short MuseTalk edge: {}".format((red, green, blue)))
                elif expected == "green":
                    self.assertGreater(green, max(red, blue) + 60, "matched pause did not restore its exact source frame: {}".format((red, green, blue)))
                else:
                    self.fail("Unexpected expected-color test case: {}".format(expected))

            all_frames = []
            for path in (rendered, corrected):
                decoded = subprocess.check_output([
                    FFMPEG, "-v", "error", "-i", str(path), "-vf", "fps=25",
                    "-frames:v", "80", "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
                ])
                self.assertEqual(len(decoded), frame_bytes * 80)
                all_frames.append(decoded)
            aligned_pause_frames = set()
            for interval in record["intervals"]:
                aligned_pause_frames.update(range(
                    int(round(interval["start_seconds"] * ads.FPS)),
                    int(round(interval["end_seconds"] * ads.FPS)),
                ))
            for frame_index in range(80):
                start = frame_index * frame_bytes
                center = start + (40 * 64 + 32) * 3
                before_green = all_frames[0][center + 1]
                after_green = all_frames[1][center + 1]
                if frame_index in aligned_pause_frames:
                    self.assertGreater(after_green, before_green + 5,
                                       "frame {} inside a matched pause did not restore its exact source frame".format(frame_index))
                else:
                    before = all_frames[0][start:start + frame_bytes]
                    after = all_frames[1][start:start + frame_bytes]
                    mean_error = sum(abs(left - right) for left, right in zip(before, after)) / float(frame_bytes)
                    self.assertLess(mean_error, 3.0,
                                    "speech/non-pause frame {} changed beyond encode tolerance".format(frame_index))
            self.assertEqual(len(pause_colors), 2)
            # At output frame 52 the exact 30-frame ping-pong map points at source frame 7 (red),
            # which is not silent; the later pause must stay unchanged rather than repeat green frames.
            source_frame = subprocess.check_output([
                FFMPEG, "-v", "error", "-i", str(base), "-vf", "select='eq(n\\,7)'", "-frames:v", "1",
                "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
            ])
            self.assertGreater(source_frame[(40 * 64 + 32) * 3], source_frame[(40 * 64 + 32) * 3 + 1])
            # Speech frames remain visually unchanged apart from the expected lossy H.264 re-encode tolerance.
            speech_indices = (10, 40, 61)
            select_speech = "+".join("eq(n\\,{})".format(index) for index in speech_indices)
            original_speech = subprocess.check_output([
                FFMPEG, "-v", "error", "-i", str(rendered), "-vf", "select=" + select_speech,
                "-fps_mode", "passthrough", "-frames:v", str(len(speech_indices)), "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
            ])
            corrected_speech = subprocess.check_output([
                FFMPEG, "-v", "error", "-i", str(corrected), "-vf", "select=" + select_speech,
                "-fps_mode", "passthrough", "-frames:v", str(len(speech_indices)), "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
            ])
            self.assertEqual(len(original_speech), len(corrected_speech))
            mean_error = sum(abs(a - b) for a, b in zip(original_speech, corrected_speech)) / len(original_speech)
            self.assertLess(mean_error, 3.0, "speech frames must remain visually unchanged")
            self.assertEqual(record["reference_cache_state"], "not_needed; reuses existing Echo motion base")

    @unittest.skipUnless(FFMPEG and FFPROBE, "FFmpeg unavailable")
    def test_run_workflow_uses_auto_pause_for_speech_base_and_restores_unshifted_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = cached_fixture.CachedMuseTalkTests()
            paths = fixture._make_fake_musetalk(root / "musetalk")
            base, audio = root / "base.mp4", root / "speech_with_pause.wav"
            self._ffmpeg(["-f", "lavfi", "-i", "color=red:s=64x80:r=25:d=1.2", "-an",
                          "-c:v", "libx264", "-pix_fmt", "yuv420p", str(base)])
            self._write_pause_audio(audio)
            manifest = {
                "mouth_mode": "speech", "source_audio": str(audio.resolve()),
                "fingerprint_inputs": {"audio_sha256": ads.echo.hash_file(audio)},
                "outputs": {"motion_base": {"path": str(base.resolve())}},
            }
            (root / "run_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            backend_audio_pcm = []

            def backend(command, cwd, environment, log_path):
                config = Path(command[command.index("--inference_config") + 1]).read_text().splitlines()
                avatar_id = config[0][:-1]
                avatar = ads.musetalk.avatar_dir_for(Path(cwd), avatar_id)
                fixture._make_fake_avatar_cache(avatar)
                info = json.loads((avatar / "avator_info.json").read_text())
                info["bbox_shift"] = 0
                (avatar / "avator_info.json").write_text(json.dumps(info))
                audio_line = next(line.strip() for line in config if line.strip().startswith("render_"))
                output_name, wav_json = audio_line.split(":", 1)
                configured_audio = Path(json.loads(wav_json))
                _, configured_pcm = ads._read_normalized_pcm(configured_audio)
                backend_audio_pcm.append(configured_pcm)
                duration = ads.musetalk.probe_media(configured_audio, FFPROBE).audio_duration
                self._video(avatar / "vid_output" / (output_name + ".mp4"), duration)
                log_path.parent.mkdir(parents=True, exist_ok=True)
                log_path.write_text("stub CUDA backend; no model loaded\n")
                return 0, .01

            common = ["run", "--base-video", str(base), "--audio", str(audio), "--duration", "1.2",
                      "--audio-offset-ms", "40", "--cache-dir", str(root / "cache"),
                      "--musetalk-dir", str(paths.root), "--musetalk-python", str(paths.python),
                      "--output-root", str(root / "out")]
            with mock.patch.object(ads.musetalk, "run_backend_process", backend), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(ads.main(common), 0)
            report = json.loads(next((root / "out").rglob("vertical_ad_report.json")).read_text())
            video = report["videos"][0]
            self.assertTrue(report["pause_mouth_closure_policy"]["enabled_for_this_base"])
            self.assertEqual(report["motion_audio_alignment"]["status"], "verified_match")
            self.assertTrue(report["motion_audio_alignment"]["sha256_matches"])
            self.assertEqual(report["motion_audio_alignment"]["echo_conditioning_audio_sha256"],
                             ads.echo.hash_file(audio))
            self.assertEqual(video["pause_mouth_closure"]["status"], "applied")
            self.assertEqual(video["pause_mouth_closure"]["reference_video"], str(base.resolve()))
            self.assertEqual(video["audio_conditioning"]["offset_ms"], 40)
            conditioning_variant = report["audio_alignment"]["conditioning_variant_details"]["40"]
            self.assertEqual(video["audio_conditioning"]["conditioning_audio_sha256"], conditioning_variant["sha256"])
            self.assertEqual(conditioning_variant["sha256"],
                             ads.musetalk.sha256_file(Path(conditioning_variant["path"])))
            self.assertEqual(video["audio_conditioning"]["pause_gate"]["interval_count"], 1)
            _, expected_conditioning_pcm = ads._read_normalized_pcm(Path(conditioning_variant["path"]))
            self.assertEqual(backend_audio_pcm[0], expected_conditioning_pcm,
                             "MuseTalk config must receive the pause-gated and offset conditioning waveform")
            gate_report = report["audio_alignment"]["pause_gated_conditioning_audio"]
            self.assertEqual(gate_report["sha256"], ads.musetalk.sha256_file(Path(gate_report["path"])))
            self.assertEqual(video["audio_output_restoration"]["status"], "restored")
            self.assertEqual(video["audio_output_restoration"]["source_sha256"],
                             report["audio_alignment"]["original_normalized_output_audio"]["sha256"])
            self.assertEqual(video["audio_conditioning"]["unshifted_output_audio"],
                             str((Path(report["job_directory"]) / "intermediate" / "audio_unshifted_16k_mono.wav").resolve()))
            decoded_source = subprocess.check_output([
                FFMPEG, "-v", "error", "-i", video["intermediate_for_hd_export"], "-map", "0:a:0",
                "-ar", "16000", "-ac", "1", "-f", "s16le", "-",
            ])
            decoded_output = subprocess.check_output([
                FFMPEG, "-v", "error", "-i", video["output"]["path"], "-map", "0:a:0",
                "-ar", "16000", "-ac", "1", "-f", "s16le", "-",
            ])
            self.assertEqual(decoded_output, decoded_source, "HD export must preserve the unshifted AAC packets exactly")

            manifest["fingerprint_inputs"]["audio_sha256"] = "0" * 64
            (root / "run_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            off_common = list(common)
            off_common[off_common.index("40")] = "0"
            off_common.extend(["--pause-mouth-closure", "off", "--output-root", str(root / "off_out")])
            with (mock.patch.object(ads.musetalk, "run_backend_process", backend),
                  mock.patch.object(ads, "gate_pause_audio", side_effect=AssertionError("off must not gate")),
                  mock.patch.object(ads, "apply_pause_mouth_closure", side_effect=AssertionError("off must not restore frames")),
                  contextlib.redirect_stdout(io.StringIO())):
                self.assertEqual(ads.main(off_common), 0)
            off_report = json.loads(next((root / "off_out").rglob("vertical_ad_report.json")).read_text())
            off_video = off_report["videos"][0]
            self.assertEqual(off_report["audio_alignment"]["pause_gated_conditioning_audio"]["status"], "disabled")
            self.assertEqual(off_report["motion_audio_alignment"]["status"], "mismatch")
            self.assertIn("đầu/vai", off_report["motion_audio_alignment"]["warning"])
            self.assertEqual(off_video["pause_mouth_closure"]["status"], "skipped")
            self.assertEqual(off_video["audio_output_restoration_required"], False)
            self.assertFalse(Path(off_report["job_directory"]).joinpath("intermediate", "pause_closed_video_1.mp4").exists())

    @staticmethod
    def _write_pause_audio(destination):
        with wave.open(str(destination), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(16000)
            pcm = ads.array("h")
            sample_index = 0
            for duration, amplitude in ((0.4, 5000), (0.4, 0), (0.4, 5000)):
                count = int(round(duration * 16000))
                for index in range(count):
                    value = int(amplitude * math.sin(2.0 * math.pi * 440.0 * (sample_index + index) / 16000)) if amplitude else 0
                    pcm.append(value)
                sample_index += count
            output.writeframes(pcm.tobytes())

    @staticmethod
    def _write_synthetic_gate_audio(destination):
        segments = ((3.0, 6000), (0.40, 3), (0.40, 50), (0.24, 0), (3.0, 6000))
        pcm = ads.array("h")
        sample_index = 0
        for duration, amplitude in segments:
            count = int(round(duration * 16000))
            for index in range(count):
                value = int(amplitude * math.sin(2.0 * math.pi * 440.0 * (sample_index + index) / 16000)) if amplitude else 0
                pcm.append(value)
            sample_index += count
        with wave.open(str(destination), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(16000)
            output.writeframes(pcm.tobytes())
        return pcm, {"quiet_speech_start": 3.40, "quiet_speech_end": 3.80}

    @unittest.skipUnless(FFMPEG and FFPROBE, "FFmpeg unavailable")
    def test_neutral_audio_is_zero_pcm_and_mode_separates_fingerprint(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image, audio = root / "image.png", root / "audio.wav"
            self._ffmpeg(["-f", "lavfi", "-i", "color=red:s=64x80", "-frames:v", "1", str(image)])
            self._ffmpeg(["-f", "lavfi", "-i", "sine=frequency=440:duration=0.6", str(audio)])
            _, silent = ads.echo.ffmpeg_prepare_inputs(image, audio, root / "neutral", ads.echo.PROFILES["F1"], .52, FFMPEG, "neutral")
            with wave.open(str(silent)) as stream:
                self.assertEqual((stream.getframerate(), stream.getnchannels()), (16000, 1))
                self.assertEqual(stream.getnframes(), 8320)
                self.assertFalse(any(stream.readframes(stream.getnframes())))
            one, _ = ads.echo.build_job_fingerprint(image, audio, ads.echo.PROFILES["F1"], 13, "rest", [], mouth_mode="neutral")
            two, _ = ads.echo.build_job_fingerprint(image, audio, ads.echo.PROFILES["F1"], 13, "rest", [], mouth_mode="speech")
            self.assertNotEqual(one, two)

    @unittest.skipUnless(FFMPEG and FFPROBE, "FFmpeg unavailable")
    def test_hd_export_preserves_foreground_edges_audio_and_timing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for dims in ("64x80", "72x128"):
                source, output = root / (dims + ".mp4"), root / (dims + "_hd.mp4")
                self._video(source, .48, dims)
                with contextlib.redirect_stdout(io.StringIO()):
                    elapsed, record = ads.export_hd_video(source, output, FFMPEG, FFPROBE, .48, root / (dims + ".log"))
                self.assertEqual((record["width"], record["height"], record["sar"], record["fps"]), (1080, 1920, "1:1", 25.0))
                self.assertGreaterEqual(elapsed, record["encoder_process_seconds"] - .002)
                # Markers near both original side edges must survive the contain composite.
                raw = subprocess.check_output([FFMPEG, "-v", "error", "-i", str(output), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"])
                for x in (80, 990):
                    pixel = raw[(960 * 1080 + x) * 3:(960 * 1080 + x) * 3 + 3]
                    self.assertGreater(pixel[1], pixel[0] + 35)
                with self.assertRaises(FileExistsError):
                    ads.export_hd_video(source, output, FFMPEG, FFPROBE, .48, root / "again.log")
            bad = root / "bad_fps.mp4"
            self._video(bad, .5, fps=30)
            with self.assertRaisesRegex(ValueError, "25 FPS"):
                ads.export_hd_video(bad, root / "bad_hd.mp4", FFMPEG, FFPROBE, .5, root / "bad.log")

    @unittest.skipUnless(FFMPEG and FFPROBE, "FFmpeg unavailable")
    def test_hd_export_keeps_decoded_video_frames_when_audio_runs_longer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output = root / "short_video_long_audio.mp4", root / "short_video_long_audio_hd.mp4"
            self._ffmpeg([
                "-f", "lavfi", "-i", "testsrc=size=64x80:rate=25:duration=0.16",
                "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=16000:duration=0.20",
                "-frames:v", "4", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "64k", "-t", "0.20", str(source),
            ])
            self.assertEqual(ads.count_video_frames(source, FFPROBE), 4)
            with contextlib.redirect_stdout(io.StringIO()):
                _, record = ads.export_hd_video(
                    source, output, FFMPEG, FFPROBE, 0.20, root / "short_video_long_audio.log",
                )
            self.assertEqual(ads.count_video_frames(output, FFPROBE), 4)
            self.assertEqual(record["source_decoded_frame_count"], 4)
            self.assertEqual(record["output_decoded_frame_count"], 4)
            self.assertTrue(record["ffprobe_checks"]["decoded_frame_count_preserved"])

    @unittest.skipUnless(FFMPEG and FFPROBE, "FFmpeg unavailable")
    def test_real_cached_controller_stub_backend_benchmark_and_calibration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = cached_fixture.CachedMuseTalkTests()
            paths = fixture._make_fake_musetalk(root / "musetalk")
            base, audio = root / "base.mp4", root / "audio.wav"
            self._ffmpeg(["-f", "lavfi", "-i", "color=red:s=64x80:r=25:d=0.6", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(base)])
            self._ffmpeg(["-f", "lavfi", "-i", "sine=frequency=440:duration=0.48", "-ar", "16000", str(audio)])
            calls = []

            def backend(command, cwd, environment, log_path):
                calls.append(command)
                config = Path(command[command.index("--inference_config") + 1]).read_text().splitlines()
                avatar_id = config[0][:-1]
                shift = int(next(line.split(":", 1)[1] for line in config if line.strip().startswith("bbox_shift:")))
                avatar = ads.musetalk.avatar_dir_for(Path(cwd), avatar_id)
                fixture._make_fake_avatar_cache(avatar)
                info = json.loads((avatar / "avator_info.json").read_text())
                info["bbox_shift"] = shift
                (avatar / "avator_info.json").write_text(json.dumps(info))
                audio_line = next(line.strip() for line in config if line.strip().startswith("render_"))
                output_name, wav = audio_line.split(":", 1)
                seconds = ads.musetalk.probe_media(Path(json.loads(wav)), FFPROBE).audio_duration
                self._video(avatar / "vid_output" / (output_name + ".mp4"), seconds)
                log_path.parent.mkdir(parents=True, exist_ok=True)
                log_path.write_text("stub CUDA backend; no model loaded\n")
                return 0, .01

            common = ["--base-video", str(base), "--audio", str(audio), "--duration", ".48", "--cache-dir", str(root / "cache"),
                      "--musetalk-dir", str(paths.root), "--musetalk-python", str(paths.python), "--output-root", str(root / "out")]
            with mock.patch.object(ads.musetalk, "run_backend_process", backend), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(ads.main(["benchmark"] + common), 0)
                self.assertEqual(ads.main(["calibrate"] + common), 0)
            self.assertEqual(len(calls), 4)
            benchmark = json.loads(next((root / "out").rglob("benchmark_report.json")).read_text())
            self.assertEqual([v["cache_state"] for v in benchmark["videos"]], ["CREATE", "REUSE"])
            self.assertEqual(benchmark["echo"]["status"], "reused_existing")
            calibration = json.loads(next((root / "out").rglob("lip_calibration_report.json")).read_text())
            self.assertEqual([v["variant"] for v in calibration["videos"]], ["baseline", "raw_mask"])
            self.assertEqual([v["lip_sync_settings"]["bbox_shift"] for v in calibration["videos"]], [0, 0])
            self.assertTrue(calibration["manual_lip_sync_review_required"])
            self.assertIn("forces bbox_shift=0", calibration["calibration_note"])
            self.assertEqual([v["cache_state"] for v in calibration["videos"]], ["REUSE", "CREATE"])
            self.assertEqual(len({v["avatar_cache_path"] for v in calibration["videos"]}), 2)
            self.assertFalse(calibration["videos"][0]["normalized_60s_is_measured"])
            self.assertEqual(calibration["status"], "complete")
            self.assertEqual(calibration["pause_mouth_closure_policy"]["decision"], "skipped_because_motion_base_mode_is_unverified")
            self.assertEqual(calibration["videos"][0]["pause_mouth_closure"]["status"], "skipped")
            # A downstream export error must retain the valid avatar and native render.
            with mock.patch.object(ads.musetalk, "run_backend_process", backend), mock.patch.object(ads, "export_hd_video", side_effect=ValueError("test export rejected")), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(ads.main(["run"] + common), 1)
            failed_path = next((root / "out").rglob("vertical_ad_report.json"))
            failed = json.loads(failed_path.read_text())
            self.assertEqual(failed["status"], "failed")
            self.assertGreater(failed["whole_job_wall_seconds"], 0)
            self.assertTrue(list(failed_path.parent.glob("intermediate/*.mp4")))
            self.assertEqual(len(list((root / "cache").rglob("cache_manifest.json"))), 2)

    @unittest.skipUnless(FFMPEG and FFPROBE, "FFmpeg unavailable")
    def test_failed_workflow_keeps_report_without_faking_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                code = ads.main(["run", "--audio", str(root / "missing.wav"), "--output-root", str(root / "out")])
            self.assertEqual(code, 1)
            report = json.loads(next((root / "out").rglob("vertical_ad_report.json")).read_text())
            self.assertEqual(report["status"], "failed")
            self.assertFalse(list((root / "out").rglob("*.mp4")))

    @staticmethod
    def _ffmpeg(arguments):
        subprocess.run([FFMPEG, "-v", "error", "-y"] + arguments, check=True, stdout=subprocess.DEVNULL)

    @classmethod
    def _video(cls, destination, duration, dims="64x80", fps=25):
        destination.parent.mkdir(parents=True, exist_ok=True)
        cls._ffmpeg(["-f", "lavfi", "-i", f"color=red:s={dims}:r={fps}:d={duration}",
                     "-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=16000:duration={duration}",
                     "-vf", "drawbox=x=0:y=0:w=8:h=ih:color=lime:t=fill,drawbox=x=iw-8:y=0:w=8:h=ih:color=lime:t=fill",
                     "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-t", str(duration), str(destination)])


if __name__ == "__main__":
    unittest.main()
