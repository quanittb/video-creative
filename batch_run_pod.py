#!/usr/bin/env python3
"""Batch Production Runner for RunPod Cloud GPU.
Executes a 6-project evaluation suite across 3 character styles (Male, Female, 3D Pixar)
and 3 target languages (Spanish, English, Vietnamese).
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path

# Ensure UTF-8 output
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("PYTHONUTF8", "1")
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR))

from run_pipeline import run_pipeline

BATCH_JOBS = [
    {
        "id": "01_nam_spanish_business",
        "title": "Nam Doanh Nhân - Tiếng Tây Ban Nha (Business / FinTech)",
        "script": "test_samples/batch_scripts/01_nam_spanish_business.txt",
        "char_dir": "assets/characters/nhanvatnam",
        "lang": "es",
        "gender": "male",
    },
    {
        "id": "02_nam_english_tech",
        "title": "Nam Chuyên Gia - Tiếng Anh (AI Tech & Automation)",
        "script": "test_samples/batch_scripts/02_nam_english_tech.txt",
        "char_dir": "assets/characters/nhanvatnam",
        "lang": "en",
        "gender": "male",
    },
    {
        "id": "03_nu_english_productivity",
        "title": "Nữ Chuyên Gia - Tiếng Anh (Productivity & Lifestyle)",
        "script": "test_samples/batch_scripts/03_nu_english_productivity.txt",
        "char_dir": "assets/characters/nhanvatnu",
        "lang": "en",
        "gender": "female",
    },
    {
        "id": "04_nu_vietnamese_startup",
        "title": "Nữ Khởi Nghiệp - Tiếng Việt (Startup & Video Viral)",
        "script": "test_samples/batch_scripts/04_nu_vietnamese_startup.txt",
        "char_dir": "assets/characters/nhanvatnu",
        "lang": "vi",
        "gender": "female",
    },
    {
        "id": "05_hoathinh_english_story",
        "title": "Hoạt Hình 3D Nữ - Tiếng Anh (Pixar Storytelling)",
        "script": "test_samples/batch_scripts/05_hoathinh_english_story.txt",
        "char_dir": "assets/characters/hoathinhnu",
        "lang": "en",
        "gender": "female",
    },
    {
        "id": "06_hoathinh_spanish_story",
        "title": "Hoạt Hình 3D Nữ - Tiếng Tây Ban Nha (Cuentos Infantiles)",
        "script": "test_samples/batch_scripts/06_hoathinh_spanish_story.txt",
        "char_dir": "assets/characters/hoathinhnu",
        "lang": "es",
        "gender": "female",
    },
]


def generate_html_gallery(results: list, out_html: Path):
    """Generate a clean HTML visual dashboard to review all generated videos."""
    cards_html = ""
    for r in results:
        status_badge = '<span style="color:#10b981;font-weight:bold;">✅ Hoàn tất</span>' if r.get("success") else '<span style="color:#ef4444;font-weight:bold;">❌ Lỗi</span>'
        cards_html += f"""
        <div style="background:#1e293b;border-radius:12px;padding:20px;box-shadow:0 4px 6px rgba(0,0,0,0.3);width:320px;display:flex;flex-direction:column;">
            <h3 style="color:#f8fafc;font-size:16px;margin-top:0;margin-bottom:10px;">{r['title']}</h3>
            <p style="color:#94a3b8;font-size:13px;margin:4px 0;">Ngôn ngữ: <b>{r['lang'].upper()}</b> | Giới tính: <b>{r['gender']}</b></p>
            <p style="color:#94a3b8;font-size:13px;margin:4px 0;">Thời gian xử lý: <b>{r.get('elapsed_s', 0):.1f}s</b></p>
            <div style="margin:12px 0;">{status_badge}</div>
            <video controls width="100%" style="border-radius:8px;background:#000;margin-top:auto;" src="{Path(r['output_file']).name}"></video>
            <div style="margin-top:10px;text-align:center;">
                <a href="{Path(r['output_file']).name}" download style="background:#3b82f6;color:#fff;text-decoration:none;padding:8px 16px;border-radius:6px;font-size:13px;display:inline-block;">Tải video MP4</a>
            </div>
        </div>
        """

    full_html = f"""<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <title>Video Creative Studio - Báo Cáo Đánh Giá Chất Lượng Batch Run</title>
</head>
<body style="background:#0f172a;color:#f8fafc;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;margin:0;padding:30px;">
    <div style="max-width:1200px;margin:0 auto;">
        <h1 style="color:#38bdf8;margin-bottom:8px;">🎬 Báo Cáo Đánh Giá Chất Lượng Video (Cloud Pod)</h1>
        <p style="color:#94a3b8;margin-bottom:30px;">Đã hoàn tất bộ 6 video thử nghiệm đa ngôn ngữ (Tây Ban Nha, Anh, Việt) với 3 phong cách nhân vật (Nam thực tế, Nữ thực tế, 3D Pixar).</p>
        <div style="display:flex;flex-wrap:wrap;gap:24px;">
            {cards_html}
        </div>
    </div>
</body>
</html>
"""
    with open(out_html, "w", encoding="utf-8") as f:
        f.write(full_html)


def main():
    print("=" * 70)
    print("🚀 BẮT ĐẦU BATCH PRODUCTION TRÊN RUNPOD (6 DỰ ÁN ĐA NGÔN NGỮ & NHÂN VẬT)")
    print(f"Tổng số dự án: {len(BATCH_JOBS)}")
    print("=" * 70)

    out_dir = ROOT_DIR / "output" / "batch_results"
    out_dir.mkdir(parents=True, exist_ok=True)

    results = []
    total_start = time.time()

    for idx, job in enumerate(BATCH_JOBS, 1):
        print(f"\n[{idx}/{len(BATCH_JOBS)}] >>> Đang xử lý: {job['title']}...")
        job_start = time.time()
        final_video_name = f"{job['id']}.mp4"
        job_out = out_dir / final_video_name

        try:
            run_pipeline(
                script_path=str(ROOT_DIR / job["script"]),
                lang=job["lang"],
                voice_gender=job["gender"],
                char_dir_path=job["char_dir"],
                bg_dir_path="assets/backgrounds",
                output_path=str(job_out.relative_to(ROOT_DIR)),
            )
            elapsed = round(time.time() - job_start, 2)
            results.append({
                "id": job["id"],
                "title": job["title"],
                "lang": job["lang"],
                "gender": job["gender"],
                "output_file": str(job_out),
                "elapsed_s": elapsed,
                "success": True,
            })
            print(f"✅ Hoàn tất dự án [{job['id']}] trong {elapsed}s!")
        except Exception as e:
            print(f"❌ Lỗi khi xử lý dự án [{job['id']}]: {e}")
            results.append({
                "id": job["id"],
                "title": job["title"],
                "lang": job["lang"],
                "gender": job["gender"],
                "output_file": str(job_out),
                "elapsed_s": 0,
                "success": False,
                "error": str(e),
            })

    total_elapsed = round(time.time() - total_start, 2)
    print("\n" + "=" * 70)
    print(f"🎉 HOÀN TẤT TOÀN BỘ BATCH RUN! Tổng thời gian: {total_elapsed}s ({total_elapsed/60:.1f} phút)")
    print(f"📁 Thư mục kết quả: {out_dir}")
    print("=" * 70)

    # Export report and HTML gallery
    report_file = out_dir / "summary_report.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    html_file = out_dir / "index.html"
    generate_html_gallery(results, html_file)
    print(f"🌐 Đã tạo trang đánh giá chất lượng HTML: {html_file}")


if __name__ == "__main__":
    main()
