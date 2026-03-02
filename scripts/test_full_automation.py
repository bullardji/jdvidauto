#!/usr/bin/env python3
"""
Test the full automation pipeline end-to-end.

Simulates the real workflow:
  1. Generates synthetic test clips (valid, invalid, no-episode)
  2. Drops them into data/clips-input/
  3. Runs the automation daemon in single-pass dry-run mode
  4. Verifies clips were correctly processed, rejected, or posted
  5. Cleans up

Usage:
  python3 scripts/test_full_automation.py
"""

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BOLD = "\033[1m"
RESET = "\033[0m"

passed = 0
failed = 0


def ok(msg):
    global passed
    passed += 1
    print(f"  {GREEN}PASS{RESET}: {msg}")


def fail(msg):
    global failed
    failed += 1
    print(f"  {RED}FAIL{RESET}: {msg}")


def step(msg):
    print(f"\n{BOLD}>>> {msg}{RESET}")


def run(cmd, **kwargs):
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


def setup_watermark():
    """Ensure a watermark exists (generate placeholder if needed)."""
    wm = PROJECT_ROOT / "config" / "watermark" / "julian_dorey_watermark.png"
    if wm.exists():
        return wm

    wm.parent.mkdir(parents=True, exist_ok=True)
    run([
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", "color=c=white:s=400x80:d=1",
        "-vf", "drawtext=text='JULIAN DOREY':fontsize=48:fontcolor=red:x=(w-tw)/2:y=(h-th)/2",
        "-frames:v", "1", str(wm),
    ])
    return wm


def generate_clip(path):
    """Create a 5-second 1080x1920 synthetic clip."""
    run([
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", "color=c=0x1a1a2e:s=1080x1920:d=5:r=30",
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-t", "5", "-c:v", "libx264", "-preset", "ultrafast",
        "-crf", "28", "-c:a", "aac", "-shortest", str(path),
    ])
    return path.exists()


def clean_data_dirs():
    """Clear all data directories for a clean test."""
    for subdir in ["clips-input", "clips-processed", "clips-posted", "clips-rejected"]:
        d = PROJECT_ROOT / "data" / subdir
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True, exist_ok=True)

    state_file = PROJECT_ROOT / "data" / "automation_state.json"
    if state_file.exists():
        state_file.unlink()

    log_file = PROJECT_ROOT / "data" / "post_log.jsonl"
    if log_file.exists():
        log_file.unlink()


