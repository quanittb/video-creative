#!/usr/bin/env python3
"""Check and install the pinned EchoMimic V3 Flash and MuseTalk model assets.

This standard-library CLI is intended to be called by a local UI as a subprocess.
It never installs Python packages, clones source code, imports CUDA/Torch, or starts
inference. ``status --json`` emits one JSON document. ``download --jsonl`` emits
versioned JSON lines with event names ``asset_started``, ``asset_progress``,
``asset_verified``, ``asset_failed``, ``asset_cancelled`` and a final
``download_completed`` summary. Every event has ``schema_version: 1``; progress
events contain byte counters suitable for a UI progress bar.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

import echo_flash_windows as echo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ManagedAsset:
    asset_id: str
    component: str
    repo: str
    revision: str
    filename: str
    size: int
    sha256: str
    relative_path: str

    def as_downloader_asset(self) -> echo.Asset:
        return echo.Asset(
            self.repo,
            self.revision,
            self.filename,
            self.size,
            self.sha256,
            self.relative_path,
        )


def _asset_id(component: str, relative_path: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", relative_path).strip("_").lower()
    return f"{component}_{normalized}"


def _musetalk_asset(repo: str, revision: str, filename: str, size: int, sha256: str, relative_path: str) -> ManagedAsset:
    return ManagedAsset(
        _asset_id("musetalk", relative_path), "musetalk", repo, revision,
        filename, size, sha256, relative_path,
    )


MUSE_TALK_ASSETS = (
    _musetalk_asset(
        "yzd-v/DWPose", "1a7144101628d69ee7a3768d1ee3a094070dc388",
        "dw-ll_ucoco_384.pth", 406878486,
        "0d9408b13cd863c4e95a149dd31232f88f2a12aa6cf8964ed74d7d97748c7a07",
        "models/dwpose/dw-ll_ucoco_384.pth",
    ),
    _musetalk_asset(
        "ManyOtherFunctions/face-parse-bisent", "0073b233a5a3c4b1377d4dbf49245017938a72b5",
        "79999_iter.pth", 53289463,
        "468e13ca13a9b43cc0881a9f99083a430e9c0a38abd935431d1c28ee94b26567",
        "models/face-parse-bisent/79999_iter.pth",
    ),
    _musetalk_asset(
        "ManyOtherFunctions/face-parse-bisent", "0073b233a5a3c4b1377d4dbf49245017938a72b5",
        "resnet18-5c106cde.pth", 46827520,
        "5c106cde386e87d4033832f2996f5493238eda96ccf559d1d62760c4de0613f8",
        "models/face-parse-bisent/resnet18-5c106cde.pth",
    ),
    _musetalk_asset(
        "openai/whisper-tiny", "169d4a4341b33bc18d8881c4b69c2e104e1cc0af",
        "config.json", 1983,
        "ffdccec4f3211f4c63310f2b7098f309fe70f3952cedc5e4d11e43f5b2379b98",
        "models/whisper/config.json",
    ),
    _musetalk_asset(
        "openai/whisper-tiny", "169d4a4341b33bc18d8881c4b69c2e104e1cc0af",
        "preprocessor_config.json", 184990,
        "9b5cd03a36fbb8a627c64d98a5b5b126ead95a77720723944487311f0110b666",
        "models/whisper/preprocessor_config.json",
    ),
    _musetalk_asset(
        "openai/whisper-tiny", "169d4a4341b33bc18d8881c4b69c2e104e1cc0af",
        "pytorch_model.bin", 151095027,
        "9607f98a2b22d9e229ae43c52ecea79dcede9e0c5cfae67e8da6eda86d8aac1d",
        "models/whisper/pytorch_model.bin",
    ),
    _musetalk_asset(
        "stabilityai/sd-vae-ft-mse", "31f26fdeee1355a5c34592e401dd41e45d25a493",
        "config.json", 547,
        "92d3dfb746fca211a2c9e019e285f8597412211728dce3c5bcf4eda0f2d62e7e",
        "models/sd-vae/config.json",
    ),
    _musetalk_asset(
        "stabilityai/sd-vae-ft-mse", "31f26fdeee1355a5c34592e401dd41e45d25a493",
        "diffusion_pytorch_model.bin", 334707217,
        "1b4889b6b1d4ce7ae320a02dedaeff1780ad77d415ea0d744b476155c6377ddc",
        "models/sd-vae/diffusion_pytorch_model.bin",
    ),
    _musetalk_asset(
        "TMElyralab/MuseTalk", "2bcb936e2fddb4d86db4c62fd45b387d0c061571",
        "musetalkV15/unet.pth", 3400074924,
        "7ebf6c98c181e20838e4c0054e96e944ac60d5d692cc01db42839fe11b787007",
        "models/musetalkV15/unet.pth",
    ),
    _musetalk_asset(
        "TMElyralab/MuseTalk", "2bcb936e2fddb4d86db4c62fd45b387d0c061571",
        "musetalk/musetalk.json", 748,
        "5b6923aee04d71692e0e9846c471e0a4ea07a4f686d39545e472bd4ba17e1b47",
        "models/musetalkV15/musetalk.json",
    ),
)


def echo_assets() -> tuple[ManagedAsset, ...]:
    """Adapt the existing pinned Echo catalog without duplicating its hashes."""
    return tuple(
        ManagedAsset(
            _asset_id("echo", item.relative_path), "echo", item.repo,
            item.revision, item.filename, item.size, item.sha256,
            item.relative_path,
        )
        for item in echo.ASSETS
    )


def all_assets() -> tuple[ManagedAsset, ...]:
    return echo_assets() + MUSE_TALK_ASSETS


def discover_musetalk_paths() -> tuple[Path | None, Path | None]:
    try:
        # The current runner's finder uses only standard-library imports and
        # carries the project's known machine/component locations.
        import importlib.util

        runner_path = PROJECT_ROOT / "runners" / "lipsync_runner.py"
        spec = importlib.util.spec_from_file_location("vcs_model_manager_runner_paths", runner_path)
        if spec is not None and spec.loader is not None:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            root, python = module.find_musetalk_paths()
            return (
                Path(root).expanduser().resolve() if root is not None else None,
                Path(python).expanduser().resolve() if python is not None else None,
            )
    except Exception:
        pass
    return None, None


def _resolve_roots(
    echo_dir: str | Path | None,
    musetalk_dir: str | Path | None,
    discovered_musetalk_root: Path | None = None,
) -> dict[str, Path]:
    echo_root = Path(echo_dir).expanduser().resolve() if echo_dir else echo.default_echo_root().resolve()
    muse_override = musetalk_dir or os.environ.get("VCS_MUSETALK_DIR")
    if muse_override:
        muse_root = Path(muse_override).expanduser().resolve()
    else:
        muse_root = discovered_musetalk_root.resolve() if discovered_musetalk_root else (PROJECT_ROOT / "musetalk").resolve()
    return {"echo": echo_root, "musetalk": muse_root}


def _runtime_candidates(component: str, root: Path) -> Iterable[Path]:
    if component == "echo":
        names = (
            "venv/Scripts/python.exe", ".venv/Scripts/python.exe", "env/Scripts/python.exe", "env_venv/Scripts/python.exe",
            "venv/bin/python", ".venv/bin/python", "env/bin/python", "env_venv/bin/python",
        )
        return (root / name for name in names)
    appdata = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "Prostudio" / "components"
    names = (
        "musetalk-venv/Scripts/python.exe", "venv/Scripts/python.exe", ".venv/Scripts/python.exe",
        "env_venv/Scripts/python.exe", "musetalk-venv/bin/python", "venv/bin/python",
    )
    candidates = [root / name for name in names]
    candidates.extend((appdata / "musetalk-venv/Scripts/python.exe", appdata / "py-env/Scripts/python.exe"))
    # The existing MuseTalk runner falls back to the Python launching the
    # pipeline when no dedicated venv is found.
    candidates.append(Path(sys.executable))
    return candidates


def _source_status(component: str, root: Path) -> dict[str, Any]:
    if component == "echo":
        required = (
            root / "infer_flash.py",
            root / "config" / "config.yaml",
            root / "src" / "pipeline_wan_fun_inpaint_audio_2512.py",
        )
    else:
        required = (
            root / "scripts" / "realtime_inference.py",
            root / "musetalk" / "utils" / "face_parsing.py",
        )
    missing = [str(path) for path in required if not path.is_file()]
    revision: dict[str, Any] = {"status": "not_applicable", "actual": None, "expected": None}
    if not missing:
        try:
            result = subprocess.run(
                ["git", "-C", str(root), "rev-parse", "HEAD"],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
                errors="replace", timeout=5, check=False,
            )
            actual = result.stdout.strip() if result.returncode == 0 else None
            expected = echo.CODE_PIN if component == "echo" else None
            if component == "echo":
                revision_status = "match" if actual == expected else "mismatch" if actual else "unverified"
            else:
                revision_status = "reported" if actual else "unverified"
            revision = {"status": revision_status, "actual": actual, "expected": expected}
        except (OSError, subprocess.TimeoutExpired):
            revision = {
                "status": "unverified",
                "actual": None,
                "expected": echo.CODE_PIN if component == "echo" else None,
            }
    status = "missing" if missing else "ready"
    if component == "echo" and not missing and revision["status"] == "mismatch":
        status = "revision_mismatch"
    elif component == "echo" and not missing and revision["status"] == "unverified":
        status = "unverified"
    return {
        "status": status,
        "path": str(root),
        "required_files": [str(path) for path in required],
        "missing_files": missing,
        "revision": revision,
    }


def _asset_status(asset: ManagedAsset, component_root: Path, verify_sha: bool = False) -> dict[str, Any]:
    target = component_root / Path(asset.relative_path)
    partial = target.with_name(target.name + ".part")
    expected_hash = asset.sha256.lower()
    item: dict[str, Any] = {
        "asset_id": asset.asset_id,
        "component": asset.component,
        "path": str(target),
        "expected_bytes": asset.size,
        "actual_bytes": None,
        "expected_sha256": expected_hash,
        "actual_sha256": None,
        "hash_status": "not_checked",
        "integrity_status": "not_checked",
        "presence_status": "missing",
        "partial_path": str(partial),
        "partial_bytes": partial.stat().st_size if partial.is_file() else 0,
        "status": "missing",
    }
    if target.is_file():
        size = target.stat().st_size
        item["actual_bytes"] = size
        item["presence_status"] = "present" if size == asset.size else "size_mismatch"
        if size != asset.size:
            item["status"] = "size_mismatch"
        else:
            item["status"] = "ready"
        if verify_sha:
            item["actual_sha256"] = echo.sha256_file(target)
            item["hash_status"] = "match" if item["actual_sha256"] == expected_hash else "mismatch"
            item["integrity_status"] = item["hash_status"]
            if size == asset.size and item["hash_status"] != "match":
                item["status"] = "hash_mismatch"
    elif partial.is_file():
        item["status"] = "partial"
        item["presence_status"] = "partial"
        item["actual_bytes"] = item["partial_bytes"]
        item["hash_status"] = "not_applicable_partial"
        item["integrity_status"] = "not_applicable_partial"
    return item


def build_status(
    echo_dir: str | Path | None = None,
    musetalk_dir: str | Path | None = None,
    verify_sha: bool = False,
) -> dict[str, Any]:
    discovered_musetalk_root, discovered_musetalk_python = discover_musetalk_paths()
    roots = _resolve_roots(echo_dir, musetalk_dir, discovered_musetalk_root)
    components = {}
    for component in ("echo", "musetalk"):
        root = roots[component]
        assets = echo_assets() if component == "echo" else MUSE_TALK_ASSETS
        discovered_runtime = discovered_musetalk_python if component == "musetalk" else None
        runtime = discovered_runtime if discovered_runtime and discovered_runtime.is_file() else next(
            (path for path in _runtime_candidates(component, root) if path.is_file()), None
        )
        asset_statuses = [_asset_status(asset, root, verify_sha=verify_sha) for asset in assets]
        components[component] = {
            "directory": str(root),
            "source": _source_status(component, root),
            "runtime": {
                "status": "ready" if runtime else "missing",
                "path": str(runtime.resolve()) if runtime else None,
                "validation": "interpreter path presence only; Python packages and CUDA are not checked",
            },
            "assets": asset_statuses,
            "assets_ready": sum(asset["status"] == "ready" for asset in asset_statuses),
            "assets_total": len(asset_statuses),
        }
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "command": "status",
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "components": components,
        "hash_verification": "sha256" if verify_sha else "size_only",
        "install_scope": "model assets only; Python environments and source checkouts are not installed by this command",
    }


class EventWriter:
    def __init__(self, jsonl: bool) -> None:
        self.jsonl = jsonl

    def emit(self, event: str, **payload: Any) -> None:
        record = {"schema_version": MANIFEST_SCHEMA_VERSION, "event": event, **payload}
        if self.jsonl:
            sys.stdout.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
            sys.stdout.flush()
            return
        if event == "asset_progress":
            received = payload.get("bytes_received", 0)
            total = payload.get("bytes_total", 0)
            percent = 100.0 * received / total if total else 0.0
            print(f"  {payload.get('asset_id')}: {percent:.1f}% ({received}/{total} bytes)")
        elif event == "asset_started":
            print(f"[{payload.get('asset_id')}] {payload.get('action')}: {payload.get('path')}")
        elif event == "asset_verified":
            print(f"Đã xác minh model {payload.get('asset_id')} ({payload.get('result')}).")
        elif event == "asset_failed":
            print(f"Lỗi model {payload.get('asset_id')}: {payload.get('error')}")
        elif event == "asset_cancelled":
            print(f"Đã hủy model {payload.get('asset_id')}; file .part được giữ để tiếp tục.")
        elif event == "download_completed":
            print(f"Download kết thúc: {payload.get('status')}; thành công {payload.get('succeeded')}, lỗi {len(payload.get('failed', []))}.")


def _emit_status(status: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return
    for component, info in status["components"].items():
        print(f"{component}: {info['directory']}")
        print(f"  Source: {info['source']['status']}; runtime: {info['runtime']['status']}")
        counts: dict[str, int] = {}
        for asset in info["assets"]:
            counts[asset["status"]] = counts.get(asset["status"], 0) + 1
        summary = ", ".join(f"{key}={value}" for key, value in sorted(counts.items())) or "không có asset"
        print(f"  Assets: {info['assets_ready']}/{info['assets_total']} sẵn sàng ({summary})")


def _selected_assets(component: str, asset_id: str | None) -> tuple[ManagedAsset, ...]:
    if component == "echo":
        candidates = echo_assets()
    elif component == "musetalk":
        candidates = MUSE_TALK_ASSETS
    elif component == "all":
        candidates = all_assets()
    else:
        raise ValueError(f"Component không hợp lệ: {component}")
    if asset_id is None:
        return candidates
    selected = tuple(asset for asset in candidates if asset.asset_id == asset_id)
    if not selected:
        raise ValueError(f"Không tìm thấy asset ID '{asset_id}' trong component '{component}'.")
    return selected


def download_models(
    component: str,
    echo_dir: str | Path | None = None,
    musetalk_dir: str | Path | None = None,
    asset_id: str | None = None,
    repair: bool = False,
    events: EventWriter | None = None,
    downloader: Any = None,
) -> int:
    writer = events or EventWriter(jsonl=False)
    download = downloader or echo.download_asset
    selected = _selected_assets(component, asset_id)
    discovered_musetalk_root, _discovered_musetalk_python = discover_musetalk_paths()
    roots = _resolve_roots(echo_dir, musetalk_dir, discovered_musetalk_root)
    failed: list[dict[str, str]] = []
    succeeded = 0
    for asset_index, asset in enumerate(selected, 1):
        try:
            root = roots[asset.component]
            target = root / Path(asset.relative_path)
            state = _asset_status(asset, root)
            action = "verify" if state["status"] == "ready" else "repair" if state["status"] in ("size_mismatch", "hash_mismatch") else "resume" if state["status"] == "partial" else "download"
            writer.emit(
                "asset_started", component=asset.component, asset_id=asset.asset_id,
                path=str(target), action=action, bytes_received=state["partial_bytes"],
                bytes_total=asset.size, asset_index=asset_index,
                asset_count=len(selected),
            )
            if state["status"] == "ready":
                state = _asset_status(asset, root, verify_sha=True)
                if state["status"] == "ready":
                    succeeded += 1
                    writer.emit("asset_verified", component=asset.component, asset_id=asset.asset_id, path=str(target), result="reused", actual_bytes=state["actual_bytes"], sha256=state["actual_sha256"])
                    continue
            if state["status"] in ("size_mismatch", "hash_mismatch") and not repair:
                raise ValueError(
                    f"Asset hiện có bị {state['status']}; giữ nguyên file. Chỉ dùng --repair nếu muốn tải bản đã xác minh và thay thế nguyên tử: {target}"
                )

            def on_progress(received: int, total: int) -> None:
                writer.emit(
                    "asset_progress", component=asset.component, asset_id=asset.asset_id,
                    path=str(target), bytes_received=received, bytes_total=total,
                    asset_index=asset_index, asset_count=len(selected),
                )

            outcome = download(
                asset.as_downloader_asset(), target,
                overwrite=repair, progress=lambda _text: None,
                progress_callback=on_progress,
            )
            # The shared downloader only returns after it has verified byte
            # count and SHA-256, then atomically replaced the target.
            if not target.is_file() or target.stat().st_size != asset.size:
                raise RuntimeError("Asset sau khi tải chưa đúng kích thước mong đợi.")
            succeeded += 1
            writer.emit(
                "asset_verified", component=asset.component, asset_id=asset.asset_id,
                path=str(target), result=outcome, actual_bytes=asset.size,
                sha256=asset.sha256,
            )
        except KeyboardInterrupt:
            writer.emit("asset_cancelled", component=asset.component, asset_id=asset.asset_id)
            writer.emit("download_completed", status="cancelled", succeeded=succeeded, failed=failed)
            return 130
        except Exception as exc:
            failed.append({"asset_id": asset.asset_id, "error": str(exc)})
            writer.emit("asset_failed", component=asset.component, asset_id=asset.asset_id, error=str(exc))
    writer.emit("download_completed", status="ok" if not failed else "incomplete", succeeded=succeeded, failed=failed)
    return 0 if not failed else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Kiểm tra/tải model EchoMimic V3 Flash và MuseTalk; không cài Python/dependency hoặc chạy GPU.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    status_parser = subparsers.add_parser("status", help="Đọc trạng thái source, runtime và từng model asset")
    status_parser.add_argument("--echo-dir", help="Thư mục EchoMimicV3, mặc định ~/Downloads/EchoMimicV3")
    status_parser.add_argument("--musetalk-dir", help="Thư mục MuseTalk; mặc định dò theo runner/components")
    status_parser.add_argument("--json", action="store_true", help="Chỉ xuất một JSON document machine-readable")
    status_parser.add_argument("--verify-sha", action="store_true", help="Băm đầy đủ các file model; có thể đọc hàng chục GB, mặc định chỉ kiểm tra presence/size")
    download_parser = subparsers.add_parser("download", help="Tải model thiếu, tiếp tục .part hoặc sửa file hỏng")
    download_parser.add_argument("--component", choices=("echo", "musetalk", "all"), required=True)
    download_parser.add_argument("--asset", dest="asset_id", help="Chỉ xử lý một asset ID ổn định (xem status --json)")
    download_parser.add_argument("--echo-dir", help="Override thư mục EchoMimicV3")
    download_parser.add_argument("--musetalk-dir", help="Override thư mục MuseTalk")
    download_parser.add_argument("--repair", action="store_true", help="Cho phép thay file đích sai size/hash sau khi tải và xác minh file staging")
    download_parser.add_argument("--jsonl", action="store_true", help="Xuất event JSON Lines schema_version=1")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "status":
            _emit_status(build_status(args.echo_dir, args.musetalk_dir, verify_sha=args.verify_sha), args.json)
            return 0
        return download_models(
            args.component,
            echo_dir=args.echo_dir,
            musetalk_dir=args.musetalk_dir,
            asset_id=args.asset_id,
            repair=args.repair,
            events=EventWriter(args.jsonl),
        )
    except Exception as exc:
        if args.command == "download" and args.jsonl:
            print(json.dumps({"schema_version": MANIFEST_SCHEMA_VERSION, "event": "download_completed", "status": "error", "succeeded": 0, "failed": [{"asset_id": args.asset_id or "", "error": str(exc)}]}, ensure_ascii=False, separators=(",", ":")))
        else:
            print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
