import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import echo_flash_backend as backend
import echo_flash_windows as controller


def _test_tool(env_name, default):
    value = os.environ.get(env_name, default)
    return shutil.which(value) or (str(Path(value).resolve()) if Path(value).is_file() else None)


HAS_MEDIA_TOOLS = bool(_test_tool("FFMPEG", "ffmpeg") and _test_tool("FFPROBE", "ffprobe"))


class FakeResponse:
    def __init__(self, payload, status=200, headers=None):
        self._stream = io.BytesIO(payload)
        self.status = status
        self.headers = headers or {}

    def read(self, size=-1):
        return self._stream.read(size)

    def close(self):
        self._stream.close()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


class ControllerUnitTests(unittest.TestCase):
    def test_profiles_and_temporal_frame_rule(self):
        self.assertEqual(controller.PROFILES["F1"].width, 384)
        self.assertEqual(controller.PROFILES["F1"].height, 480)
        self.assertEqual(controller.PROFILES["F1"].seed, 42)
        self.assertEqual(controller.PROFILES["F2"].frames, 81)
        self.assertEqual(controller.PROFILES["F3"].seed, 43)
        self.assertEqual(controller.effective_frames(3.24, controller.PROFILES["F1"]), 81)
        self.assertEqual(controller.effective_frames(3.0, controller.PROFILES["F1"]), 73)
        with self.assertRaises(ValueError):
            controller.effective_frames(float("nan"), controller.PROFILES["F1"])

    def test_audio_coverage_fails_closed_without_looping(self):
        image = Path("portrait.png")
        audio = Path("voice.wav")
        image_result = {"streams": [{"codec_type": "video", "width": 1024, "height": 1280}]}
        audio_result = {
            "streams": [{"codec_type": "audio", "duration": "3.20", "sample_rate": "16000", "channels": 1}],
            "format": {"duration": "3.20"},
        }
        with mock.patch.object(controller.Path, "is_file", return_value=True), mock.patch.object(controller.Path, "stat") as stat_mock:
            stat_mock.return_value.st_size = 123
            with mock.patch.object(controller, "probe_media", side_effect=[image_result, audio_result]):
                with self.assertRaisesRegex(ValueError, "không tự lặp audio"):
                    controller.validate_input_media(image, audio, controller.PROFILES["F1"], 3.24)

    def test_duration_below_loudness_window_is_rejected_before_model_load(self):
        image = Path("portrait.png")
        audio = Path("voice.wav")
        with mock.patch.object(controller.Path, "is_file", return_value=True), mock.patch.object(controller.Path, "stat") as stat_mock:
            stat_mock.return_value.st_size = 123
            with mock.patch.object(controller, "probe_media", side_effect=[
                {"streams": [{"codec_type": "video", "width": 1024, "height": 1280}]},
                {"streams": [{"codec_type": "audio", "duration": "1.0", "sample_rate": "16000", "channels": 1}], "format": {"duration": "1.0"}},
            ]):
                with self.assertRaisesRegex(ValueError, "tối thiểu là 13 frame"):
                    controller.validate_input_media(image, audio, controller.PROFILES["F1"], 0.4)

    def test_child_environment_preserves_parent_and_does_not_mutate_it(self):
        inherited = {"PATH": "parent-path", "PYTHONPATH": "existing path with spaces", "OTHER": "untouched"}
        original = dict(inherited)
        env = controller.child_environment(Path("/tmp/echo root"), inherited)
        self.assertEqual(inherited, original)
        self.assertTrue(env["PYTHONPATH"].startswith(str(Path("/tmp/echo root").resolve()) + os.pathsep))
        self.assertIn("existing path with spaces", env["PYTHONPATH"])
        self.assertEqual(env["PATH"], "parent-path")
        self.assertEqual(env["PYTHONUTF8"], "1")
        self.assertEqual(env["HF_HUB_OFFLINE"], "1")

    def test_fingerprint_tracks_media_prompt_source_and_model_state(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            image, audio, model, source = [root / name for name in ("image", "audio", "weight", "src.py")]
            image.write_bytes(b"image-a")
            audio.write_bytes(b"audio-a")
            model.write_bytes(b"weights-a")
            source.write_text("source-a", encoding="utf-8")
            base, _ = controller.build_job_fingerprint(image, audio, controller.PROFILES["F1"], 81, "calm", [model], [source])
            changed_prompt, _ = controller.build_job_fingerprint(image, audio, controller.PROFILES["F1"], 81, "animated", [model], [source])
            source.write_text("source-b", encoding="utf-8")
            changed_source, _ = controller.build_job_fingerprint(image, audio, controller.PROFILES["F1"], 81, "calm", [model], [source])
            model.write_bytes(b"weights-b")
            changed_model, _ = controller.build_job_fingerprint(image, audio, controller.PROFILES["F1"], 81, "calm", [model], [source])
            self.assertEqual(len({base, changed_prompt, changed_source, changed_model}), 4)

    def test_download_uses_sha_and_atomic_destination(self):
        content = b"small verified model payload"
        asset = controller.Asset("test/repo", "a" * 40, "weights.bin", len(content), hashlib.sha256(content).hexdigest(), "models/test.bin")
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / "model.bin"
            calls = []

            def opener(request, timeout):
                calls.append((request, timeout))
                return FakeResponse(content)

            result = controller.download_asset(asset, destination, opener=opener, progress=lambda _text: None)
            self.assertEqual(result, "downloaded")
            self.assertEqual(destination.read_bytes(), content)
            self.assertFalse(destination.with_name("model.bin.part").exists())
            self.assertEqual(calls[0][0].get_header("User-agent"), "EchoMimicV3-test-runner/1.0")
            self.assertEqual(controller.download_asset(asset, destination, opener=opener, progress=lambda _text: None), "reused")

    def test_download_resumes_part_and_rejects_bad_sha_without_replacing_existing(self):
        content = b"verified model bytes" * 7
        split = 12
        asset = controller.Asset("test/repo", "b" * 40, "weights.bin", len(content), hashlib.sha256(content).hexdigest(), "models/test.bin")
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / "model.bin"
            partial = destination.with_name(destination.name + ".part")
            partial.write_bytes(content[:split])
            requests = []

            def opener(request, timeout):
                requests.append(request)
                self.assertEqual(request.get_header("Range"), "bytes={}-".format(split))
                return FakeResponse(content[split:], 206, {"Content-Range": "bytes {}-{}/{}".format(split, len(content) - 1, len(content))})

            controller.download_asset(asset, destination, opener=opener, progress=lambda _text: None)
            self.assertEqual(destination.read_bytes(), content)
            self.assertEqual(len(requests), 1)

            wrong = controller.Asset("test/repo", "c" * 40, "weights.bin", len(content), "0" * 64, "models/test.bin")
            destination.write_bytes(b"keep existing file")
            with self.assertRaisesRegex(RuntimeError, "SHA-256 không khớp"):
                controller.download_asset(wrong, destination, overwrite=True, opener=lambda *_a, **_k: FakeResponse(content), progress=lambda _text: None)
            self.assertEqual(destination.read_bytes(), b"keep existing file")
            self.assertFalse(partial.exists())

    def test_wrong_existing_asset_is_preserved_without_overwrite(self):
        payload = b"expected"
        asset = controller.Asset("repo", "d" * 40, "file", len(payload), hashlib.sha256(payload).hexdigest(), "x")
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "file"
            target.write_bytes(b"wrong!!")
            with self.assertRaisesRegex(ValueError, "giữ nguyên file"):
                controller.download_asset(asset, target, progress=lambda _text: None)
            self.assertEqual(target.read_bytes(), b"wrong!!")

    def test_source_pin_and_flash_profile_assets_are_explicit(self):
        self.assertEqual(controller.CODE_PIN, "7e89489ca51c0d008fc1963ec6c03fc5bd0b9397")
        self.assertEqual(len(controller.ASSETS), 12)
        relative = {asset.relative_path for asset in controller.ASSETS}
        self.assertIn("models/echomimicv3-flash-pro/diffusion_pytorch_model.safetensors", relative)
        self.assertNotIn("models/Wan2.1-Fun-V1.1-1.3B-InP/diffusion_pytorch_model.safetensors", relative)

    @unittest.skipUnless(HAS_MEDIA_TOOLS, "FFmpeg/ffprobe chưa có sẵn")
    def test_ffmpeg_padding_and_output_validation(self):
        ffmpeg = _test_tool("FFMPEG", "ffmpeg")
        ffprobe = _test_tool("FFPROBE", "ffprobe")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            image = root / "input.png"
            audio = root / "audio.wav"
            base = root / "base.mp4"
            voiced = root / "voice.mp4"
            subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=red:s=640x480", "-frames:v", "1", str(image)], check=True)
            subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=3.4", "-ac", "1", "-ar", "16000", str(audio)], check=True)
            padded, trimmed = controller.ffmpeg_prepare_inputs(image, audio, root / "stage", controller.PROFILES["F1"], 3.24, ffmpeg)
            staged_summary = controller.summarize_media(controller.probe_media(padded, ffprobe))
            self.assertEqual((staged_summary["video"]["width"], staged_summary["video"]["height"]), (384, 480))
            trimmed_summary = controller.summarize_media(controller.probe_media(trimmed, ffprobe))
            self.assertEqual(trimmed_summary["audio"]["sample_rate"], 16000)
            self.assertEqual(trimmed_summary["audio"]["channels"], 1)
            subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=blue:s=384x480:r=25:d=3.24", "-frames:v", "81", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(base)], check=True)
            subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(base), "-i", str(trimmed), "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-shortest", str(voiced)], check=True)
            expected = {"width": 384, "height": 480, "frames": 81, "fps": 25, "duration": 3.24}
            self.assertIsNone(controller.validate_output_file(base, expected, False, ffprobe)["media"]["audio"])
            self.assertIsNotNone(controller.validate_output_file(voiced, expected, True, ffprobe)["media"]["audio"])

    @unittest.skipUnless(HAS_MEDIA_TOOLS, "FFmpeg/ffprobe chưa có sẵn")
    def test_cache_requires_manifest_hashes_and_valid_media(self):
        ffmpeg = _test_tool("FFMPEG", "ffmpeg")
        ffprobe = _test_tool("FFPROBE", "ffprobe")
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp) / "cache"
            directory.mkdir()
            base = directory / "motion_base.mp4"
            voice = directory / "voice_preview.mp4"
            audio = Path(temp) / "a.wav"
            subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=3.24", "-ac", "1", "-ar", "16000", str(audio)], check=True)
            subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=green:s=384x480:r=25:d=3.24", "-frames:v", "81", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(base)], check=True)
            subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(base), "-i", str(audio), "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-shortest", str(voice)], check=True)
            expected = {"width": 384, "height": 480, "frames": 81, "fps": 25, "duration": 3.24}
            manifest = {
                "status": "complete", "fingerprint": "abc",
                "outputs": {
                    "motion_base": {"sha256": controller.hash_file(base)},
                    "voice_preview": {"sha256": controller.hash_file(voice)},
                },
            }
            controller.write_json_atomic(directory / "run_manifest.json", manifest)
            self.assertTrue(controller.cache_manifest_valid(directory, "abc", expected, ffprobe))
            self.assertFalse(controller.cache_manifest_valid(directory, "changed", expected, ffprobe))
            replacement = Path(temp) / "different_content_same_streams.mp4"
            subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=red:s=384x480:r=25:d=3.24", "-frames:v", "81", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(replacement)], check=True)
            replacement_info = controller.summarize_media(controller.probe_media(replacement, ffprobe))["video"]
            base_info = controller.summarize_media(controller.probe_media(base, ffprobe))["video"]
            fields = ("width", "height", "fps", "frames", "duration")
            self.assertEqual({key: replacement_info[key] for key in fields}, {key: base_info[key] for key in fields})
            replacement.replace(base)
            self.assertFalse(controller.cache_manifest_valid(directory, "abc", expected, ffprobe))
            voice.write_bytes(b"corrupt")
            self.assertFalse(controller.cache_manifest_valid(directory, "abc", expected, ffprobe))

    def test_tee_streams_child_output_to_terminal_and_log(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            log = root / "log file.log"
            env = dict(os.environ)
            code = controller.tee_backend_process([sys.executable, "-c", "print('child alive')"], root, env, log)
            self.assertEqual(code, 0)
            self.assertIn("child alive", log.read_text(encoding="utf-8"))

    def test_tee_interrupt_terminates_child_and_keeps_log(self):
        class FakeProcess:
            def __init__(self):
                self.stdout = mock.Mock()
                self.stdout.readline.side_effect = [b"render started\n", KeyboardInterrupt]
                self.terminated = False
                self.wait_calls = []

            def poll(self):
                return None

            def terminate(self):
                self.terminated = True

            def wait(self, timeout=None):
                self.wait_calls.append(timeout)
                return 143

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            log = root / "interrupted.log"
            child = FakeProcess()
            with mock.patch.object(controller.subprocess, "Popen", return_value=child):
                with self.assertRaises(KeyboardInterrupt):
                    controller.tee_backend_process(["fake-worker"], root, dict(os.environ), log)
            self.assertTrue(child.terminated)
            self.assertEqual(child.wait_calls, [10])
            child.stdout.close.assert_called_once()
            text = log.read_text(encoding="utf-8")
            self.assertIn("render started", text)
            self.assertIn("preserving work directory/log", text)

    @unittest.skipUnless(HAS_MEDIA_TOOLS, "FFmpeg/ffprobe chưa có sẵn")
    def test_benchmark_renders_two_fresh_outputs_without_image_b(self):
        ffmpeg = _test_tool("FFMPEG", "ffmpeg")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            echo_root = root / "Echo source with spaces"
            (echo_root / "config").mkdir(parents=True)
            (echo_root / "src").mkdir()
            (echo_root / "infer_flash.py").write_text("source", encoding="utf-8")
            source_signature = echo_root / "src" / "module.py"
            source_signature.write_text("module", encoding="utf-8")
            model_signature = root / "flash weights.bin"
            model_signature.write_bytes(b"fake pinned weights")
            image = root / "portrait input.png"
            audio = root / "speech input.wav"
            subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=red:s=384x480", "-frames:v", "1", str(image)], check=True)
            subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=330:duration=3.4", "-ac", "1", "-ar", "16000", str(audio)], check=True)
            args = controller.make_parser().parse_args([
                "benchmark", "--echo-dir", str(echo_root), "--echo-python", sys.executable,
                "--image", str(image), "--audio", str(audio), "--duration", "3.24",
                "--profile", "F1", "--output-dir", str(root / "output"),
            ])
            plans = []
            staged_input_bytes = []

            def fake_backend(command, cwd, env, log_path):
                plan = json.loads(Path(command[-1]).read_text(encoding="utf-8"))
                plans.append(plan)
                staged_input_bytes.append([
                    (Path(item["image"]).read_bytes(), Path(item["audio"]).read_bytes())
                    for item in plan["inputs"]
                ])
                backend_out = Path(plan["outputs_dir"])
                backend_out.mkdir()
                items = []
                for index, input_item in enumerate(plan["inputs"], 1):
                    base = backend_out / "motion_base_{}.mp4".format(index)
                    voice = backend_out / "voice_preview_{}.mp4".format(index)
                    subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=blue:s=384x480:r=25:d=3.24", "-frames:v", "81", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(base)], check=True)
                    subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(base), "-i", input_item["audio"], "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-shortest", str(voice)], check=True)
                    items.append({"motion_base": str(base), "voice_preview": str(voice), "timing": {"pipeline_call_seconds": float(index)}})
                (backend_out / "backend_result.json").write_text(json.dumps({"status": "complete", "items": items}), encoding="utf-8")
                return 0

            with mock.patch.object(controller, "source_checkout_status", return_value=(True, "pinned")), \
                 mock.patch.object(controller, "missing_model_assets", return_value=[]), \
                 mock.patch.object(controller, "_model_files_for_fingerprint", return_value=[model_signature]), \
                 mock.patch.object(controller, "_source_files_for_fingerprint", return_value=[source_signature]), \
                 mock.patch.object(controller, "tee_backend_process", side_effect=fake_backend):
                self.assertEqual(controller.run_job(args, echo_root, Path(sys.executable), benchmark=True), 0)

            self.assertEqual(len(plans), 1)
            self.assertEqual(len(plans[0]["inputs"]), 2)
            self.assertEqual(staged_input_bytes[0][0][0], staged_input_bytes[0][1][0])
            self.assertEqual(staged_input_bytes[0][0][1], staged_input_bytes[0][1][1])
            self.assertEqual(plans[0]["ffmpeg"], ffmpeg)
            report_path = next((root / "output").glob("benchmark_f1_*/benchmark_report.json"))
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["comparison"], "same image rendered twice in one fresh process")
            self.assertEqual(len(report["items"]), 2)
            for item in report["items"]:
                self.assertTrue(Path(item["motion_base"]["path"]).is_file())
                self.assertTrue(Path(item["voice_preview"]["path"]).is_file())


