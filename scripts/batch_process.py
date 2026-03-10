#!/usr/bin/env python3
"""
Batch process all clips in a directory.
Validates each clip, applies watermark, outputs to a target directory.

Usage:
  python batch_process.py /path/to/raw/clips /path/to/output
  python batch_process.py ~/clips-raw ~/clips-ready --watermark ./watermark.png
"""

import argparse
import os
import sys
import json
import subprocess
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
VALIDATE_SCRIPT = SCRIPT_DIR / "validate_clip.py"
WATERMARK_SCRIPT = SCRIPT_DIR / "apply_watermark.py"

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}


def find_clips(input_dir):
    """Find all video files in input_dir (non-recursive)."""
    clips = []
    for entry in sorted(Path(input_dir).iterdir()):
        if entry.is_file() and entry.suffix.lower() in VIDEO_EXTENSIONS:
            clips.append(entry)
    return clips


def validate(clip_path):
    """Returns (valid, episode_number, errors)."""
    result = subprocess.run(
        [sys.executable, str(VALIDATE_SCRIPT), "--json", str(clip_path)],
        capture_output=True, text=True,
    )
    try:
        data = json.loads(result.stdout)
        return data.get("valid", False), data.get("episode"), data.get("errors", [])
    except json.JSONDecodeError:
        return False, None, [result.stderr or "validation script failed"]


def watermark(clip_path, output_path, watermark_path, scale, opacity):
    """Apply watermark. Returns True on success."""
    result = subprocess.run(
        [
            sys.executable, str(WATERMARK_SCRIPT),
            str(clip_path), str(output_path),
            "--watermark", str(watermark_path),
            "--scale", str(scale),
            "--opacity", str(opacity),
        ],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"    ERROR: {result.stderr.strip()}", file=sys.stderr)
        return False
    return True


def main():
    parser = argparse.ArgumentParser(description="Batch process Julian Dorey clips")
    parser.add_argument("input_dir", help="Directory containing raw clips")
    parser.add_argument("output_dir", help="Directory for watermarked output")
    parser.add_argument(
        "--watermark",
        default=str(SCRIPT_DIR.parent / "config" / "watermark" / "julian_dorey_watermark.png"),
        help="Path to watermark PNG",
    )
    parser.add_argument("--scale", type=float, default=0.25)
    parser.add_argument("--opacity", type=float, default=0.8)
    parser.add_argument("--dry-run", action="store_true", help="Validate only, don't process")
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)

    if not input_dir.is_dir():
        print(f"Input directory not found: {input_dir}", file=sys.stderr)
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    if not args.dry_run and not Path(args.watermark).is_file():
        print(f"Watermark not found: {args.watermark}", file=sys.stderr)
        print("Run: bash scripts/download_watermark.sh", file=sys.stderr)
        sys.exit(1)

    clips = find_clips(input_dir)
    if not clips:
        print(f"No video files found in {input_dir}")
        sys.exit(0)

    print(f"Found {len(clips)} clips in {input_dir}\n")

    results = {"processed": 0, "skipped": 0, "failed": 0, "invalid": 0}

    for i, clip in enumerate(clips, 1):
        print(f"[{i}/{len(clips)}] {clip.name}")

        valid, episode, errors = validate(clip)
        if not valid:
            print(f"    INVALID: {'; '.join(errors)}")
            results["invalid"] += 1
            continue

        print(f"    Episode {episode} - valid")

        if args.dry_run:
            results["skipped"] += 1
            continue

        out_name = f"{clip.stem}_watermarked{clip.suffix}"
        out_path = output_dir / out_name

        if out_path.exists():
            print(f"    SKIP: output already exists")
            results["skipped"] += 1
            continue

        ok = watermark(clip, out_path, args.watermark, args.scale, args.opacity)
        if ok:
            print(f"    OK -> {out_path}")
            results["processed"] += 1
        else:
            results["failed"] += 1

    print(f"\nDone: {results['processed']} processed, {results['skipped']} skipped, "
          f"{results['invalid']} invalid, {results['failed']} failed")


if __name__ == "__main__":
    main()
