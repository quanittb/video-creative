# 🎬 Video Creative Studio

> Desktop studio for rendering vertical avatar videos with Echo Flash motion generation and MuseTalk lip synchronization.

The current production flow is available in the Tauri desktop app: choose one of the two front-facing sample characters (or upload a custom image), enter a script to synthesize speech, then render a verified 1080×1920 video. Browser preview cannot inspect the host GPU or run inference. Use **Settings → Model render Echo Flash + MuseTalk** to inspect and manage the local model assets.

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

> **Legacy instructions:** this RunPod batch workflow predates the current desktop Echo Flash → MuseTalk flow. It is kept as historical material and does not describe the Studio render button.

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
