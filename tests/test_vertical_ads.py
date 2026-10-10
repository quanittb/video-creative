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
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import test_vertical_ads as ads
from tests import test_cached_musetalk as cached_fixture

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")


class VerticalAdsTests(unittest.TestCase):
    def test_profiles_cli_and_phase_metrics(self):
        args = ads.make_parser().parse_args(["run"])
        self.assertEqual((args.profile, args.mouth_mode), ("A10", "speech"))
        self.assertEqual(args.pause_mouth_closure, "auto")
        self.assertEqual(args.audio_offset_ms, 0)
        help_text = " ".join(ads.make_parser().format_help().split())
        self.assertIn("speech dùng audio thật để sinh chuyển động", help_text)
        self.assertIn("không khuyến nghị làm motion base chuyển động", help_text)
        self.assertIn("cùng frame motion base", help_text)
        self.assertIn("Dương làm miệng trễ audio", help_text)
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
        self.assertIn("[1:v]fps=25,setpts=PTS-STARTPTS", graph)

    def test_only_closes_when_mapped_source_time_was_also_silent(self):
        safe, uncovered = ads.split_pause_intervals_by_reference_audio(
            [{"start_seconds": 0.4, "end_seconds": 0.8}, {"start_seconds": 10.4, "end_seconds": 10.8}],
            [{"start_seconds": 0.4, "end_seconds": 0.8}],
            source_frame_count=129, duration_seconds=10.8,
        )
        self.assertEqual(safe[0], {"start_seconds": 0.4, "end_seconds": 0.8, "duration_seconds": 0.4})
        self.assertEqual(safe[1], {"start_seconds": 10.72, "end_seconds": 10.8, "duration_seconds": 0.08})
        self.assertEqual(uncovered[0], {"start_seconds": 10.4, "end_seconds": 10.72, "duration_seconds": 0.32})

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
    def test_ffmpeg_pause_detection_preserves_speech_and_restores_moving_pingpong_frames(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio = root / "speech_pause_quiet_speech.wav"
            self._ffmpeg([
                "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=16000:duration=0.4",
                "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono:d=0.4",
                "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=16000:duration=0.4,volume=0.1",
                "-filter_complex", "[0:a][1:a][2:a]concat=n=3:v=0:a=1[a]", "-map", "[a]",
                "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(audio),
            ])
            intervals = ads.detect_silence_intervals(audio)
            self.assertEqual(len(intervals), 1)
            self.assertAlmostEqual(intervals[0]["start_seconds"], 0.4, delta=0.02)
            self.assertAlmostEqual(intervals[0]["end_seconds"], 0.8, delta=0.02)

            base = root / "motion_reference.mp4"
            self._ffmpeg([
                "-f", "lavfi", "-i", "color=c=black:s=64x80:r=25:d=1.2",
                "-vf", "drawbox=x=0:y=0:w=iw:h=ih:color=red:t=fill:enable='eq(mod(n,4),0)',"
                      "drawbox=x=0:y=0:w=iw:h=ih:color=green:t=fill:enable='eq(mod(n,4),1)',"
                      "drawbox=x=0:y=0:w=iw:h=ih:color=blue:t=fill:enable='eq(mod(n,4),2)',"
                      "drawbox=x=0:y=0:w=iw:h=ih:color=yellow:t=fill:enable='eq(mod(n,4),3)'",
                "-frames:v", "30", "-an", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "0",
                "-pix_fmt", "yuv420p", str(base),
            ])
            rendered = root / "musetalk.mp4"
            self._ffmpeg([
                "-f", "lavfi", "-i", "color=c=magenta:s=64x80:r=25:d=1.2", "-i", str(audio),
                "-map", "0:v:0", "-map", "1:a:0", "-t", "1.2", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac", str(rendered),
            ])
            corrected = root / "pause_closed.mp4"
            record = ads.apply_pause_mouth_closure(rendered, base, audio, corrected, FFMPEG, FFPROBE, 1.2)
            self.assertEqual(record["status"], "applied")
            self.assertEqual(record["source_frame_count"], 30)
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
            audio_restore = ads.remux_unshifted_audio(rendered, audio, audio_restored, FFMPEG, FFPROBE, 1.2)
            self.assertEqual(audio_restore["status"], "restored")
            restored_closed = root / "restored_audio_pause_closed.mp4"
            ads.apply_pause_mouth_closure(audio_restored, base, audio, restored_closed, FFMPEG, FFPROBE, 1.2)
            restored_pcm = subprocess.check_output([
                FFMPEG, "-v", "error", "-i", str(audio_restored), "-map", "0:a:0", "-ar", "16000", "-ac", "1", "-f", "s16le", "-",
            ])
            final_pcm = subprocess.check_output([
                FFMPEG, "-v", "error", "-i", str(restored_closed), "-map", "0:a:0", "-ar", "16000", "-ac", "1", "-f", "s16le", "-",
            ])
            self.assertEqual(final_pcm, restored_pcm, "pause correction must stream-copy the restored unshifted AAC track")

            selected_frames = (2, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21)
            select_expr = "+".join("eq(n\\,{})".format(index) for index in selected_frames)
            raw = subprocess.check_output([
                FFMPEG, "-v", "error", "-i", str(corrected), "-vf", "select=" + select_expr,
                "-fps_mode", "passthrough", "-frames:v", str(len(selected_frames)), "-f", "rawvideo",
                "-pix_fmt", "rgb24", "-",
            ])
            frame_bytes = 64 * 80 * 3
            self.assertEqual(len(raw), frame_bytes * len(selected_frames))
            expected_colors = ("speech", "speech", "transition", "red", "green", "blue", "yellow", "red", "green", "blue", "transition", "speech", "speech")
            pause_colors = set()
            for index, expected in enumerate(expected_colors):
                offset = index * frame_bytes + (40 * 64 + 32) * 3
                red, green, blue = raw[offset:offset + 3]
                if 3 <= index <= 9:
                    pause_colors.add((red, green, blue))
                if expected == "speech":
                    self.assertGreater(red, 200, "speech frame was replaced at {}: {}".format(selected_frames[index], (red, green, blue)))
                    self.assertGreater(blue, 200, "speech frame was replaced at {}: {}".format(selected_frames[index], (red, green, blue)))
                    self.assertLess(green, 50, "speech frame was altered at {}: {}".format(selected_frames[index], (red, green, blue)))
                elif expected == "transition":
                    self.assertGreater(red, 200, "pause transition did not retain shared red component: {}".format((red, green, blue)))
                    self.assertGreater(green, 30, "pause transition did not blend source frame: {}".format((red, green, blue)))
                    self.assertGreater(blue, 30, "pause transition did not blend MuseTalk frame: {}".format((red, green, blue)))
                elif expected == "red":
                    self.assertGreater(red, max(green, blue) + 60, "frame {} RGB={}".format(selected_frames[index], (red, green, blue)))
                elif expected == "green":
                    self.assertGreater(green, max(red, blue) + 30, "frame {} RGB={}".format(selected_frames[index], (red, green, blue)))
                elif expected == "blue":
                    self.assertGreater(blue, max(red, green) + 60, "frame {} RGB={}".format(selected_frames[index], (red, green, blue)))
                else:
                    self.assertGreater(red, blue + 60, "frame {} RGB={}".format(selected_frames[index], (red, green, blue)))
                    self.assertGreater(green, blue + 30, "frame {} RGB={}".format(selected_frames[index], (red, green, blue)))
            self.assertGreaterEqual(len(pause_colors), 3, "pause restoration must follow the moving ping-pong source, not freeze one frame")
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
                duration = ads.musetalk.probe_media(Path(json.loads(wav_json)), FFPROBE).audio_duration
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
            self.assertEqual(video["pause_mouth_closure"]["status"], "applied")
            self.assertEqual(video["pause_mouth_closure"]["reference_video"], str(base.resolve()))
            self.assertEqual(video["audio_conditioning"]["offset_ms"], 40)
            self.assertEqual(video["audio_output_restoration"]["status"], "restored")
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
