#!/usr/bin/env python3
"""
Full automation daemon for Julian Dorey clip pipeline.

Runs continuously:
  1. Watches clips-input/ for new clips
  2. Validates (episode 343+)
  3. Applies watermark
  4. Generates captions
  5. Posts to Instagram, TikTok, YouTube on schedule
  6. Archives posted clips

No Docker or n8n required — just Python + FFmpeg.

Usage:
  python3 scripts/automate.py                    # dry-run mode (test everything)
  python3 scripts/automate.py --live             # actually post to platforms
  python3 scripts/automate.py --once             # process + post once, then exit
  python3 scripts/automate.py --once --dry-run   # full test, single pass
"""

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("automate")

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}

# Directories
INPUT_DIR = PROJECT_ROOT / "data" / "clips-input"
PROCESSED_DIR = PROJECT_ROOT / "data" / "clips-processed"
POSTED_DIR = PROJECT_ROOT / "data" / "clips-posted"
REJECTED_DIR = PROJECT_ROOT / "data" / "clips-rejected"
WATERMARK_PATH = PROJECT_ROOT / "config" / "watermark" / "julian_dorey_watermark.png"

STATE_FILE = PROJECT_ROOT / "data" / "automation_state.json"


def ensure_dirs():
    for d in [INPUT_DIR, PROCESSED_DIR, POSTED_DIR, REJECTED_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"posted_files": [], "last_post_time": None, "queue": []}


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def is_file_stable(path, wait=2):
    try:
        size1 = path.stat().st_size
        time.sleep(wait)
        size2 = path.stat().st_size
        return size1 == size2 and size1 > 0
    except OSError:
        return False


def find_new_clips():
    clips = []
    for f in sorted(INPUT_DIR.iterdir()):
        if f.is_file() and f.suffix.lower() in VIDEO_EXTENSIONS:
            clips.append(f)
    return clips


def find_ready_clips():
    clips = []
    for f in sorted(PROCESSED_DIR.iterdir()):
        if f.is_file() and f.suffix.lower() in VIDEO_EXTENSIONS:
            clips.append(f)
    return clips


def validate_clip(clip_path):
    r = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "validate_clip.py"), "--json", str(clip_path)],
        capture_output=True, text=True,
    )
    try:
        data = json.loads(r.stdout)
        return data.get("valid", False), data.get("errors", [])
    except json.JSONDecodeError:
        return False, ["validation script failed"]


def apply_watermark(clip_path, output_path):
    r = subprocess.run(
        [
            sys.executable, str(SCRIPT_DIR / "apply_watermark.py"),
            str(clip_path), str(output_path),
            "--watermark", str(WATERMARK_PATH),
            "--scale", "0.25",
            "--opacity", "0.8",
        ],
        capture_output=True, text=True,
    )
    return r.returncode == 0, r.stderr


def post_clip(clip_path, platforms, dry_run):
    r = subprocess.run(
        [
            sys.executable, str(SCRIPT_DIR / "post_to_platforms.py"),
            str(clip_path),
            "--platforms", *platforms,
        ] + ([] if dry_run else ["--live"]),
        capture_output=True, text=True,
    )
    log.info("Post output:\n%s", r.stdout.strip())
    if r.stderr.strip():
        for line in r.stderr.strip().splitlines():
            log.info("  %s", line)
    return r.returncode == 0


# ---------------------------------------------------------------------------
# Pipeline stages
# ---------------------------------------------------------------------------

