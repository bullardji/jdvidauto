#!/usr/bin/env python3
"""
Watch the clips-input directory for new video files.
When a new file arrives:
  1. Validate it (episode number >= 343, valid video)
  2. Apply the Julian Dorey watermark
  3. Move the result to clips-processed/

Runs as a long-lived process inside the clip-processor Docker container.
"""

import os
import sys
import time
import shutil
import subprocess

INPUT_DIR = os.environ.get("CLIPS_INPUT_DIR", "/data/clips-input")
PROCESSED_DIR = os.environ.get("CLIPS_PROCESSED_DIR", "/data/clips-processed")
REJECTED_DIR = os.path.join(INPUT_DIR, "_rejected")
WATERMARK_PATH = os.environ.get("WATERMARK_PATH", "/data/watermark/julian_dorey_watermark.png")
WATERMARK_SCALE = os.environ.get("WATERMARK_SCALE", "0.25")
WATERMARK_OPACITY = os.environ.get("WATERMARK_OPACITY", "0.8")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL_SECONDS", "10"))

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}
PROCESSING_SUFFIX = ".processing"


def ensure_dirs():
    os.makedirs(INPUT_DIR, exist_ok=True)
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    os.makedirs(REJECTED_DIR, exist_ok=True)


def is_video_file(filename):
    _, ext = os.path.splitext(filename.lower())
    return ext in VIDEO_EXTENSIONS


def is_file_stable(filepath, wait_seconds=3):
    """Check that the file size isn't changing (upload finished)."""
    try:
        size1 = os.path.getsize(filepath)
        time.sleep(wait_seconds)
        size2 = os.path.getsize(filepath)
        return size1 == size2 and size1 > 0
    except OSError:
        return False


def validate_clip(filepath):
    result = subprocess.run(
        [sys.executable, "/scripts/validate_clip.py", "--json", filepath],
        capture_output=True, text=True,
    )
    return result.returncode == 0, result.stdout


def process_clip(filepath):
    basename = os.path.basename(filepath)
    name, ext = os.path.splitext(basename)
    output_path = os.path.join(PROCESSED_DIR, f"{name}_watermarked{ext}")

    result = subprocess.run(
        [
            sys.executable, "/scripts/apply_watermark.py",
            filepath, output_path,
            "--watermark", WATERMARK_PATH,
            "--scale", WATERMARK_SCALE,
            "--opacity", WATERMARK_OPACITY,
        ],
        capture_output=True, text=True,
    )

    if result.returncode == 0:
        print(f"  Processed -> {output_path}")
        return True
    else:
        print(f"  Watermark failed: {result.stderr}", file=sys.stderr)
        return False


def reject_clip(filepath, reason):
    basename = os.path.basename(filepath)
    dest = os.path.join(REJECTED_DIR, basename)
    shutil.move(filepath, dest)
    reason_file = os.path.join(REJECTED_DIR, f"{basename}.reason.txt")
    with open(reason_file, "w") as f:
        f.write(reason)
    print(f"  Rejected -> {dest} ({reason})")


def scan_and_process():
    """One pass: find new videos in input dir, validate, watermark, move."""
    for filename in sorted(os.listdir(INPUT_DIR)):
        filepath = os.path.join(INPUT_DIR, filename)

        if not os.path.isfile(filepath):
            continue
        if not is_video_file(filename):
            continue
        if filename.endswith(PROCESSING_SUFFIX):
            continue

        lock_path = filepath + PROCESSING_SUFFIX
        if os.path.exists(lock_path):
            continue

        if not is_file_stable(filepath):
            print(f"  Skipping {filename} (still uploading)")
            continue

        print(f"\nNew clip: {filename}")

        # Lock file to prevent double-processing
        with open(lock_path, "w") as f:
            f.write("processing")

        try:
            valid, output = validate_clip(filepath)
            if not valid:
                reject_clip(filepath, output)
                continue

            ok = process_clip(filepath)
            if ok:
                archive_path = os.path.join(INPUT_DIR, "_done", filename)
                os.makedirs(os.path.dirname(archive_path), exist_ok=True)
                shutil.move(filepath, archive_path)
            else:
                reject_clip(filepath, "watermark processing failed")
        finally:
            if os.path.exists(lock_path):
                os.remove(lock_path)


def main():
    print("=== Julian Dorey Clip Processor ===")
    print(f"  Input:     {INPUT_DIR}")
    print(f"  Output:    {PROCESSED_DIR}")
    print(f"  Watermark: {WATERMARK_PATH}")
    print(f"  Scale:     {WATERMARK_SCALE}")
    print(f"  Opacity:   {WATERMARK_OPACITY}")
    print(f"  Poll:      every {POLL_INTERVAL}s")
    print()

    ensure_dirs()

    while True:
        try:
            scan_and_process()
        except Exception as e:
            print(f"Error during scan: {e}", file=sys.stderr)
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
