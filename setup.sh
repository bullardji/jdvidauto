#!/usr/bin/env bash
#
# One-command setup for Julian Dorey clip automation.
# Run: bash setup.sh
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Julian Dorey Clip Automation Setup ==="
echo ""

# 1. Check dependencies
echo "Checking dependencies..."

check_cmd() {
    if command -v "$1" &>/dev/null; then
        echo "  [OK] $1"
        return 0
    else
        echo "  [MISSING] $1"
        return 1
    fi
}

MISSING=0
check_cmd python3 || MISSING=1
check_cmd ffmpeg  || MISSING=1
check_cmd ffprobe || MISSING=1

if [ "$MISSING" -eq 1 ]; then
    echo ""
    echo "Install missing dependencies:"
    echo "  macOS:  brew install python ffmpeg"
    echo "  Ubuntu: sudo apt install python3 python3-pip ffmpeg"
    echo ""
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then exit 1; fi
fi

# 2. Python deps
echo ""
echo "Installing Python dependencies..."
pip3 install -q -r requirements.txt 2>/dev/null || pip install -q -r requirements.txt

# 3. Download watermark
echo ""
echo "Downloading watermark..."
bash scripts/download_watermark.sh

# 4. Create env file if missing
if [ ! -f .env ]; then
    echo ""
    echo "Creating .env from template..."
    cp .env.example .env
    echo "  Edit .env to add your API keys when ready to post."
fi

# 5. Create data directories
echo ""
echo "Creating data directories..."
mkdir -p data/clips-input data/clips-processed data/clips-posted
echo "  data/clips-input/     <- drop raw clips here"
echo "  data/clips-processed/ <- watermarked clips appear here"
echo "  data/clips-posted/    <- archive of posted clips"

# 6. Done
echo ""
echo "=== Setup Complete ==="
echo ""
echo "Quick start:"
echo "  1. Drop clips into data/clips-input/"
echo "     Name them: EP345_topic_description.mp4 (episode 343+ only)"
echo ""
echo "  2. Process a single clip:"
echo "     bash scripts/process_clip.sh data/clips-input/EP345_my_clip.mp4"
echo ""
echo "  3. Batch process all clips:"
echo "     python3 scripts/batch_process.py data/clips-input/ data/clips-processed/"
echo ""
echo "  4. Generate captions for posting:"
echo "     python3 scripts/generate_captions.py data/clips-processed/ --all"
echo ""
echo "  5. (Optional) Start n8n for automated posting:"
echo "     docker compose up -d"
echo "     Open http://localhost:5678"
