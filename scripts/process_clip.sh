#!/usr/bin/env bash
#
# Quick manual processing of a single clip.
# Usage: ./scripts/process_clip.sh input.mp4 [output.mp4]
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WATERMARK="${WATERMARK_PATH:-config/watermark/julian_dorey_watermark.png}"

INPUT="$1"
if [ -z "$INPUT" ]; then
    echo "Usage: $0 <input.mp4> [output.mp4]" >&2
    exit 1
fi

BASENAME="$(basename "$INPUT" | sed 's/\.[^.]*$//')"
OUTPUT="${2:-${BASENAME}_watermarked.mp4}"

echo "=== Validating ==="
python3 "$SCRIPT_DIR/validate_clip.py" "$INPUT"

echo ""
echo "=== Applying Watermark ==="
python3 "$SCRIPT_DIR/apply_watermark.py" "$INPUT" "$OUTPUT" --watermark "$WATERMARK"

echo ""
echo "Done: $OUTPUT"
