import contextlib
import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import echo_flash_windows as echo
import pipeline_model_manager as manager


class FakeResponse:
    def __init__(self, payload: bytes, status: int = 200, headers: dict | None = None):
        self._stream = io.BytesIO(payload)
        self.status = status
        self.headers = headers or {}

    def read(self, size: int = -1) -> bytes:
        return self._stream.read(size)

    def close(self) -> None:
        self._stream.close()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def tiny_asset(component: str = "musetalk", relative_path: str = "models/test/weights.bin", payload: bytes = b"expected model") -> manager.ManagedAsset:
    return manager.ManagedAsset(
        f"{component}_test_weights", component, "test/repo", "a" * 40,
        "weights.bin", len(payload), hashlib.sha256(payload).hexdigest(), relative_path,
    )


class PipelineModelManagerTests(unittest.TestCase):
    def test_asset_status_reports_missing_partial_valid_and_corrupt_files(self):
        asset = tiny_asset()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / Path(asset.relative_path)

            self.assertEqual(manager._asset_status(asset, root)["status"], "missing")
            target.parent.mkdir(parents=True)
            partial = target.with_name(target.name + ".part")
            partial.write_bytes(b"expected")
            partial_status = manager._asset_status(asset, root)
            self.assertEqual(partial_status["status"], "partial")
            self.assertEqual(partial_status["actual_bytes"], 8)
            self.assertEqual(partial_status["hash_status"], "not_applicable_partial")

            partial.unlink()
            target.write_bytes(b"expected model")
            ready = manager._asset_status(asset, root, verify_sha=True)
            self.assertEqual(ready["status"], "ready")
            self.assertEqual(ready["hash_status"], "match")
            self.assertEqual(ready["actual_sha256"], asset.sha256)

            target.write_bytes(b"tampered model")
            corrupt = manager._asset_status(asset, root, verify_sha=True)
            self.assertEqual(corrupt["status"], "hash_mismatch")
            self.assertEqual(corrupt["hash_status"], "mismatch")
            fast_corrupt = manager._asset_status(asset, root)
            self.assertEqual(fast_corrupt["status"], "ready")
            self.assertEqual(fast_corrupt["integrity_status"], "not_checked")
            target.write_bytes(b"short")
            size_mismatch = manager._asset_status(asset, root)
            self.assertEqual(size_mismatch["status"], "size_mismatch")
            self.assertNotEqual(size_mismatch["actual_bytes"], size_mismatch["expected_bytes"])

    def test_status_reports_components_when_roots_are_missing(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fake_runtime = root / "python.exe"
            fake_runtime.write_bytes(b"test")
            with mock.patch.object(manager, "discover_musetalk_paths", return_value=(root / "missing-source", fake_runtime)):
                status = manager.build_status(root / "echo", root / "musetalk")
        self.assertEqual(status["schema_version"], 1)
        self.assertEqual(set(status["components"]), {"echo", "musetalk"})
        self.assertEqual(status["components"]["echo"]["source"]["status"], "missing")
        self.assertEqual(status["components"]["musetalk"]["runtime"]["path"], str(fake_runtime.resolve()))
        self.assertEqual(status["components"]["musetalk"]["source"]["status"], "missing")
        self.assertEqual(status["components"]["echo"]["assets_total"], len(echo.ASSETS))
        self.assertEqual(status["hash_verification"], "size_only")

    def test_fast_status_does_not_hash_and_verify_sha_hashes_present_assets(self):
        asset = tiny_asset()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / Path(asset.relative_path)
            target.parent.mkdir(parents=True)
            target.write_bytes(b"expected model")
            with mock.patch.object(manager.echo, "sha256_file", side_effect=AssertionError("fast status hashed a model")):
                result = manager._asset_status(asset, root)
            self.assertEqual(result["status"], "ready")
            self.assertEqual(result["hash_status"], "not_checked")
            verified = manager._asset_status(asset, root, verify_sha=True)
            self.assertEqual(verified["hash_status"], "match")

            echo_root = root / "echo"
            muse_root = root / "musetalk"
            echo_asset = tiny_asset(component="echo", relative_path="models/test/echo.bin")
            (echo_root / Path(echo_asset.relative_path)).parent.mkdir(parents=True)
            (echo_root / Path(echo_asset.relative_path)).write_bytes(b"expected model")
            with mock.patch.object(echo, "ASSETS", (echo_asset.as_downloader_asset(),)), \
                    mock.patch.object(manager, "MUSE_TALK_ASSETS", (asset,)), \
                    mock.patch.object(manager, "discover_musetalk_paths", return_value=(None, None)), \
                    mock.patch.object(manager.echo, "sha256_file", side_effect=AssertionError("fast status hashed a model")):
                full_fast_status = manager.build_status(echo_root, muse_root)
            self.assertEqual(full_fast_status["hash_verification"], "size_only")
            self.assertEqual(full_fast_status["components"]["echo"]["assets"][0]["integrity_status"], "not_checked")

    def test_discovered_musetalk_runtime_and_vcs_root_are_honored(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            discovered_root = root / "components" / "musetalk"
            runtime = root / "Python310" / "python.exe"
            runtime.parent.mkdir(parents=True)
            runtime.write_bytes(b"python")
            with mock.patch.object(manager, "discover_musetalk_paths", return_value=(discovered_root, runtime)):
                status = manager.build_status(root / "echo", None)
            self.assertEqual(status["components"]["musetalk"]["directory"], str(discovered_root.resolve()))
            self.assertEqual(status["components"]["musetalk"]["runtime"]["path"], str(runtime.resolve()))

            override = root / "explicit-musetalk"
            with mock.patch.dict(manager.os.environ, {"VCS_MUSETALK_DIR": str(override)}):
                self.assertEqual(manager._resolve_roots(None, None, discovered_root)["musetalk"], override.resolve())

    def test_echo_catalog_is_reused_without_copying_hashes(self):
        converted = manager.echo_assets()
        self.assertEqual(len(converted), len(echo.ASSETS))
        for managed, original in zip(converted, echo.ASSETS):
            self.assertEqual(managed.repo, original.repo)
            self.assertEqual(managed.revision, original.revision)
            self.assertEqual(managed.filename, original.filename)
            self.assertEqual(managed.size, original.size)
            self.assertEqual(managed.sha256, original.sha256)
            self.assertEqual(managed.relative_path, original.relative_path)
            self.assertTrue(managed.asset_id.startswith("echo_"))

    def test_musetalk_catalog_keeps_immutable_revision_metadata_and_effective_config_path(self):
        assets = {(asset.repo, asset.filename): asset for asset in manager.MUSE_TALK_ASSETS}
        self.assertEqual(len(assets), 10)
        self.assertEqual(assets[("yzd-v/DWPose", "dw-ll_ucoco_384.pth")].revision, "1a7144101628d69ee7a3768d1ee3a094070dc388")
        self.assertEqual(assets[("TMElyralab/MuseTalk", "musetalkV15/unet.pth")].size, 3400074924)
        config = assets[("TMElyralab/MuseTalk", "musetalk/musetalk.json")]
        self.assertEqual(config.relative_path, "models/musetalkV15/musetalk.json")
        self.assertEqual(
            {key: (asset.size, asset.sha256) for key, asset in assets.items()},
            {
                ("yzd-v/DWPose", "dw-ll_ucoco_384.pth"): (406878486, "0d9408b13cd863c4e95a149dd31232f88f2a12aa6cf8964ed74d7d97748c7a07"),
                ("ManyOtherFunctions/face-parse-bisent", "79999_iter.pth"): (53289463, "468e13ca13a9b43cc0881a9f99083a430e9c0a38abd935431d1c28ee94b26567"),
                ("ManyOtherFunctions/face-parse-bisent", "resnet18-5c106cde.pth"): (46827520, "5c106cde386e87d4033832f2996f5493238eda96ccf559d1d62760c4de0613f8"),
                ("openai/whisper-tiny", "config.json"): (1983, "ffdccec4f3211f4c63310f2b7098f309fe70f3952cedc5e4d11e43f5b2379b98"),
                ("openai/whisper-tiny", "preprocessor_config.json"): (184990, "9b5cd03a36fbb8a627c64d98a5b5b126ead95a77720723944487311f0110b666"),
                ("openai/whisper-tiny", "pytorch_model.bin"): (151095027, "9607f98a2b22d9e229ae43c52ecea79dcede9e0c5cfae67e8da6eda86d8aac1d"),
                ("stabilityai/sd-vae-ft-mse", "config.json"): (547, "92d3dfb746fca211a2c9e019e285f8597412211728dce3c5bcf4eda0f2d62e7e"),
                ("stabilityai/sd-vae-ft-mse", "diffusion_pytorch_model.bin"): (334707217, "1b4889b6b1d4ce7ae320a02dedaeff1780ad77d415ea0d744b476155c6377ddc"),
                ("TMElyralab/MuseTalk", "musetalkV15/unet.pth"): (3400074924, "7ebf6c98c181e20838e4c0054e96e944ac60d5d692cc01db42839fe11b787007"),
                ("TMElyralab/MuseTalk", "musetalk/musetalk.json"): (748, "5b6923aee04d71692e0e9846c471e0a4ea07a4f686d39545e472bd4ba17e1b47"),
            },
        )

    def test_download_resumes_partial_and_emits_versioned_jsonl_progress(self):
        payload = b"complete verified payload"
        asset = tiny_asset(payload=payload)
        split = 9
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / Path(asset.relative_path)
            target.parent.mkdir(parents=True)
            target.with_name(target.name + ".part").write_bytes(payload[:split])
            requests = []

            def opener(request, timeout):
                requests.append(request)
                self.assertEqual(request.get_header("Range"), f"bytes={split}-")
                return FakeResponse(payload[split:], 206, {"Content-Range": f"bytes {split}-{len(payload) - 1}/{len(payload)}"})

            output = io.StringIO()
            with mock.patch.object(manager, "MUSE_TALK_ASSETS", (asset,)), mock.patch.object(echo.urllib.request, "urlopen", side_effect=opener), contextlib.redirect_stdout(output):
                result = manager.download_models(
                    "musetalk", musetalk_dir=root,
                    asset_id=asset.asset_id, events=manager.EventWriter(jsonl=True),
                )
            self.assertEqual(result, 0)
            self.assertEqual(target.read_bytes(), payload)
            self.assertFalse(target.with_name(target.name + ".part").exists())
            self.assertEqual(len(requests), 1)
            events = [json.loads(line) for line in output.getvalue().splitlines()]
            self.assertEqual(events[0]["event"], "asset_started")
            self.assertEqual(events[0]["action"], "resume")
            self.assertEqual(events[0]["asset_index"], 1)
            self.assertEqual(events[0]["asset_count"], 1)
            self.assertTrue(all(item["schema_version"] == 1 for item in events))
            self.assertIn("asset_progress", [item["event"] for item in events])
            self.assertEqual(events[-1]["event"], "download_completed")
            self.assertEqual(events[-1]["status"], "ok")

    def test_corrupt_existing_file_is_preserved_until_explicit_repair(self):
        payload = b"known good model"
        asset = tiny_asset(payload=payload)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / Path(asset.relative_path)
            target.parent.mkdir(parents=True)
            target.write_bytes(b"bad model bytes!")
            events_output = io.StringIO()
            with mock.patch.object(manager, "MUSE_TALK_ASSETS", (asset,)), contextlib.redirect_stdout(events_output):
                refused = manager.download_models(
                    "musetalk", musetalk_dir=root, asset_id=asset.asset_id,
                    events=manager.EventWriter(jsonl=True),
                )
            self.assertEqual(refused, 1)
            self.assertEqual(target.read_bytes(), b"bad model bytes!")
            refused_events = [json.loads(line) for line in events_output.getvalue().splitlines()]
            self.assertEqual(refused_events[1]["event"], "asset_failed")

            with mock.patch.object(manager, "MUSE_TALK_ASSETS", (asset,)), mock.patch.object(echo.urllib.request, "urlopen", return_value=FakeResponse(payload)):
                with contextlib.redirect_stdout(io.StringIO()):
                    repaired = manager.download_models(
                        "musetalk", musetalk_dir=root, asset_id=asset.asset_id,
                        repair=True, events=manager.EventWriter(jsonl=True),
                    )
            self.assertEqual(repaired, 0)
            self.assertEqual(target.read_bytes(), payload)
            self.assertFalse(target.with_name(target.name + ".part").exists())

    def test_failed_download_preserves_existing_file_even_when_repair_enabled(self):
        payload = b"known good model"
        asset = tiny_asset(payload=payload)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / Path(asset.relative_path)
            target.parent.mkdir(parents=True)
            original = b"corrupt original"
            target.write_bytes(original)

            def broken_response(_request, **_kwargs):
                raise OSError("network disconnected")

            output = io.StringIO()
            with mock.patch.object(manager, "MUSE_TALK_ASSETS", (asset,)), mock.patch.object(echo.urllib.request, "urlopen", side_effect=broken_response), contextlib.redirect_stdout(output):
                result = manager.download_models(
                    "musetalk", musetalk_dir=root, asset_id=asset.asset_id,
                    repair=True, events=manager.EventWriter(jsonl=True),
                )
            self.assertEqual(result, 1)
            self.assertEqual(target.read_bytes(), original)
            self.assertEqual([json.loads(line)["event"] for line in output.getvalue().splitlines()][-1], "download_completed")

    def test_full_sized_verified_partial_is_atomically_promoted_without_network(self):
        payload = b"complete verified payload"
        asset = tiny_asset(payload=payload)
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "model.bin"
            target.with_name(target.name + ".part").write_bytes(payload)
            callback_values = []
            result = echo.download_asset(
                asset.as_downloader_asset(), target,
                opener=lambda *_args, **_kwargs: self.fail("network should not be used"),
                progress=lambda _text: None,
                progress_callback=lambda received, total: callback_values.append((received, total)),
            )
            self.assertEqual(result, "downloaded")
            self.assertEqual(target.read_bytes(), payload)
            self.assertFalse(target.with_name(target.name + ".part").exists())
            self.assertEqual(callback_values, [(len(payload), len(payload))])


if __name__ == "__main__":
    unittest.main()
