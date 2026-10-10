from __future__ import annotations

import importlib.util
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "test_cached_musetalk.py"
SPEC = importlib.util.spec_from_file_location("cached_musetalk_test_module", str(SCRIPT))
assert SPEC is not None and SPEC.loader is not None
cached = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = cached
SPEC.loader.exec_module(cached)


def executable(name: str) -> str | None:
    return shutil.which(name)


class CachedMuseTalkTests(unittest.TestCase):
    def test_fingerprint_changes_when_avatar_input_changes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="vcs_fingerprint_") as temp:
            root = Path(temp)
            base = root / "base.mp4"
            base.write_bytes(b"first video bytes")
            info = cached.MediaInfo(3.2, 512, 640, 25.0, True, False)
            paths = self._make_fake_musetalk(root / "musetalk")
            first = cached.build_fingerprint_inputs(base, info, 25, paths)
            base.write_bytes(b"changed video bytes")
            second = cached.build_fingerprint_inputs(base, info, 25, paths)

            self.assertNotEqual(cached.fingerprint_key(first), cached.fingerprint_key(second))

    def test_pycache_does_not_invalidate_model_directory_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory(prefix="vcs_pycache_signature_") as temp:
            root = Path(temp)
            scripts = root / "scripts"
            scripts.mkdir()
            (scripts / "module.py").write_text("print('stable')\n", encoding="utf-8")
            before = cached._directory_signature(scripts)
            pycache = scripts / "__pycache__"
            pycache.mkdir()
            (pycache / "module.cpython-310.pyc").write_bytes(b"runtime bytecode")
            (scripts / "module.pyc").write_bytes(b"runtime bytecode")

            self.assertEqual(before, cached._directory_signature(scripts))

    def test_partial_controller_cache_is_reported_and_preserved(self) -> None:
        with tempfile.TemporaryDirectory(prefix="vcs_partial_cache_") as temp:
            root = Path(temp)
            cache_path = root / "cache" / "abc123"
            cache_path.mkdir(parents=True)
            avatar_root = root / "musetalk"
            avatar_root.mkdir()

            with self.assertRaisesRegex(cached.PipelineError, "dở hoặc thiếu manifest"):
                cached.read_cache_manifest(cache_path, "abc123", {"x": 1}, "avatar_abc", avatar_root)

            self.assertTrue(cache_path.is_dir())
            self.assertEqual(list(cache_path.iterdir()), [])

    def test_partial_upstream_avatar_without_manifest_is_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory(prefix="vcs_partial_avatar_") as temp:
            root = Path(temp)
            musetalk_root = (root / "musetalk").resolve()
            avatar_path = cached.avatar_dir_for(musetalk_root, "avatar_abc")
            avatar_path.mkdir(parents=True)

            with self.assertRaisesRegex(cached.PipelineError, "thiếu controller manifest"):
                cached.read_cache_manifest(root / "cache" / "hash", "hash", {}, "avatar_abc", musetalk_root)

            self.assertTrue(avatar_path.is_dir())

    def test_cache_fingerprint_mismatch_keeps_existing_cache(self) -> None:
        with tempfile.TemporaryDirectory(prefix="vcs_cache_mismatch_") as temp:
            root = Path(temp)
            cache_path = root / "cache"
            cache_path.mkdir()
            (cache_path / "cache_manifest.json").write_text(
                json.dumps({"schema": cached.CACHE_SCHEMA, "fingerprint": "other", "inputs": {}}),
                encoding="utf-8",
            )
            musetalk_root = root / "musetalk"
            musetalk_root.mkdir()

            with self.assertRaisesRegex(cached.PipelineError, "không khớp"):
                cached.read_cache_manifest(cache_path, "expected", {}, "avatar_abc", musetalk_root)
            self.assertTrue((cache_path / "cache_manifest.json").is_file())

    def test_reuse_rejects_corrupt_cached_base_video_copy(self) -> None:
        with tempfile.TemporaryDirectory(prefix="vcs_cache_base_integrity_") as temp:
            root = Path(temp)
            source_video = root / "source.mp4"
            source_video.write_bytes(b"original motion base")
            cache_path = root / "cache" / "cache-key"
            (cache_path / "input").mkdir(parents=True)
            cached_base = cache_path / "input" / "base_video.mp4"
            cached_base.write_bytes(source_video.read_bytes())
            avatar_id = "avatar_abc"
            musetalk_root = root / "musetalk"
            self._make_fake_avatar_cache(cached.avatar_dir_for(musetalk_root, avatar_id))
            inputs = {"base_video": {"sha256": cached.sha256_file(source_video)}}
            (cache_path / "cache_manifest.json").write_text(
                json.dumps({"schema": cached.CACHE_SCHEMA, "fingerprint": "cache-key", "inputs": inputs}),
                encoding="utf-8",
            )

            cached.read_cache_manifest(cache_path, "cache-key", inputs, avatar_id, musetalk_root)
            cached_base.write_bytes(b"corrupt copy")
            with self.assertRaisesRegex(cached.PipelineError, "sai SHA-256"):
                cached.read_cache_manifest(cache_path, "cache-key", inputs, avatar_id, musetalk_root)
            self.assertTrue((cache_path / "cache_manifest.json").is_file())

    def test_shell_path_rules_reject_spaces_but_allow_user_output_spaces(self) -> None:
        self.assertTrue(cached.is_safe_upstream_path(r"C:\vcs_cache\abc\input.wav"))
        self.assertFalse(cached.is_safe_upstream_path(r"C:\Users\Admin\Muse Talk\input.wav"))
        self.assertFalse(cached.is_safe_upstream_path("/tmp/MuseTalk/ảnh.png"))

        with tempfile.TemporaryDirectory(prefix="vcs_paths_") as temp:
            output = Path(temp) / "final output.mp4"
            self.assertIn(" ", str(output))
            self.assertFalse(cached.is_safe_upstream_path(output))
            # Final output never enters upstream's shell command; it is copied after verification.
            self.assertTrue(callable(cached.atomic_copy_output))

    def test_output_cannot_alias_inputs_or_live_cache_trees(self) -> None:
        with tempfile.TemporaryDirectory(prefix="vcs_output_guard_") as temp:
            root = Path(temp)
            base = root / "base.mp4"
            audio = root / "voice.wav"
            base.write_bytes(b"base")
            audio.write_bytes(b"audio")
            cache = root / "cache"
            avatars = root / "musetalk" / "results" / "v15" / "avatars"

            with self.assertRaisesRegex(cached.PipelineError, "file đầu vào"):
                cached.validate_output_target(base, (base, audio), (cache, avatars))
            with self.assertRaisesRegex(cached.PipelineError, "cache/avatar input tree"):
                cached.validate_output_target(cache / "render.mp4", (base, audio), (cache, avatars))

            hardlink = root / "base_hardlink.mp4"
            try:
                hardlink.hardlink_to(base)
            except OSError:
                self.skipTest("filesystem does not support hard links")
            with self.assertRaisesRegex(cached.PipelineError, "file đầu vào"):
                cached.validate_output_target(hardlink, (base, audio), (cache, avatars))

    def test_duration_coverage_rejects_audio_that_would_loop_motion(self) -> None:
        cached.validate_duration_coverage(3.2, 3.24, 25)
        with self.assertRaisesRegex(cached.PipelineError, "từ chối để MuseTalk không lặp"):
            cached.validate_duration_coverage(3.5, 3.24, 25)
        with self.assertRaisesRegex(cached.PipelineError, "Audio và video nền"):
            cached.validate_duration_coverage(float("nan"), 3.24, 25)

    def test_pingpong_policy_is_opt_in_and_reports_nominal_cycles(self) -> None:
        with self.assertRaises(cached.PipelineError):
            cached.validate_motion_coverage(55.584, 20.04, 25, "error")
        cached.validate_motion_coverage(55.584, 20.04, 25, "pingpong")
        metadata = cached.build_motion_metadata(55.584, 20.04, "pingpong")
        self.assertEqual(metadata["motion_policy"], "pingpong")
        self.assertEqual(metadata["source_video_duration_seconds"], 20.04)
        self.assertEqual(metadata["nominal_full_motion_cycle_seconds"], 40.08)
        self.assertEqual(metadata["nominal_motion_cycles"], 2)
        self.assertEqual(metadata["nominal_motion_repeats"], 1)
        with self.assertRaisesRegex(cached.PipelineError, "chỉ nhận error hoặc pingpong"):
            cached.validate_motion_coverage(55.584, 20.04, 25, "loop")

    def test_bbox_shift_fails_fast_when_v15_source_forces_zero(self) -> None:
        with tempfile.TemporaryDirectory(prefix="vcs_bbox_shift_support_") as temp:
            inference_script = Path(temp) / "realtime_inference.py"
            inference_script.write_text(
                'if args.version == "v15":\n    bbox_shift = 0\nelse:\n    bbox_shift = inference_config[avatar_id]["bbox_shift"]\n',
                encoding="utf-8",
            )
            cached.validate_bbox_shift_support(inference_script, 0)
            with self.assertRaisesRegex(cached.PipelineError, "ép bbox_shift về 0"):
                cached.validate_bbox_shift_support(inference_script, -4)

    def test_pingpong_requires_recognized_upstream_forward_reverse_implementation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="vcs_pingpong_source_") as temp:
            source = Path(temp) / "realtime_inference.py"
            source.write_text(self._pingpong_source(), encoding="utf-8")
            cached.validate_pingpong_support(source)
            source.write_text("frame_list_cycle = frame_list\n", encoding="utf-8")
            with self.assertRaisesRegex(cached.PipelineError, "source hiện tại khác phiên bản hỗ trợ"):
                cached.validate_pingpong_support(source)

    def test_pipeline_rejects_nonfinite_duration_before_file_discovery(self) -> None:
        with self.assertRaisesRegex(cached.PipelineError, "duration phải lớn hơn 0"):
            cached.run_pipeline(
                action="dry-run",
                base_video=Path("missing_base.mp4"),
                audio=Path("missing_audio.mp3"),
                duration=float("nan"),
                output=Path("output.mp4"),
                cache_dir=Path("cache"),
            )

    def test_backend_argv_is_a_list_and_never_enables_skip_save(self) -> None:
        with tempfile.TemporaryDirectory(prefix="vcs_argv_") as temp:
            root = Path(temp)
            paths = cached.MuseTalkPaths(
                root=root / "MuseTalk With Space",
                python=root / "Python With Space" / "python.exe",
                inference_script=root / "MuseTalk With Space" / "scripts" / "realtime_inference.py",
                unet_model=root / "MuseTalk With Space" / "models" / "musetalkV15" / "unet.pth",
                unet_config=root / "MuseTalk With Space" / "models" / "musetalkV15" / "musetalk.json",
                whisper_dir=root / "MuseTalk With Space" / "models" / "whisper",
                vae_dir=root / "MuseTalk With Space" / "models" / "sd-vae",
                dwpose_dir=root / "MuseTalk With Space" / "models" / "dwpose",
                face_parsing_dir=root / "MuseTalk With Space" / "models" / "face-parse-bisent",
            )
            command = cached.build_backend_command(
                paths, root / "cache" / "job" / "settings.yaml", "render_123",
                2, 25, "jaw", 10, 90, 90, 2, 2,
            )
            self.assertIsInstance(command, list)
            self.assertEqual(command[0], str(paths.python))
            self.assertIn(str(paths.root / "scripts" / "realtime_inference.py"), command)
            self.assertNotIn("--skip_save_images", command)
            self.assertNotIn("--use_float16", command)
            self.assertEqual(command[command.index("--bbox_shift") + 1], "0")

    def test_backend_environment_adds_musetalk_root_for_direct_script_import(self) -> None:
        with tempfile.TemporaryDirectory(prefix="vcs_pythonpath_import_") as temp:
            root = Path(temp) / "fake_musetalk"
            package = root / "musetalk"
            scripts = root / "scripts"
            package.mkdir(parents=True)
            scripts.mkdir()
            (package / "__init__.py").write_text("", encoding="utf-8")
            (package / "utils.py").write_text("VALUE = 'root-import-ok'\n", encoding="utf-8")
            inference_script = scripts / "realtime_inference.py"
            inference_script.write_text(
                "import musetalk.utils\nprint(musetalk.utils.VALUE)\n",
                encoding="utf-8",
            )
            command = [sys.executable, "-u", str(inference_script)]

            clean_environment = dict(os.environ)
            clean_environment.pop("PYTHONPATH", None)
            failed = subprocess.run(
                command,
                cwd=root,
                env=clean_environment,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn("No module named 'musetalk'", failed.stderr)

            existing_pythonpath = str(root.parent / "existing_pythonpath")
            base_environment = dict(clean_environment)
            base_environment["PYTHONPATH"] = existing_pythonpath
            original_environment = dict(base_environment)
            backend_environment = cached.build_backend_environment(
                sys.executable,
                base_environment,
                musetalk_root=root,
            )
            self.assertEqual(base_environment, original_environment)
            self.assertEqual(
                backend_environment["PYTHONPATH"],
                str(root.resolve()) + os.pathsep + existing_pythonpath,
            )
            log_path = root / "backend.log"
            with contextlib.redirect_stdout(io.StringIO()):
                return_code, _ = cached.run_backend_process(
                    command,
                    root,
                    backend_environment,
                    log_path,
                )
            self.assertEqual(return_code, 0)
            self.assertIn("root-import-ok", log_path.read_text(encoding="utf-8"))

    def test_output_verification_rejects_wrong_fps_when_ffmpeg_is_available(self) -> None:
        ffmpeg = executable("ffmpeg")
        ffprobe = executable("ffprobe")
        if not ffmpeg or not ffprobe:
            self.skipTest("ffmpeg/ffprobe not installed")
        with tempfile.TemporaryDirectory(prefix="vcs_media_verify_") as temp:
            output = Path(temp) / "wrong_fps.mp4"
            self._make_av_video(ffmpeg, output, 64, 64, 24, 1.0)
            expected = cached.MediaInfo(1.0, 64, 64, 25.0, True, False)
            with self.assertRaisesRegex(cached.PipelineError, "Sai FPS đầu ra"):
                cached.verify_rendered_output(output, expected, 25, 1.0, ffprobe)

    def test_output_verification_checks_audio_duration_separately(self) -> None:
        ffmpeg = executable("ffmpeg")
        ffprobe = executable("ffprobe")
        if not ffmpeg or not ffprobe:
            self.skipTest("ffmpeg/ffprobe not installed")
        with tempfile.TemporaryDirectory(prefix="vcs_audio_duration_") as temp:
            output = Path(temp) / "audio_shorter.mp4"
            command = [
                ffmpeg, "-y", "-v", "error",
                "-f", "lavfi", "-i", "color=c=green:s=64x64:r=25:d=1.0",
                "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=16000:duration=0.4",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-t", "1.0", str(output),
            ]
            result = subprocess.run(command, capture_output=True, text=True)
            if result.returncode != 0:
                self.fail(result.stderr)
            info = cached.probe_media(output, ffprobe)
            self.assertGreater(info.video_duration, 0.9)
            self.assertLess(info.audio_duration, 0.6)
            expected = cached.MediaInfo(1.0, 64, 64, 25.0, True, True)
            with self.assertRaisesRegex(cached.PipelineError, "thời lượng luồng audio"):
                cached.verify_rendered_output(output, expected, 25, 1.0, ffprobe)

    def test_stub_backend_renders_and_reuses_avatar_cache(self) -> None:
        ffmpeg = executable("ffmpeg")
        ffprobe = executable("ffprobe")
        if not ffmpeg or not ffprobe:
            self.skipTest("ffmpeg/ffprobe not installed")

        with tempfile.TemporaryDirectory(prefix="vcs_cached_musetalk_") as temp:
            root = Path(temp)
            project = root / "project"
            project.mkdir()
            musetalk_root = (root / "musetalk").resolve()
            paths = self._make_fake_musetalk(musetalk_root)
            base_video = project / "base.mp4"
            audio = project / "audio.wav"
            self._make_base_video(ffmpeg, base_video)
            self._make_audio(ffmpeg, audio)
            cache_dir = root / "cache_root"
            output = project / "final output with spaces.mp4"
            log = project / "backend.log"
            backend_calls: list[tuple[list[str], Path]] = []

            def stub_backend(command, cwd, environment, log_path):
                backend_calls.append((list(command), Path(cwd)))
                self.assertEqual(Path(cwd), musetalk_root)
                config_arg = Path(command[command.index("--inference_config") + 1])
                config_lines = config_arg.read_text(encoding="utf-8").splitlines()
                avatar_id = config_lines[0].split(":", 1)[0]
                audio_clips_index = next(
                    (index for index, line in enumerate(config_lines) if line.strip() == "audio_clips:"),
                    None,
                )
                audio_line = config_lines[audio_clips_index + 1].strip() if audio_clips_index is not None else None
                render_duration = 0.4
                if "  audio_clips: {}" in config_lines:
                    self.assertNotIn("--output_vid_name", command)
                if audio_line:
                    yaml_output_name = audio_line.split(":", 1)[0]
                    normalized_audio = Path(json.loads(audio_line.split(":", 1)[1].strip()))
                    normalized_info = cached.probe_media(normalized_audio, ffprobe)
                    render_duration = normalized_info.audio_duration or normalized_info.duration
                    self.assertEqual((normalized_info.sample_rate, normalized_info.channels, normalized_info.audio_codec), (16000, 1, "pcm_s16le"))
                    self.assertTrue(cached.is_safe_upstream_path(normalized_audio))
                avatar_dir = cached.avatar_dir_for(musetalk_root, avatar_id)
                self._make_fake_avatar_cache(avatar_dir)
                if "--output_vid_name" in command:
                    # Upstream names vid_output from the audio_clips mapping key,
                    # not the CLI --output_vid_name option.
                    generated = avatar_dir / "vid_output" / (yaml_output_name + ".mp4")
                    self._make_av_video(ffmpeg, generated, 64, 64, 25, render_duration)
                log_path.parent.mkdir(parents=True, exist_ok=True)
                log_path.write_text("stub backend completed\n", encoding="utf-8")
                return 0, 0.01

            common = dict(
                base_video=base_video,
                audio=audio,
                duration=0.4,
                output=output,
                cache_dir=cache_dir,
                fps=25,
                batch_size=2,
                musetalk_dir=musetalk_root,
                musetalk_python=Path(sys.executable),
                ffmpeg_override=ffmpeg,
                ffprobe_override=ffprobe,
                log_path=log,
                backend_runner=stub_backend,
            )
            with contextlib.redirect_stdout(io.StringIO()):
                dry = cached.run_pipeline("dry-run", **common)
                self.assertFalse(dry["cache_hit"])
                self.assertEqual(backend_calls, [])
                cold = cached.run_pipeline("run", **common)
            self.assertFalse(cold["cache_hit"])
            self.assertTrue(output.is_file())
            self.assertGreater(output.stat().st_size, 1000)
            self.assertTrue(any(" " in arg for arg in (str(output),)))
            self.assertEqual(len(backend_calls), 1)

            with contextlib.redirect_stdout(io.StringIO()):
                warm = cached.run_pipeline("run", **common)
            self.assertTrue(warm["cache_hit"])
            self.assertEqual(len(backend_calls), 2)
            self.assertEqual(backend_calls[1][1], musetalk_root)
            self.assertTrue(output.is_file())
            self.assertIn("--output_vid_name", backend_calls[1][0])
            self.assertTrue(log.is_file())

            long_audio = project / "long_audio.wav"
            long_output = project / "full_script.mp4"
            self._make_audio(ffmpeg, long_audio, duration=2.4)
            long_args = dict(common)
            long_args.update(
                audio=long_audio,
                duration=60.0,
                output=long_output,
                motion_policy="pingpong",
            )
            strict_args = dict(long_args)
            strict_args.pop("motion_policy")
            with self.assertRaisesRegex(cached.PipelineError, "không lặp ngầm"):
                cached.run_pipeline("dry-run", **strict_args)
            with contextlib.redirect_stdout(io.StringIO()):
                long_render = cached.run_pipeline("run", **long_args)
            self.assertTrue(long_render["cache_hit"])
            self.assertEqual(long_render["cache_path"], cold["cache_path"])
            self.assertAlmostEqual(long_render["audio_duration"], 2.4, delta=0.1)
            self.assertEqual(long_render["nominal_full_motion_cycle_seconds"], 2.0)
            self.assertTrue(long_output.is_file())
            manifest = next(
                json.loads(path.read_text(encoding="utf-8"))
                for path in Path(long_render["cache_path"]).glob("jobs/*/render_manifest.json")
                if json.loads(path.read_text(encoding="utf-8")).get("output") == str(long_output.resolve())
            )
            self.assertEqual(manifest["motion_policy"], "pingpong")
            self.assertEqual(manifest["source_video_duration_seconds"], 1.0)
            self.assertEqual(manifest["nominal_full_motion_cycle_seconds"], 2.0)
            self.assertEqual(manifest["nominal_motion_cycles"], 2)
            self.assertEqual(manifest["nominal_motion_repeats"], 1)
            self.assertAlmostEqual(manifest["normalized_audio_duration_seconds"], 2.4, delta=0.1)

            second_base = project / "prepare_only.mp4"
            prepare_cache_dir = root / "prepare_cache"
            self._make_base_video(ffmpeg, second_base, color="red")
            prepare_args = dict(common)
            prepare_args["base_video"] = second_base
            prepare_args["cache_dir"] = prepare_cache_dir
            with contextlib.redirect_stdout(io.StringIO()):
                prepared = cached.run_pipeline("prepare", **prepare_args)
            self.assertFalse(prepared["cache_hit"])
            self.assertTrue((Path(prepared["cache_path"]) / "cache_manifest.json").is_file())
            self.assertNotIn("--output_vid_name", backend_calls[3][0])

    def _make_fake_musetalk(self, root: Path) -> cached.MuseTalkPaths:
        scripts = root / "scripts"
        scripts.mkdir(parents=True)
        inference = scripts / "realtime_inference.py"
        inference.write_text(self._pingpong_source(), encoding="utf-8")
        models = root / "models"
        files = {
            models / "musetalkV15" / "unet.pth": b"unet checkpoint",
            models / "musetalkV15" / "musetalk.json": b"{}",
            models / "whisper" / "config.json": b"{}",
            models / "whisper" / "preprocessor_config.json": b"{}",
            models / "whisper" / "pytorch_model.bin": b"whisper weights",
            models / "sd-vae" / "config.json": b"{}",
            models / "sd-vae" / "diffusion_pytorch_model.bin": b"vae weights",
            models / "dwpose" / "dw-ll_ucoco_384.pth": b"dwpose weights",
            models / "face-parse-bisent" / "79999_iter.pth": b"face parser weights",
            models / "face-parse-bisent" / "resnet18-5c106cde.pth": b"resnet weights",
        }
        for path, content in files.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        return cached.discover_musetalk_paths(root, Path(sys.executable))

    @staticmethod
    def _make_fake_avatar_cache(avatar_dir: Path) -> None:
        (avatar_dir / "full_imgs").mkdir(parents=True, exist_ok=True)
        (avatar_dir / "mask").mkdir(parents=True, exist_ok=True)
        (avatar_dir / "vid_output").mkdir(parents=True, exist_ok=True)
        (avatar_dir / "full_imgs" / "00000000.png").write_bytes(b"image")
        (avatar_dir / "mask" / "00000000.png").write_bytes(b"mask")
        (avatar_dir / "coords.pkl").write_bytes(b"coords")
        (avatar_dir / "latents.pt").write_bytes(b"latents")
        (avatar_dir / "mask_coords.pkl").write_bytes(b"mask coords")
        (avatar_dir / "avator_info.json").write_text(
            json.dumps({"avatar_id": avatar_dir.name, "bbox_shift": 0, "version": "v15"}),
            encoding="utf-8",
        )

    @staticmethod
    def _make_base_video(ffmpeg: str, path: Path, color: str = "blue") -> None:
        command = [
            ffmpeg, "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c={color}:s=64x64:r=25:d=1.0",
            "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path),
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(result.stderr)

    @staticmethod
    def _make_audio(ffmpeg: str, path: Path, duration: float = 0.5) -> None:
        command = [
            ffmpeg, "-y", "-v", "error", "-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=44100:duration={duration:.4f}",
            "-ac", "2", "-ar", "44100", str(path),
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(result.stderr)

    @staticmethod
    def _pingpong_source() -> str:
        return """
        self.frame_list_cycle = frame_list + frame_list[::-1]
        self.coord_list_cycle = coord_list + coord_list[::-1]
        self.input_latent_list_cycle = input_latent_list + input_latent_list[::-1]
        bbox = self.coord_list_cycle[self.idx % (len(self.coord_list_cycle))]
        ori_frame = self.frame_list_cycle[self.idx % (len(self.frame_list_cycle))]
        gen = datagen(whisper_chunks, self.input_latent_list_cycle, self.batch_size)
        """

    @staticmethod
    def _make_av_video(ffmpeg: str, path: Path, width: int, height: int, fps: int, duration: float) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        command = [
            ffmpeg, "-y", "-v", "error",
            "-f", "lavfi", "-i", f"color=c=green:s={width}x{height}:r={fps}:d={duration:.4f}",
            "-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=16000:duration={duration:.4f}",
            "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-t", f"{duration:.4f}", str(path),
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(result.stderr)


if __name__ == "__main__":
    unittest.main()
