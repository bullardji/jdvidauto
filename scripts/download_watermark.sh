#!/usr/bin/env bash
#
# Download the Julian Dorey YouTube watermark from Google Drive.
# Places it at config/watermark/julian_dorey_watermark.png
#
set -euo pipefail

DEST_DIR="$(cd "$(dirname "$0")/../config/watermark" && pwd)"
DEST_FILE="$DEST_DIR/julian_dorey_watermark.png"

GDRIVE_FILE_ID="1TwHRHaww5vSOWIDVUoHJUsKcH9L1OUjQ"
DOWNLOAD_URL="https://drive.google.com/uc?export=download&id=${GDRIVE_FILE_ID}"

mkdir -p "$DEST_DIR"

if [ -f "$DEST_FILE" ]; then
    echo "Watermark already exists at: $DEST_FILE"
    exit 0
fi

echo "Downloading Julian Dorey watermark..."

if command -v curl &>/dev/null; then
    curl -L -o "$DEST_FILE" "$DOWNLOAD_URL"
elif command -v wget &>/dev/null; then
    wget -O "$DEST_FILE" "$DOWNLOAD_URL"
else
    echo "Error: neither curl nor wget found." >&2
    exit 1
fi

if [ -f "$DEST_FILE" ] && [ -s "$DEST_FILE" ]; then
    echo "Saved to: $DEST_FILE"
    echo "File size: $(du -h "$DEST_FILE" | cut -f1)"
else
    echo "Download failed or file is empty." >&2
    rm -f "$DEST_FILE"
    exit 1
fi
