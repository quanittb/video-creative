#!/usr/bin/env bash
# ==============================================================================
# 1-CLICK BOOTSTRAP SCRIPT FOR RUNPOD (RTX 4000 Ada / RTX 4090)
# Automated Video Creative Studio Setup
# ==============================================================================
set -e

echo "=========================================================="
echo "🚀 INITIATING VIDEO CREATIVE STUDIO BOOTSTRAP ON RUNPOD"
echo "=========================================================="

# 1. System packages
echo "[1/5] Updating system packages and installing FFmpeg..."
apt-get update -qq && apt-get install -y -qq ffmpeg git git-lfs wget curl libgl1-mesa-glx > /dev/null

# 2. Python core dependencies
echo "[2/5] Installing core python libraries..."
pip install --quiet --upgrade pip
pip install --quiet \
    edge-tts \
    opencv-python-headless \
    rembg[gpu] \
    onnxruntime-gpu \
    pillow \
    soundfile \
    scipy \
    timm \
    diffusers \
    transformers \
    accelerate \
    google-generativeai

# 3. Create model storage structure
echo "[3/6] Setting up model checkpoints folder..."
MODELS_DIR="/workspace/models"
mkdir -p "$MODELS_DIR/wav2lip" "$MODELS_DIR/musetalk" "$MODELS_DIR/buffalo_l"

# 4. Fast-download pre-trained models
echo "[4/6] Downloading pre-trained face enhancement & models..."
# GFPGAN v1.4
if [ ! -f "$MODELS_DIR/wav2lip/gfpgan_1.4.onnx" ]; then
    echo "Downloading GFPGAN 1.4 ONNX..."
    wget -q -O "$MODELS_DIR/wav2lip/gfpgan_1.4.onnx" \
        "https://github.com/TencentARC/GFPGAN/releases/download/v1.3.0/GFPGANv1.4.pth" || true
fi

# Buffalo_l for InsightFace
if [ ! -d "$MODELS_DIR/buffalo_l/1k3d68.onnx" ]; then
    echo "Downloading Buffalo_l face models..."
    wget -q -O /tmp/buffalo_l.zip "https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip" || true
    if [ -f /tmp/buffalo_l.zip ]; then
        unzip -q -o /tmp/buffalo_l.zip -d "$MODELS_DIR/buffalo_l/" || true
        rm -f /tmp/buffalo_l.zip
    fi
fi

# 5. Setup LivePortrait for Expressive Head Motion & Facial Animation
echo "[5/6] Setting up LivePortrait (High-fidelity Head Driving & Facial Expressions)..."
if [ ! -d "/workspace/LivePortrait" ]; then
    git clone --depth 1 https://github.com/KwaiVGI/LivePortrait.git /workspace/LivePortrait
    pip install --quiet -r /workspace/LivePortrait/requirements.txt || true
    pip install --quiet huggingface_hub
    echo "Downloading LivePortrait pretrained weights..."
    python3 -c "
from huggingface_hub import snapshot_download
snapshot_download('KwaiVGI/LivePortrait', local_dir='/workspace/LivePortrait/pretrained_weights', ignore_patterns=['*.md', '*.git*'])
" || true
fi

# 6. Initialize workspace directories
echo "[6/6] Initializing workspace directories..."
mkdir -p assets/characters assets/backgrounds assets/audio assets/brolls assets/driving_templates temp output output/batch_results

echo "=========================================================="
echo "✅ RUNPOD SETUP COMPLETE! ZERO DOWNTIME READY!"
echo "To generate the full 6-project benchmark matching Avatar_Video.mp4, run:"
echo "python batch_run_pod.py"
echo "=========================================================="