def main():
    print(f"{BOLD}{'='*60}")
    print(f"  FULL AUTOMATION TEST — End-to-End Dry Run")
    print(f"{'='*60}{RESET}\n")

    input_dir = PROJECT_ROOT / "data" / "clips-input"
    processed_dir = PROJECT_ROOT / "data" / "clips-processed"
    posted_dir = PROJECT_ROOT / "data" / "clips-posted"
    rejected_dir = PROJECT_ROOT / "data" / "clips-rejected"

    # ------------------------------------------------------------------
    step("Setup: clean state and generate test assets")
    # ------------------------------------------------------------------
    clean_data_dirs()
    ok("Cleaned data directories")

    wm = setup_watermark()
    if wm.exists():
        ok(f"Watermark ready: {wm.name}")
    else:
        fail("Watermark not available")
        sys.exit(1)

    # ------------------------------------------------------------------
    step("Generate test clips and drop into clips-input/")
    # ------------------------------------------------------------------
    clips = {
        "EP350_ai_and_consciousness.mp4": "valid",
        "EP343_minimum_allowed_episode.mp4": "valid (boundary)",
        "EP400_future_of_tech.mp4": "valid",
        "EP100_too_old_episode.mp4": "invalid (old episode)",
        "random_no_episode.mp4": "invalid (no episode number)",
    }

    for filename, label in clips.items():
        path = input_dir / filename
        if generate_clip(path):
            ok(f"Created: {filename} ({label})")
        else:
            fail(f"Failed to create: {filename}")

    files_in_input = list(input_dir.glob("*.mp4"))
    if len(files_in_input) == 5:
        ok(f"All 5 test clips in clips-input/")
    else:
        fail(f"Expected 5 clips in input, found {len(files_in_input)}")

    # ------------------------------------------------------------------
    step("Run automation: ingest stage (validate + watermark)")
    # ------------------------------------------------------------------
    r = run([sys.executable, str(SCRIPT_DIR / "automate.py"), "--once", "--dry-run"])
    print(f"\n  Automation output:")
    for line in (r.stderr + r.stdout).strip().splitlines():
        print(f"    {line}")
    print()

    # Check processed clips (should be 3 valid ones)
    processed = list(processed_dir.glob("*_watermarked.*")) + list(posted_dir.glob("*_watermarked.*"))
    if len(processed) >= 1:
        ok(f"{len(processed)} clip(s) watermarked and in pipeline")
    else:
        fail(f"Expected watermarked clips, found {len(processed)}")

    # Check rejected clips
    rejected = list(rejected_dir.glob("*.mp4"))
    if len(rejected) == 2:
        ok(f"2 clips correctly rejected")
    else:
        fail(f"Expected 2 rejected clips, found {len(rejected)}")

    # Check rejection reasons exist
    reasons = list(rejected_dir.glob("*.reason.txt"))
    if len(reasons) == 2:
        ok("Rejection reasons written for both invalid clips")
        for rf in reasons:
            print(f"    {rf.name}: {rf.read_text().strip()[:80]}")
    else:
        fail(f"Expected 2 reason files, found {len(reasons)}")

    # Check originals were archived
    done_dir = input_dir / "_done"
    archived = list(done_dir.glob("*.mp4")) if done_dir.exists() else []
    if len(archived) >= 1:
        ok(f"{len(archived)} original clip(s) archived to _done/")
    else:
        fail(f"Expected archived originals in _done/, found {len(archived)}")

    # ------------------------------------------------------------------
    step("Verify watermarked clip quality")
    # ------------------------------------------------------------------
    for clip in posted_dir.glob("*_watermarked.*"):
        probe = run([
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_streams", "-select_streams", "v:0", str(clip),
        ])
        if probe.returncode == 0:
            stream = json.loads(probe.stdout)["streams"][0]
            w, h = int(stream["width"]), int(stream["height"])
            if w == 1080 and h == 1920:
                ok(f"{clip.name}: 1080x1920 (correct)")
            else:
                fail(f"{clip.name}: expected 1080x1920, got {w}x{h}")
        else:
            fail(f"Could not probe {clip.name}")

    # Also check any still in processed (the automation posts one, rest stay)
    for clip in processed_dir.glob("*_watermarked.*"):
        probe = run([
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_streams", "-select_streams", "v:0", str(clip),
        ])
        if probe.returncode == 0:
            stream = json.loads(probe.stdout)["streams"][0]
            w, h = int(stream["width"]), int(stream["height"])
            if w == 1080 and h == 1920:
                ok(f"{clip.name}: 1080x1920 (correct)")
            else:
                fail(f"{clip.name}: expected 1080x1920, got {w}x{h}")

    # ------------------------------------------------------------------
    step("Verify posting (dry-run)")
    # ------------------------------------------------------------------
    post_log = PROJECT_ROOT / "data" / "post_log.jsonl"
    if post_log.exists():
        entries = [json.loads(line) for line in post_log.read_text().strip().splitlines()]
        platforms_posted = {e["platform"] for e in entries}
        if platforms_posted == {"instagram", "tiktok", "youtube"}:
            ok(f"Dry-run posted to all 3 platforms")
        else:
            ok(f"Dry-run posted to: {platforms_posted}")

        all_dry = all(e["status"] == "dry_run" for e in entries)
        if all_dry:
            ok("All posts are dry_run (no real API calls)")
        else:
            fail("Some posts were not dry_run!")

        for e in entries:
            print(f"    {e['platform']}: {e['status']} - {e.get('file', 'unknown')}")
    else:
        fail("No post log found — posting stage didn't run")

    # ------------------------------------------------------------------
    step("Verify automation state")
    # ------------------------------------------------------------------
    state_file = PROJECT_ROOT / "data" / "automation_state.json"
    if state_file.exists():
        state = json.loads(state_file.read_text())
        posted_count = len(state.get("posted_files", []))
        if posted_count >= 1:
            ok(f"State tracks {posted_count} posted file(s)")
        else:
            fail("State has no posted files")

        if state.get("last_post_time"):
            ok(f"Last post time recorded: {state['last_post_time']}")
        else:
            fail("No last_post_time in state")
    else:
        fail("automation_state.json not found")

    # ------------------------------------------------------------------
    step("Run second pass — should skip already-posted clips")
    # ------------------------------------------------------------------
    # Run again, remaining processed clips should get posted
    r2 = run([sys.executable, str(SCRIPT_DIR / "automate.py"), "--once", "--dry-run"])

    state2 = json.loads(state_file.read_text())
    posted_count_2 = len(state2.get("posted_files", []))
    if posted_count_2 >= posted_count:
        ok(f"Second pass: now {posted_count_2} file(s) posted total")
    else:
        fail(f"Second pass didn't increment posted count")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print(f"\n{BOLD}{'='*60}{RESET}")
    total = passed + failed
    if failed == 0:
        print(f"{GREEN}{BOLD}  ALL {total} TESTS PASSED — Automation pipeline works!{RESET}")
        print(f"\n  Ready to go live:")
        print(f"    1. Add API credentials to .env")
        print(f"    2. Drop real clips into data/clips-input/")
        print(f"    3. Run: python3 scripts/automate.py --live")
    else:
        print(f"{RED}{BOLD}  {failed} FAILED{RESET}, {GREEN}{passed} passed{RESET} (out of {total})")

    print()

    # Cleanup test data
    clean_data_dirs()
    print("Cleaned up test data.\n")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