def stage_ingest():
    """Pick up new clips from input, validate, watermark, move to processed."""
    new_clips = find_new_clips()
    if not new_clips:
        return 0

    processed_count = 0

    for clip in new_clips:
        log.info("--- New clip: %s ---", clip.name)

        if not is_file_stable(clip, wait=1):
            log.info("  Still uploading, skipping for now")
            continue

        valid, errors = validate_clip(clip)
        if not valid:
            log.warning("  REJECTED: %s", "; ".join(errors))
            dest = REJECTED_DIR / clip.name
            shutil.move(str(clip), str(dest))
            reason_file = REJECTED_DIR / f"{clip.name}.reason.txt"
            reason_file.write_text("\n".join(errors))
            continue

        out_name = f"{clip.stem}_watermarked{clip.suffix}"
        out_path = PROCESSED_DIR / out_name

        log.info("  Applying watermark...")
        ok, err = apply_watermark(clip, out_path)
        if ok and out_path.exists():
            log.info("  Watermarked -> %s", out_path.name)
            archive = INPUT_DIR / "_done"
            archive.mkdir(exist_ok=True)
            shutil.move(str(clip), str(archive / clip.name))
            processed_count += 1
        else:
            log.error("  Watermark failed: %s", err[:200])
            dest = REJECTED_DIR / clip.name
            shutil.move(str(clip), str(dest))

    return processed_count


def stage_post(platforms, dry_run, state):
    """Post the next ready clip to all platforms."""
    ready = find_ready_clips()

    already_posted = set(state.get("posted_files", []))
    to_post = [c for c in ready if c.name not in already_posted]

    if not to_post:
        log.info("No new clips to post")
        return state

    clip = to_post[0]
    log.info("--- Posting: %s ---", clip.name)

    ok = post_clip(clip, platforms, dry_run)

    if ok:
        state.setdefault("posted_files", []).append(clip.name)
        state["last_post_time"] = datetime.now().isoformat()

        dest = POSTED_DIR / clip.name
        shutil.move(str(clip), str(dest))
        log.info("  Archived -> %s", dest)
    else:
        log.error("  Posting failed, will retry next cycle")

    return state


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run_once(platforms, dry_run):
    """Single pass: ingest + post."""
    log.info("=== INGEST STAGE ===")
    ingested = stage_ingest()
    log.info("Ingested %d clip(s)\n", ingested)

    log.info("=== POST STAGE ===")
    state = load_state()
    state = stage_post(platforms, dry_run, state)
    save_state(state)

    log.info("\n=== DONE ===")


def run_loop(platforms, dry_run, post_interval_minutes):
    """Continuous loop: ingest constantly, post on schedule."""
    log.info("Starting automation daemon")
    log.info("  Mode: %s", "DRY RUN" if dry_run else "LIVE")
    log.info("  Platforms: %s", ", ".join(platforms))
    log.info("  Post interval: every %d minutes", post_interval_minutes)
    log.info("  Input: %s", INPUT_DIR)
    log.info("  Processed: %s", PROCESSED_DIR)
    log.info("  Posted: %s", POSTED_DIR)
    log.info("")

    state = load_state()
    last_post = None

    if state.get("last_post_time"):
        try:
            last_post = datetime.fromisoformat(state["last_post_time"])
        except ValueError:
            pass

    while True:
        try:
            # Always ingest
            ingested = stage_ingest()
            if ingested > 0:
                log.info("Ingested %d clip(s)", ingested)

            # Post on schedule
            now = datetime.now()
            should_post = (
                last_post is None
                or (now - last_post) >= timedelta(minutes=post_interval_minutes)
            )

            if should_post:
                state = load_state()
                state = stage_post(platforms, dry_run, state)
                save_state(state)
                last_post = now

        except KeyboardInterrupt:
            log.info("\nShutting down...")
            break
        except Exception as e:
            log.error("Error in automation loop: %s", e)

        time.sleep(30)


def main():
    parser = argparse.ArgumentParser(
        description="Full automation: watch -> validate -> watermark -> post"
    )
    parser.add_argument("--live", action="store_true", help="Actually post to platforms")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Simulate posting (default)")
    parser.add_argument("--once", action="store_true",
                        help="Run one pass then exit (don't loop)")
    parser.add_argument(
        "--platforms", nargs="+",
        default=["instagram", "tiktok", "youtube"],
        choices=["instagram", "tiktok", "youtube"],
    )
    parser.add_argument("--interval", type=int, default=480,
                        help="Minutes between posts (default: 480 = 8 hours, ~3 posts/day)")
    args = parser.parse_args()

    dry_run = not args.live

    ensure_dirs()

    if args.once:
        run_once(args.platforms, dry_run)
    else:
        run_loop(args.platforms, dry_run, args.interval)


if __name__ == "__main__":
    main()
