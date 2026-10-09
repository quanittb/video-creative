# 🎬 Video Creative Studio

> **Automated Multi-Angle Video Generation Engine**  
> High-retention short-form video production from raw scripts and multi-angle character assets.

---

## ⚡ Quick Architecture Overview

```
[Raw Script (ES/EN/VI)] 
       │
       ▼
[1. Script Director] ──► Decomposes into 3-6s scenes (Hook, Explain, Punchline, CTA)
       │                  Assigns Multi-Camera Angles (Front, 45°, Close-up) & B-Roll
       ▼
[2. Multilingual TTS] ──► Synthesizes natural audio (Edge-TTS / Pro Studio Workers)
       │                  Generates word-level timestamps for subtitles
       ▼
[3. Lip-Sync Engine] ──► Runs MuseTalk / LivePortrait / LatentSync with GFPGAN enhancement
       │
       ▼
[4. Video Composer]  ──► Integrates Dynamic Background Video + Bokeh Blur + Camera Punch-in
                          Adds B-roll cutaway + BGM Ducking + Word-level Karaoke Subtitles
       │
       ▼
[Final 1080x1920 MP4 Video]
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
│   ├── characters/                 # Character angle photos (angle_front, angle_45, closeup)
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
