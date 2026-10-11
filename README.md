# 🎬 Video Creative Studio

Desktop application for creating vertical avatar videos with the **Echo Flash → MuseTalk** pipeline. The Tauri app submits jobs to a local Python bridge; browser preview does not run inference or inspect the host GPU.

## Customer trial requirements

- Use the desktop app on a machine where the Echo Flash and MuseTalk source checkouts, compatible Python environments/dependencies, FFmpeg, and required model files have already been installed and configured.
- **Settings → Model render Echo Flash + MuseTalk** checks and manages catalogued model-weight files only. It does not install the core source checkouts, Python environments, or their packages.
- The current Tauri bundle does not include those runtimes and assets. Building an installer does not by itself produce a self-contained customer-ready installation; prepare the machine/runtime separately before the trial.
- In Studio, select a front-facing sample character or upload a custom image, enter a script and voice, then render. A successful job writes a verified 1080×1920 MP4 under the configured output directory.

The legacy RunPod and batch workflow below is historical material; it is not used by the desktop Studio render button.

---

## ⚡ Current Render Flow

```
[Script]
       │
       ├──► TTS audio (when script is provided)
       │
       ▼
[Echo Flash] ──► Motion base from the chosen character image and speech audio
       │
       ▼
[MuseTalk] ──► Lip synchronization ──► Verified 1080×1920 MP4
```

---

## 📁 Project Directory Structure

> **Historical reference:** this directory map describes the earlier cloud pipeline, not the current desktop implementation.

```
video-creative-studio/
├── config/
│   └── settings.json               # Video presets, voice mappings, lipsync config
├── core/
│   ├── script_director.py          # AI scene splitter & multi-cam director
│   ├── tts_engine.py               # Multilingual TTS & word timestamp engine
│   ├── matting_engine.py           # BiRefNet / Rembg alpha background removal
│   ├── lipsync_engine.py           # MuseTalk & ProStudio-AI adapter
│   └── video_composer.py           # FFmpeg multi-layer compositor & audio ducking
├── assets/
│   ├── characters/                 # Two canonical front-facing samples; custom images are runtime assets
│   ├── backgrounds/                # Video background loops (studio, office, tech room)
│   ├── brolls/                     # B-roll footage for cutaways
│   └── audio/                      # Background music (BGM) & Sound Effects (SFX)
├── test_samples/
│   ├── script_spanish_sample.txt   # Sample Spanish TikTok/Reels script
│   └── script_english_sample.txt   # Sample English script
├── runpod_setup.sh                 # 1-Click bootstrap script for RunPod cloud deployment
└── run_pipeline.py                 # Master pipeline execution CLI
```

---

## 🚀 How to Run on Cloud (RunPod RTX A4500 / RTX 4000 Ada)

> **Historical workflow:** this RunPod batch workflow predates the current desktop Echo Flash → MuseTalk flow and does not describe the Studio render button.

### 1. Upload & Setup (1-Click)
1. Deploy your Pod on RunPod (**RTX A4500 $0.26/h** or **RTX 4000 Ada $0.28/h**).
2. Ensure **Container Disk is set to 50 GB**.
3. Open Web Terminal and run:
   ```bash
   cd /workspace
   # Upload or clone video-creative-studio
   cd video-creative-studio
   bash runpod_setup.sh
   ```

### 2. Run the Full Batch Production Suite (~30-45 mins on Pod)
To automatically process all 6 diverse evaluation projects across 3 character styles and 3 languages:
```bash
python batch_run_pod.py
```

### 3. Evaluation Projects Included in the Batch
1. **01_nam_spanish_business.mp4**: Nam Doanh Nhân (nhanvatnam) - Tiếng Tây Ban Nha (Alvaro) - Topic: Kinh doanh & FinTech
2. **02_nam_english_tech.mp4**: Nam Chuyên Gia (nhanvatnam) - Tiếng Anh (Guy) - Topic: AI Tech & Automation
3. **03_nu_english_productivity.mp4**: Nữ Chuyên Gia (nhanvatnu) - Tiếng Anh (Jenny) - Topic: Productivity & Lifestyle
4. **04_nu_vietnamese_startup.mp4**: Nữ Khởi Nghiệp (nhanvatnu) - Tiếng Việt (HoaiMy) - Topic: Khởi nghiệp & Video ngắn
5. **05_hoathinh_english_story.mp4**: Hoạt hình 3D Pixar (hoathinhnu) - Tiếng Anh (Ana) - Topic: Kể chuyện thiếu nhi
6. **06_hoathinh_spanish_story.mp4**: Hoạt hình 3D Pixar (hoathinhnu) - Tiếng Tây Ban Nha (Dalia) - Topic: Cuentos Infantiles

### 4. Review Results
* Mở file `output/batch_results/index.html` trên trình duyệt để xem toàn bộ 6 video cạnh nhau, so sánh chất lượng hình ảnh, độ khớp khẩu hình và giọng đọc!
