from __future__ import annotations

import importlib.util
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runners import studio_bridge


class _CompletedProcess:
    def __init__(self, *_args, **_kwargs):
        self.stdout = io.StringIO("Pipeline preflight complete\n")
        self.returncode = 0

    def wait(self):
        return 0


class StudioBridgeTests(unittest.TestCase):
    def test_job_manager_module_imports_for_worker_startup(self):
        module_path = Path(__file__).resolve().parents[1] / "core" / "job_manager.py"
        spec = importlib.util.spec_from_file_location("vcs_job_manager_smoke", module_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        job_manager = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = job_manager
        try:
            spec.loader.exec_module(job_manager)
        finally:
            sys.modules.pop(spec.name, None)
        self.assertTrue(hasattr(job_manager, "SequentialWorker"))

    def setUp(self):
        self.project_root = Path(__file__).resolve().parents[1]
        self.male_image = self.project_root / "assets/characters/nhanvatnam/ChatGPT Image Sep 8, 2026, 08_46_26 AM (1).png"
        self.female_image = self.project_root / "assets/characters/nhanvatnu/ChatGPT Image Sep 14, 2026, 11_35_53 AM (1).png"

    def test_resolver_uses_only_the_two_canonical_sample_personas(self):
        self.assertEqual(studio_bridge._resolve_character_image({"char": "male"}), self.male_image)
        self.assertEqual(studio_bridge._resolve_character_image({"char": "female"}), self.female_image)

    def test_resolver_rejects_image_paths_outside_managed_character_root(self):
        with self.assertRaisesRegex(ValueError, "phải nằm trong assets/characters"):
            studio_bridge._resolve_character_image({"source": str(self.project_root / "README.md")})

    def test_output_name_is_a_safe_mp4_basename(self):
        self.assertEqual(studio_bridge._resolve_output_name("output/campaign-final.mp4"), "campaign-final.mp4")
        self.assertEqual(studio_bridge._resolve_output_name("campaign-final"), "campaign-final.mp4")
        for unsafe in ("../outside.mp4", r"..\outside.mp4", "folder/name.mp4", "name.exe"):
            with self.subTest(unsafe=unsafe), self.assertRaises(ValueError):
                studio_bridge._resolve_output_name(unsafe)

    def test_dry_run_calls_pipeline_preflight_and_never_reports_fake_video(self):
        events = []
        with tempfile.TemporaryDirectory() as temp_dir:
            fake_root = Path(temp_dir)
            scripts = fake_root / "scripts"
            scripts.mkdir()
            (scripts / "test_vertical_ads.py").touch()
            with (
                patch.object(studio_bridge, "ROOT_DIR", fake_root),
                patch.object(studio_bridge, "_resolve_character_image", return_value=self.male_image),
                patch.object(studio_bridge, "_preflight_audio", return_value=(fake_root / "silent.wav", False)),
                patch.object(studio_bridge.subprocess, "Popen", side_effect=_CompletedProcess) as popen,
                patch.object(studio_bridge, "emit_event", side_effect=lambda name, data: events.append((name, data))),
                patch.object(studio_bridge, "emit_log"),
                patch.object(studio_bridge, "emit_progress"),
            ):
                result = studio_bridge.run_pipeline_job({
                    "id": "dry_run_test", "dry_run": True, "output": "output/campaign-final.mp4",
                })

        self.assertEqual(result, 0)
        command = popen.call_args.args[0]
        self.assertIn("dry-run", command)
        self.assertIn("scripts/test_vertical_ads.py", command[2])
        self.assertNotIn("test_option_b_avatar.py", command)
        self.assertEqual(command[command.index("--output-name") + 1], "campaign-final.mp4")
        validated = [data for name, data in events if name == "job_validated"]
        completed = [data for name, data in events if name == "job_completed"]
        self.assertEqual(validated, [{"job_id": "dry_run_test", "status": "validated", "output": None}])
        self.assertEqual(completed, [])

    def test_success_exit_without_verified_video_is_a_failure(self):
        events = []
        with tempfile.TemporaryDirectory() as temp_dir:
            fake_root = Path(temp_dir)
            scripts = fake_root / "scripts"
            scripts.mkdir()
            (scripts / "test_vertical_ads.py").touch()
            with (
                patch.object(studio_bridge, "ROOT_DIR", fake_root),
                patch.object(studio_bridge, "_resolve_character_image", return_value=self.male_image),
                patch.object(studio_bridge, "_resolve_job_audio", return_value=fake_root / "audio.wav"),
                patch.object(studio_bridge.subprocess, "Popen", side_effect=_CompletedProcess),
                patch.object(studio_bridge, "emit_event", side_effect=lambda name, data: events.append((name, data))),
                patch.object(studio_bridge, "emit_log"),
                patch.object(studio_bridge, "emit_progress"),
            ):
                result = studio_bridge.run_pipeline_job({"id": "missing_output", "script": "hello"})

        self.assertEqual(result, 1)
        failures = [data for name, data in events if name == "job_failed"]
        self.assertEqual(len(failures), 1)
        self.assertIn("không tìm thấy video", failures[0]["error"])
        self.assertFalse(any(name == "job_completed" for name, _ in events))


if __name__ == "__main__":
    unittest.main()
