"""Persistent Job Manager and Batch Automation Engine for Video Creative Studio.

Manages persistent queue in config/jobs.json and runs sequential worker execution
to protect the RTX 3060 12GB VRAM from out-of-memory errors.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import signal
import subprocess
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure standard UTF-8 stream handling
if sys.platform == "win32":
    try:
        if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
CONFIG_DIR = ROOT_DIR / "config"
JOBS_FILE = CONFIG_DIR / "jobs.json"
OUTPUT_DIR = ROOT_DIR / "output"


@dataclass
class JobParams:
    name: str = "Untitled Render"
    char: str = "office"
    source: Optional[str] = None
    driving: Optional[str] = None
    script: Optional[str] = None
    audio: Optional[str] = None
    voice: str = "vi-VN-NamMinhNeural"
    voice_provider: str = "edge-tts"
    duration: Optional[float] = None
    fps: int = 25
    multiplier: float = 0.55
    driving_policy: str = "hold"
    motion_mode: str = "off"
    batch_size: int = 2
    offset_ms: int = 0
    output_path: Optional[str] = None
    dry_run: bool = False


@dataclass
class RenderJob:
    id: str = field(default_factory=lambda: f"vcs_{uuid.uuid4().hex[:8]}")
    name: str = "Video Render"
    status: str = "queued"  # queued, running, completed, failed, cancelled
    progress: float = 0.0
    stage: str = "idle"
    message: str = "Chờ trong hàng đợi..."
    params: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    output_file: Optional[str] = None
    error: Optional[str] = None
    log_tail: List[str] = field(default_factory=list)


class JobStore:
    """Thread-safe and process-safe JSON persistence for jobs."""

    def __init__(self, storage_path: Path = JOBS_FILE):
        self.storage_path = storage_path
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.storage_path.is_file():
            self._save([])

    def _load(self) -> List[Dict[str, Any]]:
        try:
            if self.storage_path.is_file():
                raw = self.storage_path.read_text(encoding="utf-8").strip()
                if raw:
                    return json.loads(raw)
        except Exception:
            pass
        return []

    def _save(self, jobs: List[Dict[str, Any]]):
        temp_file = self.storage_path.with_suffix(".tmp")
        temp_file.write_text(json.dumps(jobs, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_file.replace(self.storage_path)

    def list_jobs(self) -> List[Dict[str, Any]]:
        return self._load()

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        jobs = self._load()
        for j in jobs:
            if j.get("id") == job_id:
                return j
        return None

    def add_job(self, job: Dict[str, Any]) -> Dict[str, Any]:
        jobs = self._load()
        jobs.insert(0, job)  # Newest first
        self._save(jobs)
        return job

    def update_job(self, job_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        jobs = self._load()
        for idx, j in enumerate(jobs):
            if j.get("id") == job_id:
                jobs[idx].update(updates)
                self._save(jobs)
                return jobs[idx]
        return None

    def delete_job(self, job_id: str) -> bool:
        jobs = self._load()
        filtered = [j for j in jobs if j.get("id") != job_id]
        if len(filtered) != len(jobs):
            self._save(filtered)
            return True
        return False

    def clear_completed(self):
        jobs = self._load()
        active = [j for j in jobs if j.get("status") in {"queued", "running"}]
        self._save(active)


class BatchImporter:
    """Imports batch jobs from CSV or JSON manifests."""

    @staticmethod
    def from_csv(file_path: Path) -> List[Dict[str, Any]]:
        if not file_path.is_file():
            raise FileNotFoundError(f"File không tồn tại: {file_path}")

        jobs = []
        with open(file_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = row.get("name") or row.get("title") or f"Batch Item {len(jobs) + 1}"
                script = row.get("script") or row.get("text") or ""
                char = row.get("char") or row.get("character") or "office"
                voice = row.get("voice") or "vi-VN-NamMinhNeural"
                driving = row.get("driving") or None
                duration = float(row["duration"]) if row.get("duration") else None
                multiplier = float(row["multiplier"]) if row.get("multiplier") else 0.55
                output_name = row.get("output_name") or f"{Path(name).stem}.mp4"
                output_path = f"output/{output_name}" if not output_name.startswith("output/") else output_name
                dry_run = str(row.get("dry_run", "true")).lower() in ("true", "1", "yes")

                job = RenderJob(
                    name=name,
                    params={
                        "name": name,
                        "script": script,
                        "char": char,
                        "voice": voice,
                        "driving": driving,
                        "duration": duration,
                        "multiplier": multiplier,
                        "output": output_path,
                        "dry_run": dry_run,
                    }
                )
                jobs.append(asdict(job))
        return jobs

    @staticmethod
    def from_json(file_path: Path) -> List[Dict[str, Any]]:
        if not file_path.is_file():
            raise FileNotFoundError(f"File không tồn tại: {file_path}")

        raw = json.loads(file_path.read_text(encoding="utf-8"))
        items = raw if isinstance(raw, list) else raw.get("items", raw.get("jobs", []))
        jobs = []
        for item in items:
            name = item.get("name") or f"Batch Item {len(jobs) + 1}"
            job = RenderJob(
                name=name,
                params=item.get("params", item)
            )
            jobs.append(asdict(job))
        return jobs


class SequentialWorker:
    """Pulls jobs from the queue one-by-one to prevent RTX 3060 VRAM OOM."""

    def __init__(self, store: JobStore):
        self.store = store
        self.running = True
        self.current_process: Optional[subprocess.Popen] = None
        self.current_job_id: Optional[str] = None

    def stop(self):
        self.running = False
        if self.current_process and self.current_process.poll() is None:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.current_process.pid)], capture_output=True, creationflags=CREATE_NO_WINDOW)
            else:
                self.current_process.terminate()

    def process_one_job(self, job: Dict[str, Any]) -> bool:
        job_id = job["id"]
        self.current_job_id = job_id
        params = job.get("params", {})

        print(f"\n[Worker] Bắt đầu xử lý Job {job_id}: {job.get('name', '')}", flush=True)
        self.store.update_job(job_id, {
            "status": "running",
            "stage": "starting",
            "progress": 5.0,
            "message": "Đang chuẩn bị render...",
            "started_at": datetime.now().isoformat(),
        })

        bridge_script = ROOT_DIR / "runners" / "studio_bridge.py"
        python_exe = sys.executable

        # Prepare payload
        job_payload = {
            "id": job_id,
            **params,
        }

        cmd = [
            python_exe,
            "-u",
            str(bridge_script),
            "--job-string",
            json.dumps(job_payload, ensure_ascii=False),
        ]

        try:
            self.current_process = subprocess.Popen(
                cmd,
                cwd=str(ROOT_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                encoding="utf-8",
                errors="replace",
                creationflags=CREATE_NO_WINDOW,
            )

            log_buffer: List[str] = []
            output_file = params.get("output")

            for raw_line in self.current_process.stdout:
                line = raw_line.strip()
                if not line:
                    continue

                print(f"[{job_id}] {line}", flush=True)

                # Keep last 50 lines in memory
                log_buffer.append(line)
                if len(log_buffer) > 50:
                    log_buffer.pop(0)

                # Parse event
                if line.startswith("[VCS_EVENT] "):
                    event_json = line[len("[VCS_EVENT] "):]
                    try:
                        event = json.loads(event_json)
                        ev_type = event.get("type")
                        if ev_type == "progress":
                            self.store.update_job(job_id, {
                                "stage": event.get("stage", "running"),
                                "progress": event.get("percent", 10.0),
                                "message": event.get("message", "Đang xử lý..."),
                                "log_tail": log_buffer[-10:],
                            })
                        elif ev_type == "job_completed":
                            output_file = event.get("output") or output_file
                    except Exception:
                        pass

            self.current_process.wait()
            rc = self.current_process.returncode

            if rc == 0:
                print(f"[Worker] ✅ Job {job_id} hoàn tất thành công!", flush=True)
                self.store.update_job(job_id, {
                    "status": "completed",
                    "stage": "done",
                    "progress": 100.0,
                    "message": "Hoàn tất render video.",
                    "completed_at": datetime.now().isoformat(),
                    "output_file": output_file,
                    "log_tail": log_buffer[-10:],
                })
                return True
            else:
                print(f"[Worker] ❌ Job {job_id} thất bại với exit code {rc}", flush=True)
                self.store.update_job(job_id, {
                    "status": "failed",
                    "stage": "error",
                    "error": f"Lỗi thực thi (exit code {rc})",
                    "completed_at": datetime.now().isoformat(),
                    "log_tail": log_buffer[-20:],
                })
                return False

        except Exception as exc:
            print(f"[Worker] ❌ Ngoại lệ khi chạy Job {job_id}: {exc}", flush=True)
            self.store.update_job(job_id, {
                "status": "failed",
                "stage": "exception",
                "error": str(exc),
                "completed_at": datetime.now().isoformat(),
            })
            return False
        finally:
            self.current_process = None
            self.current_job_id = None

    def run_loop(self, once: bool = False):
        """Worker main loop polling for queued jobs."""
        print("[Worker] Vòng lặp sequential queue worker đã kích hoạt...", flush=True)
        while self.running:
            jobs = self.store.list_jobs()
            # Find next queued job (oldest queued first)
            next_job = None
            for j in reversed(jobs):
                if j.get("status") == "queued":
                    next_job = j
                    break

            if next_job:
                self.process_one_job(next_job)
                if once:
                    break
            else:
                if once:
                    print("[Worker] Không có job nào đang chờ trong hàng đợi.", flush=True)
                    break
                time.sleep(2.0)


def main():
    parser = argparse.ArgumentParser(description="VCS Job Manager & Sequential Worker")
    subparsers = parser.add_subparsers(dest="command")

    # list
    subparsers.add_parser("list", help="Liệt kê danh sách tất cả các job")

    # add
    add_parser = subparsers.add_parser("add", help="Thêm một job mới")
    add_parser.add_argument("--name", default="Video Render")
    add_parser.add_argument("--char", default="office")
    add_parser.add_argument("--script", default="")
    add_parser.add_argument("--voice", default="vi-VN-NamMinhNeural")
    add_parser.add_argument("--driving", default=None)
    add_parser.add_argument("--output", default=None)
    add_parser.add_argument("--multiplier", type=float, default=0.55)
    add_parser.add_argument("--dry-run", action="store_true")

    # import-csv
    csv_parser = subparsers.add_parser("import-csv", help="Import danh sách job từ file CSV")
    csv_parser.add_argument("file", help="Đường dẫn file CSV")

    # import-json
    json_parser = subparsers.add_parser("import-json", help="Import danh sách job từ file JSON")
    json_parser.add_argument("file", help="Đường dẫn file JSON")

    # start-worker
    worker_parser = subparsers.add_parser("start-worker", help="Chạy worker xử lý tuần tự hàng đợi")
    worker_parser.add_argument("--once", action="store_true", help="Chạy một lượt rồi dừng")

    # cancel
    cancel_parser = subparsers.add_parser("cancel", help="Hủy một job")
    cancel_parser.add_argument("job_id", help="ID của job")

    # retry
    retry_parser = subparsers.add_parser("retry", help="Thử lại một job đã thất bại")
    retry_parser.add_argument("job_id", help="ID của job")

    # clear
    subparsers.add_parser("clear-completed", help="Xóa các job đã hoàn thành hoặc thất bại")

    args = parser.parse_args()
    store = JobStore()

    if args.command == "list":
        jobs = store.list_jobs()
        print(json.dumps(jobs, ensure_ascii=False, indent=2))
        return 0

    elif args.command == "add":
        out_name = args.output or str(OUTPUT_DIR / f"{Path(args.name).stem}.mp4")
        job = RenderJob(
            name=args.name,
            params={
                "name": args.name,
                "char": args.char,
                "script": args.script,
                "voice": args.voice,
                "driving": args.driving,
                "output": out_name,
                "multiplier": args.multiplier,
                "dry_run": args.dry_run,
            }
        )
        saved = store.add_job(asdict(job))
        print(json.dumps(saved, ensure_ascii=False, indent=2))
        return 0

    elif args.command == "import-csv":
        jobs = BatchImporter.from_csv(Path(args.file))
        for j in jobs:
            store.add_job(j)
        print(f"Đã import thành công {len(jobs)} jobs từ {args.file}")
        return 0

    elif args.command == "import-json":
        jobs = BatchImporter.from_json(Path(args.file))
        for j in jobs:
            store.add_job(j)
        print(f"Đã import thành công {len(jobs)} jobs từ {args.file}")
        return 0

    elif args.command == "start-worker":
        worker = SequentialWorker(store)

        def sig_handler(sig, frame):
            print("\nĐang dừng worker...", flush=True)
            worker.stop()
            sys.exit(0)

        signal.signal(signal.SIGINT, sig_handler)
        signal.signal(signal.SIGTERM, sig_handler)
        worker.run_loop(once=args.once)
        return 0

    elif args.command == "cancel":
        job = store.get_job(args.job_id)
        if not job:
            print(f"Không tìm thấy job: {args.job_id}", file=sys.stderr)
            return 1
        store.update_job(args.job_id, {"status": "cancelled", "message": "Đã hủy bởi người dùng"})
        print(f"Đã hủy job {args.job_id}")
        return 0

    elif args.command == "retry":
        job = store.get_job(args.job_id)
        if not job:
            print(f"Không tìm thấy job: {args.job_id}", file=sys.stderr)
            return 1
        store.update_job(args.job_id, {
            "status": "queued",
            "progress": 0.0,
            "stage": "idle",
            "message": "Đã đưa lại vào hàng đợi",
            "error": None,
        })
        print(f"Đã đưa lại job {args.job_id} vào hàng đợi")
        return 0

    elif args.command == "clear-completed":
        store.clear_completed()
        print("Đã làm sạch các job đã hoàn tất.")
        return 0

    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