class BackendContractTests(unittest.TestCase):
    class Parameter:
        def __init__(self, shape, device="cpu"):
            self.shape = shape
            self.device = type("Device", (), {"type": device})()

    class Model:
        def __init__(self, params):
            self.params = params

        def named_parameters(self):
            return iter(self.params.items())

    def test_flash_header_coverage_rejects_missing_or_wrong_weights(self):
        model = self.Model({"layer.weight": self.Parameter((2, 3)), "bias": self.Parameter((3,))})
        backend.validate_parameter_coverage(model, {"layer.weight": (2, 3), "bias": (3,)})
        with self.assertRaisesRegex(RuntimeError, "missing learned parameters"):
            backend.validate_parameter_coverage(model, {"layer.weight": (2, 3)})
        with self.assertRaisesRegex(RuntimeError, "shape mismatch"):
            backend.validate_parameter_coverage(model, {"layer.weight": (3, 2), "bias": (3,)})
        meta_model = self.Model({"layer.weight": self.Parameter((2, 3), "meta")})
        with self.assertRaisesRegex(RuntimeError, "meta tensor remains"):
            backend.validate_parameter_coverage(meta_model, {"layer.weight": (2, 3)})

    def test_adapter_uses_flash_checkpoint_and_cpu_offload_without_cuda_to(self):
        source = (REPO_ROOT / "scripts" / "echo_flash_backend.py").read_text(encoding="utf-8")
        loader = source.split("def _load_models(", 1)[1].split("\ndef _sync_cuda", 1)[0]
        self.assertIn('model_root / "echomimicv3-flash-pro"', loader)
        self.assertIn("WanTransformerAudioMask3DModel.from_pretrained", loader)
        self.assertIn("pipeline.enable_sequential_cpu_offload(device=device)", loader)
        self.assertEqual(loader.count("enable_sequential_cpu_offload"), 1)
        self.assertEqual(source.count("pipeline.enable_sequential_cpu_offload"), 1)
        execution = source.split("def execute_plan(", 1)[1].split("\ndef make_parser", 1)[0]
        self.assertNotIn("pipeline.enable_sequential_cpu_offload", execution)
        self.assertNotIn("pipeline.to(device", loader)
        self.assertNotIn("enable_teacache", loader)
        self.assertNotIn("enable_riflex", loader)


if __name__ == "__main__":
    unittest.main()
